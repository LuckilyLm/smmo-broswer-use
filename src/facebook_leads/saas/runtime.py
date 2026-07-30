from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.error import URLError
from urllib.request import Request, urlopen
from browser_use.browser.browser import Browser, BrowserConfig
from sqlalchemy.exc import IntegrityError

from src.facebook_leads.facebook.orchestrator import default_health_check

from .db import utc_now
from .models import TenantContext
from .storage import SaaSStorage


LoginChecker = Callable[[str], Awaitable[str]]
logger = logging.getLogger(__name__)


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
        cdp_port_start: int = 9300,
        cdp_port_end: int = 9399,
        runtime_host: str = "local",
        cdp_base_url: str = "http://127.0.0.1",
        cdp_bind_address: str = "127.0.0.1",
        remote_control_url: str | None = None,
        browser_headless: bool = False,
        allow_chrome_discovery: bool = True,
    ) -> None:
        self.storage = storage
        self.profiles_root = Path(profiles_root)
        self.chrome_executable = chrome_executable or (_find_chrome() if allow_chrome_discovery else None)
        self.login_checker = login_checker or _default_login_checker
        self.cdp_port_start = cdp_port_start
        self.cdp_port_end = cdp_port_end
        self.runtime_host = runtime_host
        self.cdp_base_url = cdp_base_url.rstrip("/")
        self.cdp_bind_address = cdp_bind_address
        self.remote_control_url = remote_control_url.rstrip("/") if remote_control_url else None
        self.browser_headless = browser_headless
        self._sessions: dict[str, Browser] = {}
        self._browser_pids: dict[str, int] = {}
        self._cdp_proxies: dict[str, _CdpPortForwarder] = {}
        self._browser_loop = _BrowserUseRuntimeLoop()

    def get_runtime(self, context: TenantContext, account_id: str) -> dict[str, Any] | None:
        return self.storage.find_one("browser_runtimes", {"tenant_id": context.tenant_id, "platform_account_id": account_id})

    def get_runtime_by_id(self, context: TenantContext, runtime_id: str) -> dict[str, Any] | None:
        return self.storage.get_by_id("browser_runtimes", runtime_id, tenant_id=context.tenant_id)

    def create_runtime(self, context: TenantContext, account_id: str) -> dict[str, Any]:
        profile_path = self.profile_path(context.tenant_id, account_id)
        existing = self.get_runtime(context, account_id)
        if existing:
            if self._runtime_matches_current_backend(context.tenant_id, account_id, existing):
                return existing
            logger.warning(
                "discarding incompatible browser runtime",
                extra={
                    "tenant_id": context.tenant_id,
                    "platform_account_id": account_id,
                    "runtime_id": existing["id"],
                    "runtime_type": existing.get("runtime_type"),
                    "profile_path": existing.get("profile_path"),
                },
                )
            self.storage.delete_by_id("browser_runtimes", existing["id"], tenant_id=context.tenant_id)
            self.storage.update_by_id("platform_accounts", account_id, {"browser_runtime_id": None}, tenant_id=context.tenant_id)
        account = self.storage.get_by_id("platform_accounts", account_id, tenant_id=context.tenant_id)
        if not account:
            raise BrowserRuntimeError("platform_account_not_found", "platform account not found")
        if self.runtime_host == "local":
            profile_path.mkdir(parents=True, exist_ok=True)
        runtime = None
        for _attempt in range(5):
            cdp_port = self.allocate_port()
            try:
                runtime = self.storage.insert(
                    "browser_runtimes",
                    {
                        "tenant_id": context.tenant_id,
                        "platform_account_id": account_id,
                        "runtime_type": "browser_use_chromium_cdp",
                        "status": "stopped",
                        "profile_path": str(profile_path),
                        "cdp_port": cdp_port,
                        "cdp_url": self._cdp_url(cdp_port),
                    },
                )
                break
            except IntegrityError:
                existing = self.get_runtime(context, account_id)
                if existing:
                    return existing
        if runtime is None:
            raise BrowserRuntimeError("cdp_port_allocation_conflict", "could not reserve a CDP port after 5 attempts")
        self.storage.update_by_id("platform_accounts", account_id, {"browser_runtime_id": runtime["id"]}, tenant_id=context.tenant_id)
        return runtime

    def start_runtime(self, context: TenantContext, account_id: str, *, url: str = "https://www.facebook.com/") -> dict[str, Any]:
        runtime = self.create_runtime(context, account_id)
        if self.runtime_host == "remote":
            self._remote_control("POST", f"/internal/runtime/{context.tenant_id}/{account_id}/start", {"url": url})
            return self.get_runtime_by_id(context, runtime["id"]) or runtime
        self.reconcile_runtime(context, runtime["id"])
        runtime = self.get_runtime_by_id(context, runtime["id"]) or runtime
        if runtime["status"] == "running" and self.health_check(context, runtime["id"])["reachable"]:
            return self.get_runtime_by_id(context, runtime["id"]) or runtime
        Path(runtime["profile_path"]).mkdir(parents=True, exist_ok=True)
        self.storage.update_by_id("browser_runtimes", runtime["id"], {"status": "starting", "last_error": None}, tenant_id=context.tenant_id)
        try:
            self._run_async(self._start_browser_use(runtime, url=url))
        except Exception as exc:
            logger.exception(
                "browser-use runtime start failed",
                extra={"tenant_id": context.tenant_id, "platform_account_id": account_id, "runtime_id": runtime["id"], "error": type(exc).__name__},
            )
            return self._mark_error(context, runtime, "browser_use_start_failed", f"{type(exc).__name__}: {exc}")
        updated = self.storage.update_by_id(
            "browser_runtimes",
            runtime["id"],
            {"status": "running", "browser_pid": self._browser_pids.get(runtime["id"]) or os.getpid(), "started_at": utc_now(), "stopped_at": None, "last_error": None},
            tenant_id=context.tenant_id,
        )
        if not _wait_for_cdp(runtime["cdp_url"], timeout_seconds=8):
            self._close_session(runtime["id"])
            self.storage.update_by_id("browser_runtimes", runtime["id"], {"browser_pid": None}, tenant_id=context.tenant_id)
            return self._mark_error(context, runtime, "cdp_start_timeout", "browser-use started but CDP did not become reachable")
        return updated or runtime

    def stop_runtime(self, context: TenantContext, account_id: str) -> dict[str, Any]:
        runtime = self.get_runtime(context, account_id)
        if not runtime:
            raise BrowserRuntimeError("runtime_not_found", "runtime not found")
        if self.runtime_host == "remote":
            self._remote_control("POST", f"/internal/runtime/{context.tenant_id}/{account_id}/stop", {})
            return self.get_runtime_by_id(context, runtime["id"]) or runtime
        self._close_session(runtime["id"])
        return self.storage.update_by_id(
            "browser_runtimes",
            runtime["id"],
            {"status": "stopped", "browser_pid": None, "stopped_at": utc_now()},
            tenant_id=context.tenant_id,
        ) or runtime

    def restart_runtime(self, context: TenantContext, account_id: str) -> dict[str, Any]:
        if self.runtime_host == "remote":
            runtime = self.create_runtime(context, account_id)
            self._remote_control("POST", f"/internal/runtime/{context.tenant_id}/{account_id}/restart", {})
            return self.get_runtime_by_id(context, runtime["id"]) or runtime
        self.stop_runtime(context, account_id)
        return self.start_runtime(context, account_id)

    def reset_profile(self, context: TenantContext, account_id: str, *, confirm: str) -> dict[str, Any]:
        if confirm != "RESET PROFILE":
            raise BrowserRuntimeError("confirmation_required", "reset profile requires exact confirmation")
        if self.runtime_host == "remote":
            self._remote_control("POST", f"/internal/runtime/{context.tenant_id}/{account_id}/reset-profile", {"confirm": confirm})
            return self.get_runtime(context, account_id) or self.create_runtime(context, account_id)
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
        if self.runtime_host == "local" and not reachable and runtime.get("browser_pid") and not _pid_exists(int(runtime["browser_pid"])):
            status = "stopped"
        updated = self.storage.update_by_id(
            "browser_runtimes",
            runtime["id"],
            {"status": status, "last_health_check_at": utc_now(), "last_error": None if reachable else "CDP unreachable"},
            tenant_id=context.tenant_id,
        )
        return {"reachable": reachable, "status": status, "runtime": safe_runtime(updated or runtime)}

    async def check_login(self, context: TenantContext, account_id: str) -> dict[str, Any]:
        if self.runtime_host == "remote":
            self._remote_control("POST", f"/internal/runtime/{context.tenant_id}/{account_id}/check-login", {})
            account = self.storage.get_by_id("platform_accounts", account_id, tenant_id=context.tenant_id) or {}
            runtime = self.get_runtime(context, account_id) or {}
            return {
                "login_status": account.get("login_status") or "unknown",
                "connection_status": account.get("connection_status") or "not_connected",
                "account": safe_account(account),
                "runtime": safe_runtime(runtime),
            }
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
        if login_status == "logged_in":
            snapshot = await self._persist_login_state_snapshot(runtime)
            if snapshot:
                metadata = dict((account or {}).get("connection_metadata") or {})
                metadata["login_state_snapshot"] = snapshot
                account = self.storage.update_by_id(
                    "platform_accounts",
                    account_id,
                    {"connection_metadata": metadata},
                    tenant_id=context.tenant_id,
                ) or account
        return {"login_status": login_status, "connection_status": connection_status, "account": safe_account(account or {}), "runtime": safe_runtime(runtime)}

    def reconcile_runtime(self, context: TenantContext, runtime_id: str) -> dict[str, Any] | None:
        runtime = self.get_runtime_by_id(context, runtime_id)
        if not runtime:
            return None
        if runtime["status"] == "running" and not _cdp_reachable(runtime["cdp_url"]):
            return self.storage.update_by_id("browser_runtimes", runtime_id, {"status": "unhealthy", "last_error": "CDP unreachable"}, tenant_id=context.tenant_id)
        return runtime

    def reconcile_all(self) -> int:
        reconciled = 0
        for runtime in self.storage.list("browser_runtimes", limit=10000):
            context = TenantContext(tenant_id=runtime["tenant_id"], user_id="startup", role="system")
            before = runtime.get("status")
            after = self.reconcile_runtime(context, runtime["id"])
            if after and after.get("status") != before:
                reconciled += 1
        return reconciled

    def allocate_port(self) -> int:
        used = {int(row["cdp_port"]) for row in self.storage.list("browser_runtimes", limit=1000)}
        for port in range(self.cdp_port_start, self.cdp_port_end + 1):
            if port in used:
                continue
            if self.runtime_host != "local" or _port_free(port):
                return port
        raise BrowserRuntimeError("no_available_cdp_port", "no available CDP port")

    def _require_local_runtime(self) -> None:
        if self.runtime_host != "local":
            raise BrowserRuntimeError("runtime_host_not_implemented", "browser-use local runtime host is required")

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

    def _runtime_matches_current_backend(self, tenant_id: str, account_id: str, runtime: dict[str, Any]) -> bool:
        cdp_port = runtime.get("cdp_port")
        return (
            runtime.get("runtime_type") == "browser_use_chromium_cdp"
            and Path(str(runtime.get("profile_path") or "")).resolve() == self.profile_path(tenant_id, account_id)
            and (cdp_port is None or str(runtime.get("cdp_url") or "") == self._cdp_url(int(cdp_port)))
        )

    async def _start_browser_use(self, runtime: dict[str, Any], *, url: str) -> None:
        existing = self._sessions.pop(runtime["id"], None)
        if existing:
            await existing.close()
        old_pid = self._browser_pids.pop(runtime["id"], None)
        if old_pid:
            _terminate_process_tree(old_pid)
        profile_path = Path(runtime["profile_path"])
        profile_path.mkdir(parents=True, exist_ok=True)
        self._remove_stale_profile_locks(profile_path)
        extra_args = [
            "--no-first-run",
            "--no-default-browser-check",
            "--window-size=1366,900",
            "--window-position=0,0",
            "--ozone-platform=x11",
            "--remote-allow-origins=*",
        ]
        if self.chrome_executable:
            stderr_path = Path("/tmp") / f"saas-chromium-{runtime['id']}.err"
            stdout_path = Path("/tmp") / f"saas-chromium-{runtime['id']}.out"
            launch_args = [
                self.chrome_executable,
                f"--remote-debugging-port={int(runtime['cdp_port'])}",
                f"--remote-debugging-address={self.cdp_bind_address}",
                f"--user-data-dir={profile_path}",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                *extra_args,
            ]
            if self.browser_headless:
                launch_args.extend(["--headless=new", "--disable-gpu"])
            env = os.environ.copy()
            if not self.browser_headless:
                env.setdefault("DISPLAY", ":99")
            logger.info(
                "launching chromium for browser-use runtime",
                extra={
                    "tenant_id": runtime.get("tenant_id"),
                    "platform_account_id": runtime.get("platform_account_id"),
                    "runtime_id": runtime["id"],
                    "cdp_port": runtime.get("cdp_port"),
                    "profile_path": str(profile_path),
                    "display": env.get("DISPLAY"),
                    "stderr_path": str(stderr_path),
                },
            )
            with stderr_path.open("ab") as stderr_file, stdout_path.open("ab") as stdout_file:
                process = await asyncio.create_subprocess_exec(
                    *launch_args,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    env=env,
                )
            self._browser_pids[runtime["id"]] = process.pid
            local_cdp_url = self._local_cdp_url(int(runtime["cdp_port"]))
            if not await asyncio.to_thread(_wait_for_cdp, local_cdp_url, timeout_seconds=10):
                _terminate_process_tree(process.pid)
                self._browser_pids.pop(runtime["id"], None)
                stderr_tail = _tail_file(stderr_path, max_bytes=4000)
                raise BrowserRuntimeError("cdp_start_timeout", f"Chromium started but CDP did not become reachable; stderr={stderr_tail}")
            self._ensure_cdp_proxy(runtime)
            if not await asyncio.to_thread(_wait_for_cdp, runtime["cdp_url"], timeout_seconds=5):
                self._close_cdp_proxy(runtime["id"])
                _terminate_process_tree(process.pid)
                self._browser_pids.pop(runtime["id"], None)
                raise BrowserRuntimeError("cdp_proxy_unreachable", f"CDP proxy did not become reachable at {runtime['cdp_url']}")
            config = BrowserConfig(cdp_url=local_cdp_url, headless=self.browser_headless)
        else:
            config = BrowserConfig(
                chrome_remote_debugging_port=int(runtime["cdp_port"]),
                extra_browser_args=extra_args,
                headless=self.browser_headless,
            )
        browser = Browser(config=config)
        playwright_browser = await browser.get_playwright_browser()
        await self._restore_login_state_snapshot(runtime, playwright_browser)
        if url:
            page = await playwright_browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        self._sessions[runtime["id"]] = browser

    def _close_session(self, runtime_id: str) -> None:
        self._close_cdp_proxy(runtime_id)
        browser = self._sessions.pop(runtime_id, None)
        if browser is not None:
            self._run_async(browser.close())
        pid = self._browser_pids.pop(runtime_id, None)
        if pid:
            _terminate_process_tree(pid)

    def _run_async(self, awaitable: Awaitable[Any]) -> Any:
        return self._browser_loop.run(awaitable)

    def _remove_stale_profile_locks(self, profile_path: Path) -> None:
        for directory in [profile_path, profile_path / "Default"]:
            for lock_path in directory.glob("Singleton*"):
                try:
                    lock_path.unlink()
                except (FileNotFoundError, PermissionError, OSError) as exc:
                    logger.warning(
                        "failed to remove stale chromium profile lock",
                        extra={"profile_path": str(profile_path), "lock_path": str(lock_path), "error": type(exc).__name__},
                    )

    def _login_state_snapshot_path(self, runtime: dict[str, Any]) -> Path:
        return Path(runtime["profile_path"]) / "saas_login_state.json"

    def _cdp_url(self, port: int) -> str:
        return f"{self.cdp_base_url}:{int(port)}"

    def _local_cdp_url(self, port: int) -> str:
        return f"http://127.0.0.1:{int(port)}"

    def _ensure_cdp_proxy(self, runtime: dict[str, Any]) -> None:
        if self._local_cdp_url(int(runtime["cdp_port"])) == runtime["cdp_url"]:
            return
        runtime_id = runtime["id"]
        self._close_cdp_proxy(runtime_id)
        try:
            bind_host = socket.gethostbyname(socket.gethostname())
        except OSError as exc:
            raise BrowserRuntimeError("cdp_proxy_bind_unavailable", f"could not resolve container bind address: {exc}") from exc
        proxy = _CdpPortForwarder(bind_host=bind_host, port=int(runtime["cdp_port"]))
        proxy.start()
        self._cdp_proxies[runtime_id] = proxy

    def _close_cdp_proxy(self, runtime_id: str) -> None:
        proxy = self._cdp_proxies.pop(runtime_id, None)
        if proxy:
            proxy.close()

    def _remote_control(self, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.remote_control_url:
            raise BrowserRuntimeError("runtime_control_unavailable", "browser runtime control URL is not configured")
        data = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.remote_control_url}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except Exception as exc:
            raise BrowserRuntimeError("runtime_control_failed", f"{type(exc).__name__}: {exc}") from exc

    async def _persist_login_state_snapshot(self, runtime: dict[str, Any]) -> dict[str, Any] | None:
        path = self._login_state_snapshot_path(runtime)
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.connect_over_cdp(runtime["cdp_url"])
                context = browser.contexts[0] if browser.contexts else await browser.new_context()
                state = await context.storage_state()
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
                try:
                    tmp.chmod(0o600)
                except OSError:
                    pass
                tmp.replace(path)
            snapshot = {
                "path": str(path),
                "updated_at": utc_now().isoformat(),
                "cookie_count": len(state.get("cookies") or []),
                "origin_count": len(state.get("origins") or []),
            }
            logger.info(
                "browser login state snapshot saved",
                extra={
                    "tenant_id": runtime.get("tenant_id"),
                    "platform_account_id": runtime.get("platform_account_id"),
                    "runtime_id": runtime.get("id"),
                    "cookie_count": snapshot["cookie_count"],
                    "origin_count": snapshot["origin_count"],
                },
            )
            return snapshot
        except Exception as exc:
            logger.warning(
                "browser login state snapshot failed",
                extra={
                    "tenant_id": runtime.get("tenant_id"),
                    "platform_account_id": runtime.get("platform_account_id"),
                    "runtime_id": runtime.get("id"),
                    "error": type(exc).__name__,
                },
            )
            return None

    async def _restore_login_state_snapshot(self, runtime: dict[str, Any], playwright_browser: Any) -> None:
        path = self._login_state_snapshot_path(runtime)
        if not path.exists():
            return
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            cookies = state.get("cookies") or []
            if not cookies:
                return
            context = playwright_browser.contexts[0] if playwright_browser.contexts else await playwright_browser.new_context()
            await context.add_cookies(cookies)
            logger.info(
                "browser login state snapshot restored",
                extra={
                    "tenant_id": runtime.get("tenant_id"),
                    "platform_account_id": runtime.get("platform_account_id"),
                    "runtime_id": runtime.get("id"),
                    "cookie_count": len(cookies),
                },
            )
        except Exception as exc:
            logger.warning(
                "browser login state snapshot restore failed",
                extra={
                    "tenant_id": runtime.get("tenant_id"),
                    "platform_account_id": runtime.get("platform_account_id"),
                    "runtime_id": runtime.get("id"),
                    "error": type(exc).__name__,
                },
            )


