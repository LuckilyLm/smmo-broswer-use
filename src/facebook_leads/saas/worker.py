from __future__ import annotations

import asyncio
import socket
from datetime import timedelta
from typing import Any

from .db import utc_now
from .service import SaaSService


class ExecutionWorker:
    def __init__(
        self,
        service: SaaSService,
        *,
        worker_id: str | None = None,
        heartbeat_interval_seconds: float = 15,
        queue_stale_seconds: int = 21600,
        heartbeat_stale_seconds: int = 60,
    ) -> None:
        self.service = service
        self.worker_id = worker_id or f"{socket.gethostname()}-worker"
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.queue_stale_seconds = queue_stale_seconds
        self.heartbeat_stale_seconds = heartbeat_stale_seconds

    async def tick(self) -> dict[str, Any] | None:
        self.heartbeat(status="polling")
        self.service.storage.queue.recover_stale(
            stale_before=utc_now() - timedelta(seconds=self.queue_stale_seconds),
            heartbeat_stale_before=utc_now() - timedelta(seconds=self.heartbeat_stale_seconds),
            retry_analysis_only=True,
        )
        item = self.service.storage.queue.claim(worker_id=self.worker_id)
        if not item:
            return None
        self.heartbeat(status="running", current_queue_item_id=item["id"])
        heartbeat_stop = asyncio.Event()
        heartbeat_task = asyncio.create_task(self._heartbeat_during_run(item["id"], heartbeat_stop))
        try:
            return await self.service.run_queue_item(item)
        finally:
            heartbeat_stop.set()
            await heartbeat_task
            self.heartbeat(status="online", current_queue_item_id=None)

    async def _heartbeat_during_run(self, queue_item_id: str, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.heartbeat_interval_seconds)
            except TimeoutError:
                self.heartbeat(status="running", current_queue_item_id=queue_item_id)

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
