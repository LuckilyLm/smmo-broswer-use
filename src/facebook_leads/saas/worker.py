from __future__ import annotations

import asyncio
import os
import socket
from datetime import timedelta
from typing import Any

from .db import utc_now
from .service import SaaSService


class ExecutionWorker:
    def __init__(self, service: SaaSService, *, worker_id: str | None = None) -> None:
        self.service = service
        self.worker_id = worker_id or f"{socket.gethostname()}-worker"

    async def tick(self) -> dict[str, Any] | None:
        self.heartbeat(status="polling")
        stale_seconds = int(os.getenv("SAAS_QUEUE_STALE_SECONDS", "21600"))
        heartbeat_seconds = int(os.getenv("SAAS_HEARTBEAT_STALE_SECONDS", "60"))
        self.service.storage.fail_stale_queue_items(
            stale_before=utc_now() - timedelta(seconds=stale_seconds),
            heartbeat_stale_before=utc_now() - timedelta(seconds=heartbeat_seconds),
        )
        item = self.service.storage.claim_queue_item(worker_id=self.worker_id)
        if not item:
            return None
        self.heartbeat(status="running", current_queue_item_id=item["id"])
        try:
            return await self.service.run_queue_item(item)
        finally:
            self.heartbeat(status="online", current_queue_item_id=None)

    async def run_forever(self, *, poll_seconds: float = 5.0, stop_event: asyncio.Event | None = None) -> None:
        stop_event = stop_event or asyncio.Event()
        while not stop_event.is_set():
            await self.tick()
            if stop_event.is_set():
                break
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
            except TimeoutError:
                pass
        self.heartbeat(status="stopped", current_queue_item_id=None)

    def heartbeat(self, *, status: str, current_queue_item_id: str | None = None) -> dict[str, Any]:
        existing = self.service.storage.find_one("worker_heartbeats", {"worker_id": self.worker_id})
        payload = {"worker_id": self.worker_id, "last_seen_at": utc_now(), "status": status, "current_queue_item_id": current_queue_item_id}
        if existing:
            return self.service.storage.update_by_id("worker_heartbeats", existing["id"], payload) or existing
        return self.service.storage.insert("worker_heartbeats", payload)
