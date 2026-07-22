from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    user_id: str
    role: str = "member"


PLATFORMS = {"facebook", "instagram", "x", "tiktok", "ozon"}
PLACEHOLDER_PLATFORMS = {"instagram", "x", "tiktok", "ozon"}
TARGET_POLICIES = {"owned_only", "allowlist", "discovery_only"}
