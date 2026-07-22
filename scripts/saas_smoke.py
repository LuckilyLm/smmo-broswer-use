from __future__ import annotations

import asyncio
import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.facebook_leads.facebook.orchestrator import FacebookLeadsRunConfig
from src.facebook_leads.saas.providers import FacebookProvider, InstagramProvider, OzonProvider, TikTokProvider, XProvider
from src.facebook_leads.saas.runtime import safe_runtime
from src.facebook_leads.saas.seed import seed_demo_data
from src.facebook_leads.saas.service import SaaSService
from src.facebook_leads.saas.storage import SaaSStorage
from src.facebook_leads.saas.worker import ExecutionWorker


async def fake_runner(config: FacebookLeadsRunConfig) -> dict:
    run_dir = Path(config.runs_root) / "smoke_run"
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / "lead_report_enriched.json"
    report_path.write_text(
        json.dumps(
            {
                "contents": [
                    {
                        "leads": [
                            {
                                "comment_id": "smoke-comment-1",
                                "comment_fingerprint": "smoke-fp-1",
                                "author_name": "Smoke Buyer",
                                "comment_text": "Price please for massage chair",
                                "source_content_url": "https://www.facebook.com/reel/smoke",
                                "direct_comment_url": "https://www.facebook.com/reel/smoke?comment_id=smoke-comment-1",
                                "rule_intent_level": "high",
                                "reply_allowed": True,
                                "ownership_status": "owned",
                                "llm_review": {
                                    "confidence": 0.95,
                                    "intent_level": "high",
                                    "intent_types": ["explicit_price_query"],
                                    "suggested_reply": "Thanks, our team can share details.",
                                },
                            }
                        ]
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return {
        "run_id": "smoke_run",
        "status": "completed",
        "stage": "completed",
        "started_at": "2026-07-22T00:00:00+00:00",
        "finished_at": "2026-07-22T00:00:01+00:00",
        "elapsed_ms": 1000,
        "scan_summary": {"scanned_contents": 1, "scanned_comments": 1, "lead_candidates": 1},
        "batch_plan_summary": {"eligible_count": 1, "selected_count": 1},
        "llm_review_summary": {"model": "smoke-model", "prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12, "call_count": 1},
        "paths": {"lead_report_enriched_json": str(report_path)},
        "send_disabled": True,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run a safe SaaS smoke test with a fixture Facebook provider.")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--sqlite-temp", action="store_true", help="Use a temporary SQLite database for unit-style smoke.")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        root = Path(temp_dir)
        providers = {
            "facebook": FacebookProvider(runner=fake_runner),
            "instagram": InstagramProvider(),
            "x": XProvider(),
            "tiktok": TikTokProvider(),
            "ozon": OzonProvider(),
        }
        database = root / "saas.sqlite" if args.sqlite_temp else args.database_url
        storage = SaaSStorage(database)
        service = SaaSService(storage, providers=providers, artifacts_root=root / "artifacts", runtime_registry=FixtureRuntimeRegistry(storage, root))
        seed_demo_data(service.storage, password="pass123456")
        session = service.login("admin@example.com", "pass123456")
        context = service.context_from_token(session["access_token"])
        account = service.list_platform_accounts(context)[0]
        service.runtime_registry.provision_logged_in(context, account["id"])
        dashboard_before = service.dashboard_summary(context)
        campaign = service.list_campaigns(context)[0]
        run = await service.run_campaign(context, campaign["id"])
        await ExecutionWorker(service, worker_id="saas-smoke").tick()
        execution = service.get_execution(context, run["execution_id"])
        leads = service.list_leads(context, {"keyword": "price"})
        tokens = service.token_usage_summary(context)
        print(f"login=ok")
        print(f"dashboard_before_active_campaigns={dashboard_before['active_campaigns']}")
        print(f"campaign_run_status={execution['status']}")
        print(f"send_disabled={str(run['send_disabled']).lower()}")
        print(f"lead_count={len(leads['items'])}")
        print(f"tokens_this_month={tokens['this_month']}")
        print("real_facebook_reply_executed=false")


class FixtureRuntimeRegistry:
    def __init__(self, storage: SaaSStorage, root: Path) -> None:
        self.storage = storage
        self.root = root
        self.next_port = 9500

    def provision_logged_in(self, context, account_id: str):
        runtime = self.storage.find_one("browser_runtimes", {"tenant_id": context.tenant_id, "platform_account_id": account_id})
        if not runtime:
            runtime = self.storage.insert(
                "browser_runtimes",
                {
                    "tenant_id": context.tenant_id,
                    "platform_account_id": account_id,
                    "runtime_type": "local_chrome_cdp",
                    "status": "running",
                    "profile_path": str(self.root / "profiles" / context.tenant_id / account_id / "profile"),
                    "cdp_port": self.next_port,
                    "cdp_url": f"http://127.0.0.1:{self.next_port}",
                    "browser_pid": self.next_port + 1000,
                },
            )
            self.next_port += 1
        self.storage.update_by_id("platform_accounts", account_id, {"browser_runtime_id": runtime["id"], "connection_status": "connected", "login_status": "logged_in"}, tenant_id=context.tenant_id)
        return runtime

    def get_runtime(self, context, account_id: str):
        return self.storage.find_one("browser_runtimes", {"tenant_id": context.tenant_id, "platform_account_id": account_id})

    def health_check(self, context, runtime_id: str):
        runtime = self.storage.get_by_id("browser_runtimes", runtime_id, tenant_id=context.tenant_id)
        return {"reachable": True, "status": "running", "runtime": safe_runtime(runtime)}

    def start_runtime(self, context, account_id: str, **_kwargs):
        return self.get_runtime(context, account_id) or self.provision_logged_in(context, account_id)


if __name__ == "__main__":
    asyncio.run(main())
