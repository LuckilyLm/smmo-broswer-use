from __future__ import annotations

import hashlib
import os
from datetime import timedelta
from typing import Any

from .db import utc_now
from .models import TenantContext
from .service import SaaSService
from .storage import SaaSStorage

DEMO_SLUG = "demo"
DEMO_ADMIN_EMAIL = "demo.admin@example.com"
DEMO_TABLES = (
    "tenant_users",
    "tenant_invitations",
    "platform_accounts",
    "campaigns",
    "campaign_keywords",
    "reply_templates",
    "reply_match_rules",
    "leads",
    "executions",
    "reply_plans",
    "reply_candidates",
    "reply_records",
    "token_usage",
    "notifications",
    "audit_logs",
)


def seed_demo_data(storage: SaaSStorage, *, password: str | None = None) -> dict[str, Any]:
    """Create or refresh the isolated demo tenant without deleting any rows.

    The seed deliberately leaves all execution sends disabled and all illustrative
    replies either historical or awaiting manual approval.
    """
    password = password or os.getenv("FACEBOOK_LEADS_DEMO_PASSWORD")
    if not password:
        raise ValueError("FACEBOOK_LEADS_DEMO_PASSWORD is required for demo seed")
    if len(password) < 8:
        raise ValueError("demo password must be at least 8 characters")

    service = SaaSService(storage)
    now = utc_now()
    tenant = storage.find_one("tenants", {"slug": DEMO_SLUG})
    if tenant is None:
        tenant = service.create_tenant(
            "Acme Wellness Demo", DEMO_SLUG, plan_code="pro", timezone="Asia/Shanghai",
            default_contact_text="Book a complimentary showroom consultation.",
            tenant_reply_enabled=False,
        )
    else:
        tenant = storage.update_by_id(
            "tenants", tenant["id"],
            {"name": "Acme Wellness Demo", "status": "active", "tenant_reply_enabled": False},
        ) or tenant

    admin = _ensure_user(service, storage, DEMO_ADMIN_EMAIL, password, "Maya Chen")
    member = _ensure_user(service, storage, "demo.member@example.com", password, "Jordan Lee")
    admin_membership = _ensure(storage, "tenant_users", {"tenant_id": tenant["id"], "user_id": admin["id"]}, {"role": "admin"})
    member_membership = _ensure(storage, "tenant_users", {"tenant_id": tenant["id"], "user_id": member["id"]}, {"role": "member"})
    context = TenantContext(tenant_id=tenant["id"], user_id=admin["id"], role="admin")

    invitation = _ensure(
        storage, "tenant_invitations",
        {"tenant_id": tenant["id"], "email": "demo.invited@example.com"},
        {"role": "viewer", "token_hash": hashlib.sha256(b"facebook-leads-demo-invitation").hexdigest(),
         "status": "pending", "expires_at": now + timedelta(days=30), "invited_by_user_id": admin["id"]},
    )
    account = _ensure(
        storage, "platform_accounts", {"tenant_id": tenant["id"], "display_name": "Acme Wellness Facebook"},
        {"platform": "facebook", "external_account_id": "demo-acme-wellness", "external_account_name": "Acme Wellness",
         "connection_status": "demo", "login_status": "demo", "config_json": {"demo": True},
         "connection_metadata": {"mode": "read_only_demo"}},
    )

    campaign_specs = [
        ("Massage Chair Buyer Intent", "active", "High-intent product discovery", ["massage chair price", "best massage chair", "zero gravity chair"]),
        ("Corporate Wellness Research", "paused", "Paused B2B research campaign", ["office wellness room", "employee massage chair"]),
        ("Holiday Showroom Launch", "draft", "Draft launch campaign", ["holiday massage chair offer"]),
    ]
    campaigns: dict[str, dict[str, Any]] = {}
    for name, status, description, keywords in campaign_specs:
        campaign = _ensure(
            storage, "campaigns", {"tenant_id": tenant["id"], "name": name},
            {"description": description, "platform_account_id": account["id"], "status": status,
             "target_policy": "discovery_only", "max_contents": 5, "max_comments": 80, "max_leads": 10,
             "min_confidence": 0.85, "llm_enabled": True, "lead_detection_mode": "hybrid",
             "reply_mode": "manual_approval", "positive_keywords_json": ["price", "recommend", "buy"],
             "negative_keywords_json": ["repair", "job"], "reply_daily_limit": 10},
        )
        campaigns[status] = campaign
        for priority, keyword in enumerate(keywords, 1):
            _ensure(storage, "campaign_keywords", {"campaign_id": campaign["id"], "keyword": keyword},
                    {"tenant_id": tenant["id"], "enabled": True, "priority": priority})

    active = campaigns["active"]
    template = _ensure(
        storage, "reply_templates", {"tenant_id": tenant["id"], "name": "Showroom consultation"},
        {"description": "Helpful, non-automated demo response", "content": "Hi {author_name}, thanks for your interest. Our team can help compare options—would you like showroom details?",
         "platform": "facebook", "language": "en", "enabled": True, "priority": 10, "is_default": True,
         "created_by": admin["id"]},
    )
    rule = _ensure(
        storage, "reply_match_rules", {"tenant_id": tenant["id"], "name": "Purchase questions"},
        {"campaign_id": active["id"], "reply_template_id": template["id"], "enabled": True, "priority": 10,
         "contains_any_json": ["price", "recommend", "where can I buy"], "contains_all_json": [],
         "author_exclude_json": ["Acme Wellness"], "comment_language": "en", "minimum_length": 8,
         "created_by": admin["id"]},
    )
    storage.update_by_id("campaigns", active["id"], {"default_reply_template_id": template["id"]}, tenant_id=tenant["id"])

    executions = {
        "completed": _ensure_execution(storage, tenant["id"], active["id"], "demo-run-completed", "completed", now - timedelta(days=2), 100, None),
        "partial": _ensure_execution(storage, tenant["id"], active["id"], "demo-run-partial", "partial", now - timedelta(hours=8), 100, "One keyword timed out"),
        "failed": _ensure_execution(storage, tenant["id"], campaigns["paused"]["id"], "demo-run-failed", "failed", now - timedelta(days=1), 35, "Demo browser session expired"),
    }

    lead_specs = [
        ("demo-comment-001", "Alex Rivera", "What is the price and which model is best for a small apartment?", "high", "new", True),
        ("demo-comment-002", "Priya Shah", "Can you recommend a chair for an office wellness room?", "high", "qualified", True),
        ("demo-comment-003", "Sam Wilson", "Do you have a showroom near downtown?", "medium", "contacted", True),
        ("demo-comment-004", "Taylor Kim", "Great photo!", "low", "invalid", False),
    ]
    leads = []
    for index, (comment_id, author, text, intent, status, allowed) in enumerate(lead_specs):
        lead = _ensure(
            storage, "leads", {"tenant_id": tenant["id"], "campaign_id": active["id"], "comment_fingerprint": f"demo:{comment_id}"},
            {"platform_account_id": account["id"], "platform": "facebook", "external_lead_id": f"demo-lead-{index + 1}",
             "comment_id": comment_id, "author_name": author, "comment_text": text,
             "source_content_url": f"https://example.invalid/demo/posts/{index + 1}",
             "direct_comment_url": f"https://example.invalid/demo/comments/{comment_id}", "rule_intent_level": intent,
             "final_intent_level": intent, "llm_confidence": 0.96 - index * 0.08,
             "llm_intent_types": ["purchase_interest"] if allowed else ["noise"], "llm_reason": "Illustrative demo classification",
             "suggested_reply": "Thanks for reaching out. Our team can help with options.", "ownership_status": "unverified",
             "reply_allowed": allowed, "status": status, "assigned_user_id": member["id"] if index in {1, 2} else None,
             "invalid_reason": "No purchase intent" if not allowed else None, "matched_search_keywords": ["massage chair price"],
             "discovered_at": now - timedelta(hours=12 + index), "first_discovered_at": now - timedelta(hours=12 + index),
             "last_discovered_at": now - timedelta(hours=4 + index)},
        )
        leads.append(lead)

    plan = _ensure(
        storage, "reply_plans", {"tenant_id": tenant["id"], "execution_id": executions["completed"]["id"]},
        {"campaign_id": active["id"], "platform_account_id": account["id"], "status": "pending_approval",
         "reply_mode": "manual_approval", "total_candidates": 3, "approved_count": 1, "sent_count": 0,
         "failed_count": 0, "created_by": admin["id"]},
    )
    candidate_specs = [(0, "pending_approval"), (1, "approved"), (2, "blocked")]
    candidates = []
    for lead_index, status in candidate_specs:
        lead = leads[lead_index]
        candidate = _ensure(
            storage, "reply_candidates", {"tenant_id": tenant["id"], "campaign_id": active["id"], "idempotency_key": f"demo-reply-{lead_index + 1}"},
            {"execution_id": executions["completed"]["id"], "reply_plan_id": plan["id"], "platform_account_id": account["id"],
             "platform": "facebook", "comment_id": lead["comment_id"], "comment_fingerprint": lead["comment_fingerprint"],
             "author_name": lead["author_name"], "comment_text": lead["comment_text"], "source_content_url": lead["source_content_url"],
             "direct_comment_url": lead["direct_comment_url"], "matched_rule_id": rule["id"], "matched_rule_name": rule["name"],
             "reply_template_id": template["id"], "rendered_reply_text": f"Hi {lead['author_name']}, thanks for your interest. Our demo team can help compare options.",
             "status": status, "blocked_reason": "demo_send_disabled" if status == "blocked" else None,
             "approved_by": admin["id"] if status != "pending_approval" else None,
             "approved_at": now - timedelta(days=1) if status != "pending_approval" else None,
             "sent_at": None},
        )
        candidates.append(candidate)
    record = _ensure(
        storage, "reply_records", {"tenant_id": tenant["id"], "idempotency_key": "demo-reply-record-1"},
        {"reply_candidate_id": candidates[2]["id"], "reply_plan_id": plan["id"], "campaign_id": active["id"],
         "platform_account_id": account["id"], "comment_id": candidates[2]["comment_id"],
         "reply_text": candidates[2]["rendered_reply_text"], "status": "blocked", "verified": False,
         "error_type": "demo_send_disabled", "error_message": "Seeded demo record; no real platform reply was sent"},
    )
    usage = _ensure(
        storage, "token_usage", {"tenant_id": tenant["id"], "execution_id": executions["completed"]["id"], "provider": "openai"},
        {"campaign_id": active["id"], "model": "gpt-4o-mini", "prompt_tokens": 1840, "completion_tokens": 420,
         "total_tokens": 2260, "request_count": 4, "estimated_cost": 0.0012, "elapsed_ms": 3920},
    )
    notification = _ensure(
        storage, "notifications", {"tenant_id": tenant["id"], "dedupe_key": "demo:execution:partial"},
        {"user_id": admin["id"], "type": "execution_partial", "severity": "warning", "title": "Execution needs review",
         "message": "One demo keyword timed out; discovered leads were preserved.", "resource_type": "execution",
         "resource_id": executions["partial"]["id"]},
    )
    audit = _ensure(
        storage, "audit_logs", {"tenant_id": tenant["id"], "action": "demo.seed_ready", "resource_id": tenant["id"]},
        {"user_id": admin["id"], "resource_type": "tenant", "metadata_json": {"safe_mode": True, "real_sends_enabled": False}},
        update=False,
    )

    result = {"tenant": tenant, "user": admin, "admin": admin, "member": member, "memberships": [admin_membership, member_membership],
              "invitation": invitation, "platform_account": account, "campaign": active, "campaigns": campaigns,
              "reply_template": template, "reply_rule": rule, "leads": leads, "executions": executions,
              "reply_plan": plan, "reply_candidates": candidates, "reply_record": record, "token_usage": usage,
              "notification": notification, "audit_log": audit}
    result["readiness"] = demo_readiness_summary(storage, tenant_id=tenant["id"])
    return result


