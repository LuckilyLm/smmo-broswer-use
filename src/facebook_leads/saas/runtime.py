from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterator
from urllib.error import URLError
from urllib.request import urlopen

from src.facebook_leads.facebook.orchestrator import default_health_check

from .db import utc_now
from .models import TenantContext
from .storage import SaaSStorage


LoginChecker = Callable[[str], Awaitable[str]]


class BrowserRuntimeError(RuntimeError):
    def __init__(self, error_type: str, message: str):
        super().__init__(message)
        self.error_type = error_type


class BrowserRuntimeRegistry:
    def __init__(
        self,
        storage: SaaSStorage,
        *,
        profiles_root: str | Path = "data/browser_profiles",
        chrome_executable: str | None = None,
        login_checker: LoginChecker | None = None,
    ) -> None:
        self.storage = storage
        self.profiles_root = Path(profiles_root)
        self.chrome_executable = chrome_executable or os.getenv("SAAS_CHROME_EXECUTABLE") or _find_chrome()
        self.login_checker = login_checker or _default_login_checker

    def get_runtime(self, context: TenantContext, account_id: str) -> dict[str, Any] | None:
        return self.storage.find_one("browser_runtimes", {"tenant_id": context.tenant_id, "platform_account_id": account_id})

    def get_runtime_by_id(self, context: TenantContext, runtime_id: str) -> dict[str, Any] | None:
        return self.storage.get_by_id("browser_runtimes", runtime_id, tenant_id=context.tenant_id)

    def create_runtime(self, context: TenantContext, account_id: str) -> dict[str, Any]:
        existing = self.get_runtime(context, account_id)
        if existing:
            return existing
        account = self.storage.get_by_id("platform_accounts", account_id, tenant_id=context.tenant_id)
        if not account:
            raise BrowserRuntimeError("platform_account_not_found", "platform account not found")
        cdp_port = self.allocate_port()
        profile_path = self.profile_path(context.tenant_id, account_id)
        profile_path.mkdir(parents=True, exist_ok=True)
        runtime = self.storage.insert(
            "browser_runtimes",
            {
                "tenant_id": context.tenant_id,
                "platform_account_id": account_id,
                "runtime_type": "local_chrome_cdp",
                "status": "stopped",
                "profile_path": str(profile_path),
                "cdp_port": cdp_port,
                "cdp_url": f"http://127.0.0.1:{cdp_port}",
            },
        )
        self.storage.update_by_id("platform_accounts", account_id, {"browser_runtime_id": runtime["id"]}, tenant_id=context.tenant_id)
        return runtime

    def start_runtime(self, context: TenantContext, account_id: str, *, url: str = "https://www.facebook.com/") -> dict[str, Any]:
        runtime = self.create_runtime(context, account_id)
        self.reconcile_runtime(context, runtime["id"])
        runtime = self.get_runtime_by_id(context, runtime["id"]) or runtime
        if runtime["status"] == "running" and self.health_check(context, runtime["id"])["reachable"]:
            return self.get_runtime_by_id(context, runtime["id"]) or runtime
        if not self.chrome_executable or not Path(self.chrome_executable).exists():
            return self._mark_error(context, runtime, "missing_chrome_executable", "SAAS_CHROME_EXECUTABLE does not point to chrome.exe")
        Path(runtime["profile_path"]).mkdir(parents=True, exist_ok=True)
        self.storage.update_by_id("browser_runtimes", runtime["id"], {"status": "starting", "last_error": None}, tenant_id=context.tenant_id)
        process = subprocess.Popen(
            [
                self.chrome_executable,
                f"--remote-debugging-port={runtime['cdp_port']}",
                f"--user-data-dir={runtime['profile_path']}",
                "--no-first-run",
                "--no-default-browser-check",
                "--new-window",
                url,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        updated = self.storage.update_by_id(
            "browser_runtimes",
            runtime["id"],
            {"status": "running", "browser_pid": process.pid, "started_at": utc_now(), "stopped_at": None, "last_error": None},
            tenant_id=context.tenant_id,
        )
        if not _wait_for_cdp(runtime["cdp_url"], timeout_seconds=8):
            if _pid_exists(process.pid):
                _terminate_process_tree(process.pid)
            self.storage.update_by_id("browser_runtimes", runtime["id"], {"browser_pid": None}, tenant_id=context.tenant_id)
            return self._mark_error(context, runtime, "cdp_start_timeout", "Chrome started but CDP did not become reachable")
        return updated or runtime

    def stop_runtime(self, context: TenantContext, account_id: str) -> dict[str, Any]:
        runtime = self.get_runtime(context, account_id)
        if not runtime:
            raise BrowserRuntimeError("runtime_not_found", "runtime not found")
        pid = runtime.get("browser_pid")
        if pid and _pid_exists(int(pid)):
            _terminate_process_tree(int(pid))
        return self.storage.update_by_id(
            "browser_runtimes",
            runtime["id"],
            {"status": "stopped", "browser_pid": None, "stopped_at": utc_now()},
            tenant_id=context.tenant_id,
        ) or runtime

    def restart_runtime(self, context: TenantContext, account_id: str) -> dict[str, Any]:
        self.stop_runtime(context, account_id)
        return self.start_runtime(context, account_id)

    def reset_profile(self, context: TenantContext, account_id: str, *, confirm: str) -> dict[str, Any]:
        if confirm != "RESET PROFILE":
            raise BrowserRuntimeError("confirmation_required", "reset profile requires exact confirmation")
        runtime = self.get_runtime(context, account_id)
        if runtime:
            self.stop_runtime(context, account_id)
            profile = self._safe_profile_path(context.tenant_id, account_id, runtime["profile_path"])
            if profile.exists():
                shutil.rmtree(profile, ignore_errors=True)
            self.storage.delete_by_id("browser_runtimes", runtime["id"], tenant_id=context.tenant_id)
        self.storage.update_by_id(
            "platform_accounts",
            account_id,
            {"browser_runtime_id": None, "login_status": "unknown", "connection_status": "not_connected", "last_connection_error": None},
            tenant_id=context.tenant_id,
        )
        return self.create_runtime(context, account_id)

    def health_check(self, context: TenantContext, runtime_id: str) -> dict[str, Any]:
        runtime = self.get_runtime_by_id(context, runtime_id)
        if not runtime:
            raise BrowserRuntimeError("runtime_not_found", "runtime not found")
        reachable = _cdp_reachable(runtime["cdp_url"])
        status = "running" if reachable else "unhealthy"
        if not reachable and runtime.get("browser_pid") and not _pid_exists(int(runtime["browser_pid"])):
            status = "stopped"
        updated = self.storage.update_by_id(
            "browser_runtimes",
            runtime["id"],
            {"status": status, "last_health_check_at": utc_now(), "last_error": None if reachable else "CDP unreachable"},
            tenant_id=context.tenant_id,
        )
        return {"reachable": reachable, "status": status, "runtime": safe_runtime(updated or runtime)}

    async def check_login(self, context: TenantContext, account_id: str) -> dict[str, Any]:
        runtime = self.get_runtime(context, account_id)
        if not runtime:
            raise BrowserRuntimeError("runtime_not_found", "runtime not found")
        health = self.health_check(context, runtime["id"])
        if not health["reachable"]:
            login_status = "error"
            connection_status = "not_connected"
            error = "CDP unreachable"
        else:
            try:
                login_status = await self.login_checker(runtime["cdp_url"])
                connection_status = "connected" if login_status == "logged_in" else "login_required"
                error = None
            except Exception as exc:
                login_status = "error"
                connection_status = "not_connected"
                error = type(exc).__name__
        account = self.storage.update_by_id(
            "platform_accounts",
            account_id,
            {
                "login_status": login_status,
                "connection_status": connection_status,
                "last_login_check_at": utc_now(),
                "last_checked_at": utc_now(),
                "last_connection_error": error,
            },
            tenant_id=context.tenant_id,
        )
        return {"login_status": login_status, "connection_status": connection_status, "account": safe_account(account or {}), "runtime": safe_runtime(runtime)}

    def reconcile_runtime(self, context: TenantContext, runtime_id: str) -> dict[str, Any] | None:
        runtime = self.get_runtime_by_id(context, runtime_id)
        if not runtime:
            return None
        if runtime["status"] == "running" and runtime.get("browser_pid") and not _pid_exists(int(runtime["browser_pid"])):
            return self.storage.update_by_id("browser_runtimes", runtime_id, {"status": "stopped", "browser_pid": None}, tenant_id=context.tenant_id)
        if runtime["status"] == "running" and not _cdp_reachable(runtime["cdp_url"]):
            return self.storage.update_by_id("browser_runtimes", runtime_id, {"status": "unhealthy", "last_error": "CDP unreachable"}, tenant_id=context.tenant_id)
        return runtime

    def allocate_port(self) -> int:
        start = int(os.getenv("SAAS_BROWSER_CDP_PORT_START", "9300"))
        end = int(os.getenv("SAAS_BROWSER_CDP_PORT_END", "9399"))
        used = {int(row["cdp_port"]) for row in self.storage.list("browser_runtimes", limit=1000)}
        for port in range(start, end + 1):
            if port in used:
                continue
            if _port_free(port):
                return port
        raise BrowserRuntimeError("no_available_cdp_port", "no available CDP port")

    def profile_path(self, tenant_id: str, account_id: str) -> Path:
        return (self.profiles_root / f"tenant_{tenant_id}" / f"platform_account_{account_id}" / "profile").resolve()

    def _safe_profile_path(self, tenant_id: str, account_id: str, profile_path: str) -> Path:
        expected = self.profile_path(tenant_id, account_id).resolve()
        actual = Path(profile_path).resolve()
        if actual != expected:
            raise BrowserRuntimeError("invalid_profile_path", "profile path is not owned by this platform account")
        return actual

    def _mark_error(self, context: TenantContext, runtime: dict[str, Any], error_type: str, message: str) -> dict[str, Any]:
        self.storage.update_by_id("platform_accounts", runtime["platform_account_id"], {"last_connection_error": message}, tenant_id=context.tenant_id)
        return self.storage.update_by_id("browser_runtimes", runtime["id"], {"status": "error", "last_error": message}, tenant_id=context.tenant_id) or runtime


def safe_runtime(runtime: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": runtime.get("id"),
        "status": runtime.get("status"),
        "runtime_type": runtime.get("runtime_type"),
        "cdp_port": runtime.get("cdp_port"),
        "browser_pid": runtime.get("browser_pid"),
        "started_at": runtime.get("started_at"),
        "last_health_check_at": runtime.get("last_health_check_at"),
        "stopped_at": runtime.get("stopped_at"),
        "last_error": runtime.get("last_error"),
    }


def safe_account(account: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in account.items() if key not in {"config_json", "connection_metadata", "secret_ref"}}


async def _default_login_checker(cdp_url: str) -> str:
    with scoped_browser_cdp(cdp_url):
        result = await default_health_check()
    return str(result.get("login_state") or "unknown")


@contextmanager
def scoped_browser_cdp(cdp_url: str) -> Iterator[None]:
    keys = ["BROWSER_CDP", "FACEBOOK_CDP_URL"]
    previous = {key: os.environ.get(key) for key in keys}
    try:
        for key in keys:
            os.environ[key] = cdp_url
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _cdp_reachable(cdp_url: str) -> bool:
    try:
        with urlopen(f"{cdp_url.rstrip('/')}/json/version", timeout=2) as response:
            return response.status == 200
    except (OSError, URLError, TimeoutError):
        return False


def _wait_for_cdp(cdp_url: str, *, timeout_seconds: float) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if _cdp_reachable(cdp_url):
            return True
        time.sleep(0.25)
    return False


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def _find_chrome() -> str | None:
    candidates = [
        os.getenv("CHROME_PATH"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        shutil.which("chrome"),
        shutil.which("chrome.exe"),
        shutil.which("msedge"),
        shutil.which("msedge.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV"], capture_output=True, text=True)
        return str(pid) in result.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _terminate_process_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            os.kill(pid, 15)
            time.sleep(1)
            if _pid_exists(pid):
                os.kill(pid, 9)
        except OSError:
            pass
