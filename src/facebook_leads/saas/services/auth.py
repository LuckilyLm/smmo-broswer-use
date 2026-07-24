from __future__ import annotations

import secrets
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from ..db import utc_now

if TYPE_CHECKING:
    from ..service import SaaSService


class AuthService:
    def __init__(self, facade: SaaSService) -> None:
        self.facade = facade

    def rotate_session(self, token: str, tenant_id: str) -> dict[str, Any]:
        context = self.facade.context_from_token(token)
        switched = self.facade.switch_tenant(context, tenant_id)
        now = utc_now()
        new_token = f"sess_{secrets.token_urlsafe(24)}"
        with self.facade.storage.transaction() as session:
            self.facade.storage.insert(
                "sessions",
                {
                    "id": new_token,
                    "user_id": switched.user_id,
                    "tenant_id": switched.tenant_id,
                    "expires_at": now + self.facade.session_ttl,
                    "last_seen_at": now,
                    "revoked_at": None,
                },
                session=session,
            )
            self.facade.storage.update_by_id("sessions", token, {"revoked_at": now}, session=session)
        return {"access_token": new_token, "tenant_id": switched.tenant_id}