def demo_readiness_summary(storage: SaaSStorage, *, tenant_id: str | None = None) -> dict[str, Any]:
    tenant = storage.get_by_id("tenants", tenant_id) if tenant_id else storage.find_one("tenants", {"slug": DEMO_SLUG})
    if not tenant:
        return {"ready": False, "tenant_id": None, "reason": "demo tenant not seeded", "counts": {}, "real_sends_enabled": False}
    counts = {table: storage.count(table, tenant_id=tenant["id"]) for table in DEMO_TABLES}
    statuses = {status: storage.count("campaigns", tenant_id=tenant["id"], filters={"status": status}) for status in ("active", "paused", "draft")}
    required = {"tenant_users": 2, "platform_accounts": 1, "campaigns": 3, "leads": 4, "executions": 3,
                "reply_plans": 1, "reply_candidates": 3, "reply_records": 1, "token_usage": 1,
                "notifications": 1, "audit_logs": 1}
    ready = all(counts.get(table, 0) >= minimum for table, minimum in required.items()) and all(statuses.values())
    return {"ready": ready, "tenant_id": tenant["id"], "tenant_slug": tenant["slug"], "admin_email": DEMO_ADMIN_EMAIL,
            "counts": counts, "campaign_statuses": statuses, "real_sends_enabled": False,
            "safety": "Demo rows are additive; executions are send-disabled and replies require manual approval."}


