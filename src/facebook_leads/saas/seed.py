from __future__ import annotations

import os
from typing import Any

from .service import SaaSService
from .storage import SaaSStorage


def seed_demo_data(storage: SaaSStorage, *, password: str | None = None) -> dict[str, Any]:
    service = SaaSService(storage)
    password = password or os.getenv("FACEBOOK_LEADS_DEMO_PASSWORD")
    if not password:
        raise ValueError("FACEBOOK_LEADS_DEMO_PASSWORD is required for demo seed")

    tenant = storage.find_one("tenants", {"slug": "demo"}) or service.create_tenant("Demo Tenant", "demo")
    user = storage.find_one("users", {"email": "admin@example.com"}) or service.create_user(
        "admin@example.com",
        password,
        "Demo Admin",
    )
    membership = storage.find_one("tenant_users", {"tenant_id": tenant["id"], "user_id": user["id"]})
    if not membership:
        service.add_user_to_tenant(tenant["id"], user["id"], role="admin")

    account = storage.find_one("platform_accounts", {"tenant_id": tenant["id"], "platform": "facebook"})
    context = service.login("admin@example.com", password)
    tenant_context = service.context_from_token(context["access_token"])
    if not account:
        account = service.create_platform_account(
            tenant_context,
            {
                "platform": "facebook",
                "display_name": "Demo Facebook Account",
                "external_account_name": "Demo Page",
                "connection_status": "connected",
            },
        )
    campaign = storage.find_one("campaigns", {"tenant_id": tenant["id"], "name": "Massage Chair Leads"})
    if not campaign:
        campaign = service.create_campaign(
            tenant_context,
            {
                "name": "Massage Chair Leads",
                "platform_account_id": account["id"],
                "status": "active",
                "target_policy": "discovery_only",
                "max_contents": 5,
                "max_comments": 80,
                "min_confidence": 0.9,
            },
        )
    existing_keywords = storage.list("campaign_keywords", tenant_id=tenant["id"], filters={"campaign_id": campaign["id"]}, limit=100)
    existing = {row["keyword"] for row in existing_keywords}
    for index, keyword in enumerate(["massage chair", "zero gravity massage chair", "home massage chair"]):
        if keyword not in existing:
            service.create_keyword(tenant_context, campaign["id"], {"keyword": keyword, "priority": index + 1})
    service.logout(context["access_token"])
    return {"tenant": tenant, "user": user, "platform_account": account, "campaign": campaign}
