from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


VALID_TARGET_POLICIES = {"owned_only", "allowlist", "discovery_only"}


@dataclass(frozen=True)
class TargetPolicyConfig:
    tenant_id: str | None = None
    policy: str = "discovery_only"
    owned_source_ids: frozenset[str] = field(default_factory=frozenset)
    allowed_source_urls: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if self.policy not in VALID_TARGET_POLICIES:
            raise ValueError(f"target policy must be one of {sorted(VALID_TARGET_POLICIES)}")

    @property
    def owned_source_count(self) -> int:
        return len(self.owned_source_ids)

    @property
    def allowlisted_source_count(self) -> int:
        return len(self.allowed_source_urls)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "policy": self.policy,
            "owned_source_ids": sorted(self.owned_source_ids),
            "allowed_source_urls": sorted(self.allowed_source_urls),
            "owned_source_count": self.owned_source_count,
            "allowlisted_source_count": self.allowlisted_source_count,
        }


def build_target_policy_config(
    *,
    tenant_id: str | None = None,
    policy: str | None = None,
    owned_source_ids: list[str] | tuple[str, ...] | set[str] | None = None,
    allowed_source_urls: list[str] | tuple[str, ...] | set[str] | None = None,
) -> TargetPolicyConfig:
    return TargetPolicyConfig(
        tenant_id=tenant_id,
        policy=policy or "discovery_only",
        owned_source_ids=frozenset(_normalize_source_id(item) for item in (owned_source_ids or []) if _normalize_source_id(item)),
        allowed_source_urls=frozenset(_normalize_url(item) for item in (allowed_source_urls or []) if _normalize_url(item)),
    )


def target_policy_from_env(env: dict[str, str] | None = None) -> TargetPolicyConfig:
    env = env or os.environ
    owned = _split_env_list(env.get("FACEBOOK_LEADS_OWNED_SOURCE_IDS"))
    allowed = _split_env_list(env.get("FACEBOOK_LEADS_ALLOWED_SOURCE_URLS"))
    owned.extend(_owned_sources_from_file(Path("config/facebook_owned_sources.json")))
    allowed.extend(_allowed_urls_from_file(Path("config/facebook_allowed_targets.json")))
    return build_target_policy_config(
        tenant_id=env.get("FACEBOOK_LEADS_TENANT_ID") or None,
        policy=env.get("FACEBOOK_LEADS_TARGET_POLICY") or "discovery_only",
        owned_source_ids=owned,
        allowed_source_urls=allowed,
    )


def evaluate_source_policy(lead: dict[str, Any], config: TargetPolicyConfig) -> dict[str, Any]:
    source_url = lead.get("source_content_url") or lead.get("source_final_url") or ""
    source_owner_name = lead.get("source_author_name")
    source_owner_url = lead.get("source_owner_url")
    source_owner_id = lead.get("source_owner_id") or _source_id_from_url(source_url) or _normalize_source_id(source_owner_name)
    source_owner_name_id = _normalize_source_id(source_owner_name)
    normalized_url = _normalize_url(source_url)
    url_allowed = _url_is_allowed(normalized_url, config.allowed_source_urls)
    owned = bool(
        (source_owner_id and source_owner_id in config.owned_source_ids)
        or (source_owner_name_id and source_owner_name_id in config.owned_source_ids)
    )

    if config.policy == "discovery_only":
        return _decision(source_owner_id, source_owner_name, source_owner_url, "unknown", False, "target_policy_discovery_only", config)
    if config.policy == "allowlist":
        if url_allowed:
            return _decision(source_owner_id, source_owner_name, source_owner_url, "allowlisted", True, "source_url_allowlisted", config)
        return _decision(source_owner_id, source_owner_name, source_owner_url, "third_party" if source_owner_id else "unknown", False, "source_not_allowlisted", config)
    if owned:
        return _decision(source_owner_id, source_owner_name, source_owner_url, "owned", True, "source_owner_configured", config)
    return _decision(source_owner_id, source_owner_name, source_owner_url, "third_party" if source_owner_id else "unknown", False, "source_not_owned", config)


def annotate_report_targets(report: dict[str, Any], config: TargetPolicyConfig) -> dict[str, Any]:
    counts = {"owned": 0, "allowlisted": 0, "third_party": 0, "unknown": 0}
    allowed_leads = 0
    blocked_leads = 0
    for content in report.get("contents") or []:
        content_policy = evaluate_source_policy(
            {
                "source_content_url": content.get("source_content_url"),
                "source_author_name": content.get("author_name"),
            },
            config,
        )
        content.update({key: content_policy[key] for key in _OWNERSHIP_FIELDS})
        counts[content_policy["ownership_status"]] = counts.get(content_policy["ownership_status"], 0) + 1
        for lead in content.get("leads") or []:
            policy = evaluate_source_policy({**lead, "source_author_name": lead.get("source_author_name") or content.get("author_name")}, config)
            lead.update(policy)
            if policy["reply_allowed"]:
                allowed_leads += 1
            else:
                blocked_leads += 1
    report["target_policy"] = {
        **config.to_dict(),
        "owned_content_count": counts.get("owned", 0),
        "allowlisted_content_count": counts.get("allowlisted", 0),
        "third_party_content_count": counts.get("third_party", 0),
        "unknown_content_count": counts.get("unknown", 0),
        "reply_allowed_lead_count": allowed_leads,
        "discovery_only_blocked_lead_count": blocked_leads,
    }
    return report


_OWNERSHIP_FIELDS = (
    "source_owner_id",
    "source_owner_name",
    "source_owner_url",
    "ownership_status",
    "reply_allowed",
    "ownership_reason",
    "target_policy",
    "tenant_id",
)


def _decision(
    source_owner_id: str | None,
    source_owner_name: str | None,
    source_owner_url: str | None,
    ownership_status: str,
    reply_allowed: bool,
    ownership_reason: str,
    config: TargetPolicyConfig,
) -> dict[str, Any]:
    return {
        "source_owner_id": source_owner_id,
        "source_owner_name": source_owner_name,
        "source_owner_url": source_owner_url,
        "ownership_status": ownership_status,
        "reply_allowed": bool(reply_allowed),
        "ownership_reason": ownership_reason,
        "target_policy": config.policy,
        "tenant_id": config.tenant_id,
    }


def _split_env_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.replace("\n", ",").split(",") if item.strip()]


def _owned_sources_from_file(path: Path) -> list[str]:
    payload = _read_json(path)
    return [str(item.get("source_id") or item.get("username") or item.get("name") or "") for item in payload.get("sources") or [] if isinstance(item, dict)]


def _allowed_urls_from_file(path: Path) -> list[str]:
    payload = _read_json(path)
    return [str(item) for item in payload.get("allowed_urls") or []]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _source_id_from_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in ("id", "profile_id", "owner_id"):
        if query.get(key):
            return _normalize_source_id(query[key][0])
    parts = [part for part in parsed.path.split("/") if part]
    if parts and parts[0] not in {"reel", "reels", "posts", "videos", "permalink.php", "watch"}:
        return _normalize_source_id(parts[0])
    return None


def _normalize_source_id(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _normalize_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    scheme = parsed.scheme.lower() or "https"
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{scheme}://{host}{path}{query}"


def _url_is_allowed(url: str, allowed_urls: frozenset[str]) -> bool:
    if not url:
        return False
    return any(url == allowed or url.startswith(allowed + "/") for allowed in allowed_urls)