class _BrowserUseRuntimeLoop:
    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_forever, name="browser-use-runtime-loop", daemon=True)
        self._thread.start()

    def run(self, awaitable: Awaitable[Any]) -> Any:
        future = asyncio.run_coroutine_threadsafe(awaitable, self._loop)
        return future.result()

    def _run_forever(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()


class _CdpPortForwarder:
    def __init__(self, *, bind_host: str, port: int, target_host: str = "127.0.0.1") -> None:
        self.bind_host = bind_host
        self.port = port
        self.target_host = target_host
        self._closed = threading.Event()
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.bind_host, self.port))
        server.listen(32)
        server.settimeout(0.5)
        self._server = server
        self._thread = threading.Thread(target=self._serve, name=f"cdp-proxy-{self.port}", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._closed.set()
        if self._server:
            try:
                self._server.close()
            except OSError:
                pass
        if self._thread:
            self._thread.join(timeout=1)

    def _serve(self) -> None:
        assert self._server is not None
        while not self._closed.is_set():
            try:
                client, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle_client, args=(client,), daemon=True).start()

    def _handle_client(self, client: socket.socket) -> None:
        try:
            upstream = socket.create_connection((self.target_host, self.port), timeout=5)
        except OSError:
            client.close()
            return
        public_host = {"value": f"{self.bind_host}:{self.port}"}
        threading.Thread(target=self._pipe_client_to_upstream, args=(client, upstream, self.port, public_host), daemon=True).start()
        threading.Thread(target=self._pipe_upstream_to_client, args=(upstream, client, self.port, public_host), daemon=True).start()

    @staticmethod
    def _pipe_client_to_upstream(source: socket.socket, target: socket.socket, port: int, public_host: dict[str, str]) -> None:
        first_chunk = True
        buffered = b""
        try:
            while True:
                data = source.recv(65536)
                if not data:
                    break
                if first_chunk:
                    buffered += data
                    if b"\r\n\r\n" not in buffered and len(buffered) < 131072:
                        continue
                    host = _request_host_header(buffered)
                    if host:
                        public_host.setdefault("requested_host", host)
                    data = _rewrite_cdp_request_headers(buffered, f"127.0.0.1:{port}")
                    buffered = b""
                    first_chunk = False
                target.sendall(data)
        except OSError:
            pass
        finally:
            for sock in (source, target):
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    sock.close()
                except OSError:
                    pass

    @staticmethod
    def _pipe_upstream_to_client(source: socket.socket, target: socket.socket, port: int, public_host: dict[str, str]) -> None:
        first_chunk = True
        try:
            while True:
                data = source.recv(65536)
                if not data:
                    break
                if first_chunk:
                    data = _rewrite_cdp_response(data, port, public_host.get("value") or f"127.0.0.1:{port}")
                    first_chunk = False
                target.sendall(data)
        except OSError:
            pass
        finally:
            for sock in (source, target):
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    sock.close()
                except OSError:
                    pass


