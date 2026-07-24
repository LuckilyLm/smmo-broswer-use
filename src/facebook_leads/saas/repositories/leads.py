from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ..storage import SaaSStorage


class LeadRepository:
    def __init__(self, storage: SaaSStorage) -> None:
        self.storage = storage

    def upsert(self, lead: dict[str, Any], *, session: Session | None = None) -> dict[str, Any]:
        return self.storage.upsert_lead(lead, session=session)
