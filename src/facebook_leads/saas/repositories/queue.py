from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..storage import SaaSStorage


class QueueRepository:
    def __init__(self, storage: SaaSStorage) -> None:
        self.storage = storage

    def claim(self, *, worker_id: str | None = None) -> dict[str, Any] | None:
        return self.storage.claim_queue_item(worker_id=worker_id)

    def recover_stale(
        self,
        *,
        stale_before: datetime,
        heartbeat_stale_before: datetime,
        retry_analysis_only: bool,
    ) -> int:
        return self.storage.fail_stale_queue_items(
            stale_before=stale_before,
            heartbeat_stale_before=heartbeat_stale_before,
            retry_analysis_only=retry_analysis_only,
        )