def _request_host_header(data: bytes) -> str | None:
    header_end = data.find(b"\r\n\r\n")
    if header_end == -1:
        return None
    for line in data[:header_end].split(b"\r\n"):
        if line.lower().startswith(b"host:"):
            try:
                return line.split(b":", 1)[1].strip().decode("ascii")
            except UnicodeDecodeError:
                return None
    return None


def _rewrite_cdp_response(data: bytes, port: int, public_host: str) -> bytes:
    header_end = data.find(b"\r\n\r\n")
    if header_end == -1:
        return data.replace(f"ws://127.0.0.1:{port}".encode("ascii"), f"ws://{public_host}".encode("ascii"))
    headers = data[:header_end].split(b"\r\n")
    body = data[header_end + 4 :]
    old = f"ws://127.0.0.1:{port}".encode("ascii")
    new = f"ws://{public_host}".encode("ascii")
    if old not in body:
        return data
    body = body.replace(old, new)
    rewritten: list[bytes] = []
    for line in headers:
        if line.lower().startswith(b"content-length:"):
            rewritten.append(f"Content-Length: {len(body)}".encode("ascii"))
        else:
            rewritten.append(line)
    return b"\r\n".join(rewritten) + b"\r\n\r\n" + body


def _rewrite_cdp_request_headers(data: bytes, host: str) -> bytes:
    header_end = data.find(b"\r\n\r\n")
    if header_end == -1:
        return data
    headers = data[:header_end].split(b"\r\n")
    rewritten: list[bytes] = []
    replaced = False
    for line in headers:
        if line.lower().startswith(b"host:"):
            rewritten.append(f"Host: {host}".encode("ascii"))
            replaced = True
        elif line.lower().startswith(b"origin:"):
            rewritten.append(f"Origin: http://{host}".encode("ascii"))
        else:
            rewritten.append(line)
    if not replaced:
        rewritten.insert(1, f"Host: {host}".encode("ascii"))
    return b"\r\n".join(rewritten) + data[header_end:]


def _rewrite_host_header(data: bytes, host: str) -> bytes:
    return _rewrite_cdp_request_headers(data, host)


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
    result = await default_health_check(cdp_url=cdp_url)
    return str(result.get("login_state") or "unknown")


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


def _tail_file(path: Path, *, max_bytes: int) -> str:
    try:
        with path.open("rb") as file:
            file.seek(0, os.SEEK_END)
            size = file.tell()
            file.seek(max(0, size - max_bytes), os.SEEK_SET)
            return file.read().decode("utf-8", errors="replace").strip()
    except OSError:
        return ""


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def _find_chrome() -> str | None:
    candidates = [
        os.getenv("CHROME_PATH"),
        shutil.which("chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("google-chrome"),
    ]
    candidates.extend(str(path) for path in Path("/ms-browsers").glob("chromium-*/chrome-linux64/chrome"))
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _terminate_process_tree(pid: int) -> None:
    try:
        os.kill(pid, 15)
        time.sleep(1)
        if _pid_exists(pid):
            os.kill(pid, 9)
    except OSError:
        pass
