from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .db import utc_now
from .models import TenantContext
from .productization import QuotaExceededError
from .service import SaaSService


@dataclass(frozen=True)
class EnqueueResult:
    status: str
    execution: dict[str, Any] | None = None


class CampaignScheduler:
    def __init__(self, service: SaaSService, *, queue_full_retry_minutes: int | None = None) -> None:
        self.service = service
        self.queue_full_retry_minutes = queue_full_retry_minutes or 5
        self.last_tick_at: datetime | None = None
        self.due_campaign_count = 0

    def scan_due_campaigns(self) -> list[dict[str, Any]]:
        now = utc_now()
        schedules = self.service.storage.query_all(
            """
            SELECT s.*
            FROM campaign_schedules s
            JOIN campaigns c ON c.id = s.campaign_id
            WHERE s.enabled = ?
              AND s.next_run_at IS NOT NULL
              AND s.next_run_at <= ?
              AND c.status = ?
            ORDER BY s.next_run_at ASC
            """,
            [True, now, "active"],
        )
        self.last_tick_at = now
        self.due_campaign_count = len(schedules)
        return schedules

    def enqueue_execution(self, schedule: dict[str, Any]) -> EnqueueResult:
        scheduled_time = _iso_minute(schedule["next_run_at"])
        trigger_key = f"{schedule['campaign_id']}:{scheduled_time}"
        context = TenantContext(tenant_id=schedule["tenant_id"], user_id="scheduler", role="scheduler")
        try:
            execution = self.service.enqueue_campaign_execution(context, schedule["campaign_id"], trigger_type="scheduled", schedule_trigger_key=trigger_key)
            return EnqueueResult(status="enqueued", execution=execution)
        except QuotaExceededError:
            return EnqueueResult(status="quota_exceeded")
        except ValueError as exc:
            if "already enqueued" in str(exc):
                return EnqueueResult(status="duplicate")
            if "queue_limit_reached" in str(exc):
                return EnqueueResult(status="queue_full")
            raise

    def update_next_run(self, schedule: dict[str, Any]) -> dict[str, Any] | None:
        context = TenantContext(tenant_id=schedule["tenant_id"], user_id="scheduler", role="scheduler")
        next_run_at = self.service._compute_next_run(
            schedule["schedule_type"],
            schedule["timezone"],
            interval_minutes=schedule.get("interval_minutes"),
            daily_time=schedule.get("daily_time"),
        )
        return self.service.storage.update_by_id("campaign_schedules", schedule["id"], {"last_run_at": utc_now(), "next_run_at": next_run_at}, tenant_id=context.tenant_id)

    def defer_queue_full(self, schedule: dict[str, Any]) -> dict[str, Any] | None:
        return self.service.storage.update_by_id(
            "campaign_schedules",
            schedule["id"],
            {"next_run_at": utc_now() + timedelta(minutes=self.queue_full_retry_minutes)},
            tenant_id=schedule["tenant_id"],
        )

    def recover_missed_schedule(self) -> list[dict[str, Any]]:
        return self.tick()

    def tick(self) -> list[dict[str, Any]]:
        enqueued = []
        for schedule in self.scan_due_campaigns():
            result = self.enqueue_execution(schedule)
            if result.status == "queue_full":
                self.defer_queue_full(schedule)
            else:
                self.update_next_run(schedule)
            if result.execution:
                enqueued.append(result.execution)
        self._heartbeat()
        return enqueued

    def _heartbeat(self) -> None:
        payload = {"worker_id": "scheduler", "last_seen_at": self.last_tick_at or utc_now(), "status": "online", "current_queue_item_id": None, "last_error": None}
        existing = self.service.storage.find_one("worker_heartbeats", {"worker_id": "scheduler"})
        if existing:
            self.service.storage.update_by_id("worker_heartbeats", existing["id"], payload)
        else:
            self.service.storage.insert_ignore("worker_heartbeats", payload)

    def record_error(self, error_type: str) -> None:
        existing = self.service.storage.find_one("worker_heartbeats", {"worker_id": "scheduler"})
        payload = {"worker_id": "scheduler", "last_seen_at": utc_now(), "status": "error", "last_error": error_type}
        if existing:
            self.service.storage.update_by_id("worker_heartbeats", existing["id"], payload)
        else:
            self.service.storage.insert_ignore("worker_heartbeats", payload)


def scheduler_status(scheduler: CampaignScheduler) -> dict[str, Any]:
    return {
        "last_tick_at": scheduler.last_tick_at.isoformat() if scheduler.last_tick_at else None,
        "due_campaign_count": scheduler.due_campaign_count,
    }


def _iso_minute(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(second=0, microsecond=0).isoformat()
