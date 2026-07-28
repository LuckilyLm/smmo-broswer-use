from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from src.facebook_leads.facebook.orchestrator import FacebookLeadsRunConfig, run_facebook_leads_job
from src.facebook_leads.facebook.target_policy import build_target_policy_config


@dataclass(frozen=True)
class PlatformRunContext:
    tenant_id: str
    platform_account_id: str
    runtime_id: str
    cdp_url: str
    profile_path: str
    target_policy: str
    send_disabled: bool = True


@dataclass(frozen=True)
class ProviderRunRequest:
    tenant_id: str
    campaign_id: str
    keyword: str
    target_policy: str
    max_contents: int
    max_comments: int
    min_confidence: float
    max_leads: int
    daily_limit: int
    llm_enabled: bool
    history_path: str
    runs_root: str
    custom_positive_keywords: tuple[str, ...] = ()
    run_context: PlatformRunContext | None = None


class BasePlatformProvider:
    platform = "unknown"
    enabled = False

    async def health_check(self, *_args, **_kwargs) -> dict[str, Any]:
        return {"platform": self.platform, "status": "not_implemented"}

    async def discover(self, *_args, **_kwargs) -> dict[str, Any]:
        return {"platform": self.platform, "status": "not_implemented"}

    async def scan(self, *_args, **_kwargs) -> dict[str, Any]:
        return {"platform": self.platform, "status": "not_implemented"}

    async def classify(self, *_args, **_kwargs) -> dict[str, Any]:
        return {"platform": self.platform, "status": "not_implemented"}

    async def plan_reply(self, *_args, **_kwargs) -> dict[str, Any]:
        return {"platform": self.platform, "status": "not_implemented"}

    async def execute_reply(self, *_args, **_kwargs) -> dict[str, Any]:
        return {"platform": self.platform, "status": "disabled"}

    async def run_campaign(self, request: ProviderRunRequest) -> dict[str, Any]:
        return {"platform": self.platform, "status": "not_implemented", "send_disabled": True, "request": request}


class FacebookProvider(BasePlatformProvider):
    platform = "facebook"
    enabled = True

    def __init__(self, runner: Callable[[FacebookLeadsRunConfig], Awaitable[dict[str, Any]]] | None = None) -> None:
        self.runner = runner or run_facebook_leads_job

    async def run_campaign(self, request: ProviderRunRequest) -> dict[str, Any]:
        config = FacebookLeadsRunConfig(
            cdp_url=request.run_context.cdp_url if request.run_context else None,
            keyword=request.keyword,
            max_contents=request.max_contents,
            max_comments=request.max_comments,
            llm_review=request.llm_enabled,
            max_leads=request.max_leads,
            min_confidence=request.min_confidence,
            daily_limit=request.daily_limit,
            history_path=request.history_path,
            runs_root=request.runs_root,
            target_policy=build_target_policy_config(policy=request.target_policy),
            custom_positive_keywords=request.custom_positive_keywords,
        )
        result = await self.runner(config)
        result["send_disabled"] = True
        return result


class InstagramProvider(BasePlatformProvider):
    platform = "instagram"


class XProvider(BasePlatformProvider):
    platform = "x"


class TikTokProvider(BasePlatformProvider):
    platform = "tiktok"


class OzonProvider(BasePlatformProvider):
    platform = "ozon"


def default_provider_registry(runner: Callable[[FacebookLeadsRunConfig], Awaitable[dict[str, Any]]] | None = None) -> dict[str, BasePlatformProvider]:
    return {
        "facebook": FacebookProvider(runner=runner),
        "instagram": InstagramProvider(),
        "x": XProvider(),
        "tiktok": TikTokProvider(),
        "ozon": OzonProvider(),
    }


def internal_runs_root(base: str | Path, tenant_id: str) -> str:
    return str(Path(base) / tenant_id / "runs")
