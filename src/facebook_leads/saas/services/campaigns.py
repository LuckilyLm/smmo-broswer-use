from __future__ import annotations

from typing import Any


class CampaignService:
    @staticmethod
    def config_snapshot(campaign: dict[str, Any], keywords: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "platform_account_id": campaign["platform_account_id"],
            "target_policy": campaign["target_policy"],
            "max_contents": int(campaign["max_contents"]),
            "max_comments": int(campaign["max_comments"]),
            "min_confidence": float(campaign["min_confidence"]),
            "max_leads": int(campaign["max_leads"]),
            "daily_limit": int(campaign["daily_limit"]),
            "llm_enabled": bool(campaign["llm_enabled"]),
            "keywords": [{"id": row["id"], "keyword": row["keyword"]} for row in keywords],
        }