def _ensure_user(service: SaaSService, storage: SaaSStorage, email: str, password: str, display_name: str) -> dict[str, Any]:
    existing = storage.find_one("users", {"email": email})
    return existing or service.create_user(email, password, display_name)


def _ensure(storage: SaaSStorage, table: str, filters: dict[str, Any], payload: dict[str, Any], *, update: bool = True) -> dict[str, Any]:
    existing = storage.find_one(table, filters)
    if existing:
        return (storage.update_by_id(table, existing["id"], payload, tenant_id=existing.get("tenant_id")) or existing) if update else existing
    return storage.insert(table, {**filters, **payload})


def _ensure_execution(storage: SaaSStorage, tenant_id: str, campaign_id: str, run_id: str, status: str,
                      started_at: Any, progress: int, error_message: str | None) -> dict[str, Any]:
    finished_at = started_at + timedelta(minutes=4)
    return _ensure(
        storage, "executions", {"tenant_id": tenant_id, "run_id": run_id},
        {"campaign_id": campaign_id, "platform": "facebook", "status": status, "trigger_type": "manual", "stage": status,
         "started_at": started_at, "finished_at": finished_at, "elapsed_ms": 240000, "total_keywords": 3,
         "completed_keywords": 3 if status == "completed" else 2 if status == "partial" else 0,
         "failed_keywords": 0 if status == "completed" else 1, "progress_percent": progress,
         "config_snapshot": {"demo": True, "demo_seed": True, "target_policy": "discovery_only"}, "scanned_contents": 14,
         "scanned_comments": 126, "lead_candidates": 8, "eligible_count": 4, "selected_count": 4,
         "prompt_tokens": 1840, "completion_tokens": 420, "total_tokens": 2260, "send_disabled": True,
         "error_type": "demo_partial" if error_message else None, "error_message": error_message},
    )
