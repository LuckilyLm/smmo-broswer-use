from __future__ import annotations

import hashlib
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import and_, delete, func, insert, inspect, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .db import TABLES, create_saas_engine, make_session_factory, metadata, resolve_database_url, utc_now
from .repositories import LeadRepository, QueueRepository

CURRENT_SCHEMA_REVISION = "010_frontend_crud_support"


class SaaSStorage:
    def __init__(
        self,
        database_url: str | Path | None = None,
        *,
        create_schema: bool | None = None,
        engine: Engine | None = None,
    ) -> None:
        if engine is not None:
            self.engine = engine
            self.database_url = str(engine.url)
        else:
            self.database_url = resolve_database_url(str(database_url) if database_url is not None else None)
            self.engine = create_saas_engine(self.database_url)
        self.session_factory: sessionmaker[Session] = make_session_factory(self.engine)
        self.leads = LeadRepository(self)
        self.queue = QueueRepository(self)
        if create_schema is None:
            create_schema = self.engine.dialect.name == "sqlite"
        if create_schema:
            metadata.create_all(self.engine)

    def migrate(self) -> None:
        metadata.create_all(self.engine)

    def ping(self) -> bool:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True

    def schema_available(self) -> bool:
        inspector = inspect(self.engine)
        return all(name in inspector.get_table_names() for name in TABLES)

    def schema_current(self) -> bool:
        if not self.schema_available():
            return False
        if self.engine.dialect.name == "sqlite":
            return True
        try:
            row = self.query_one("SELECT version_num FROM alembic_version", [])
            return bool(row and row.get("version_num") == CURRENT_SCHEMA_REVISION)
        except Exception:
            return False

    @contextmanager
    def transaction(self):
        with self.session_factory.begin() as session:
            yield session

    def insert(self, table: str, data: dict[str, Any], *, session: Session | None = None) -> dict[str, Any]:
        db_table = _table(table)
        payload = _prepare_payload(table, data)
        if session is not None:
            session.execute(insert(db_table).values(**payload))
            return self.get_by_id(table, payload["id"], session=session) or _required_row(payload)
        with self.transaction() as owned_session:
            owned_session.execute(insert(db_table).values(**payload))
            return self.get_by_id(table, payload["id"], session=owned_session) or _required_row(payload)

    def insert_ignore(self, table: str, data: dict[str, Any]) -> dict[str, Any] | None:
        db_table = _table(table)
        payload = _prepare_payload(table, data)
        try:
            with self.session_factory.begin() as session:
                session.execute(insert(db_table).values(**payload))
        except IntegrityError:
            return None
        return self.get_by_id(table, payload["id"]) or _row(payload)

    def insert_many(self, table: str, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        db_table = _table(table)
        payloads = [_prepare_payload(table, row) for row in rows]
        with self.session_factory.begin() as session:
            session.execute(insert(db_table), payloads)
        return len(payloads)

    def update_by_id(self, table: str, item_id: str, data: dict[str, Any], *, tenant_id: str | None = None, session: Session | None = None) -> dict[str, Any] | None:
        db_table = _table(table)
        payload = {key: _coerce_value(value) for key, value in data.items() if key in db_table.c and key != "id"}
        if "updated_at" in db_table.c:
            payload["updated_at"] = utc_now()
        criteria = [db_table.c.id == item_id]
        if tenant_id is not None and "tenant_id" in db_table.c:
            criteria.append(db_table.c.tenant_id == tenant_id)
        if session is not None:
            session.execute(update(db_table).where(and_(*criteria)).values(**payload))
            return self.get_by_id(table, item_id, tenant_id=tenant_id, session=session)
        with self.transaction() as owned_session:
            owned_session.execute(update(db_table).where(and_(*criteria)).values(**payload))
            return self.get_by_id(table, item_id, tenant_id=tenant_id, session=owned_session)

    def delete_by_id(self, table: str, item_id: str, *, tenant_id: str | None = None) -> None:
        db_table = _table(table)
        criteria = [db_table.c.id == item_id]
        if tenant_id is not None and "tenant_id" in db_table.c:
            criteria.append(db_table.c.tenant_id == tenant_id)
        with self.session_factory.begin() as session:
            session.execute(delete(db_table).where(and_(*criteria)))

    def get_by_id(self, table: str, item_id: str, *, tenant_id: str | None = None, session: Session | None = None) -> dict[str, Any] | None:
        db_table = _table(table)
        criteria = [db_table.c.id == item_id]
        if tenant_id is not None and "tenant_id" in db_table.c:
            criteria.append(db_table.c.tenant_id == tenant_id)
        if session is not None:
            row = session.execute(select(db_table).where(and_(*criteria))).mappings().first()
            return _row(row)
        with self.session_factory() as owned_session:
            row = owned_session.execute(select(db_table).where(and_(*criteria))).mappings().first()
            return _row(row)

    def find_one(self, table: str, filters: dict[str, Any], *, order_by: list[str] | None = None) -> dict[str, Any] | None:
        rows = self.list(table, filters=filters, limit=1, order_by=order_by)
        return rows[0] if rows else None

    def list(
        self,
        table: str,
        *,
        tenant_id: str | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        offset: int = 0,
        order_by: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        db_table = _table(table)
        criteria = []
        if tenant_id is not None and "tenant_id" in db_table.c:
            criteria.append(db_table.c.tenant_id == tenant_id)
        for key, value in (filters or {}).items():
            if value is None or value == "":
                continue
            if key == "keyword" and table == "leads":
                criteria.append(or_(db_table.c.comment_text.ilike(f"%{value}%"), db_table.c.author_name.ilike(f"%{value}%")))
            elif key in db_table.c:
                criteria.append(db_table.c[key] == value)
        stmt = select(db_table)
        if criteria:
            stmt = stmt.where(and_(*criteria))
        stmt = stmt.order_by(*_order_columns(db_table, order_by)).limit(limit).offset(offset)
        with self.session_factory() as session:
            rows = session.execute(stmt).mappings().all()
        return [_required_row(row) for row in rows]

    def query_one(self, sql: str, values: list[Any]) -> dict[str, Any] | None:
        with self.session_factory() as session:
            row = session.execute(text(_named_sql(sql, values)), _named_values(values)).mappings().first()
        return _row(row)

    def query_all(self, sql: str, values: list[Any]) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            rows = session.execute(text(_named_sql(sql, values)), _named_values(values)).mappings().all()
        return [_required_row(row) for row in rows]

    def execute(self, sql: str, values: list[Any] | tuple[Any, ...] = ()) -> None:
        with self.session_factory.begin() as session:
            session.execute(text(_named_sql(sql, list(values))), _named_values(list(values)))

    def count(self, table: str, *, tenant_id: str | None = None, filters: dict[str, Any] | None = None, date_field: str | None = None, since: datetime | None = None, month_utc: bool = False) -> int:
        db_table = _table(table)
        criteria = _criteria(db_table, tenant_id=tenant_id, filters=filters)
        if date_field and since:
            criteria.append(db_table.c[date_field] >= since)
        if date_field and month_utc:
            now = utc_now()
            month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
            criteria.append(db_table.c[date_field] >= month_start)
        stmt = select(func.count()).select_from(db_table)
        if criteria:
            stmt = stmt.where(and_(*criteria))
        with self.session_factory() as session:
            return int(session.execute(stmt).scalar_one())

    def sum(self, table: str, column: str, *, tenant_id: str | None = None, date_field: str | None = None, since: datetime | None = None, month_utc: bool = False) -> int:
        db_table = _table(table)
        criteria = _criteria(db_table, tenant_id=tenant_id)
        if date_field and since:
            criteria.append(db_table.c[date_field] >= since)
        if date_field and month_utc:
            now = utc_now()
            criteria.append(db_table.c[date_field] >= datetime(now.year, now.month, 1, tzinfo=timezone.utc))
        stmt = select(func.coalesce(func.sum(db_table.c[column]), 0))
        if criteria:
            stmt = stmt.where(and_(*criteria))
        with self.session_factory() as session:
            return int(session.execute(stmt).scalar_one() or 0)

    def grouped_sum(self, table: str, group_column: str, sum_column: str, *, tenant_id: str) -> list[dict[str, Any]]:
        db_table = _table(table)
        stmt = (
            select(db_table.c[group_column], func.coalesce(func.sum(db_table.c[sum_column]), 0).label(sum_column))
            .where(db_table.c.tenant_id == tenant_id)
            .group_by(db_table.c[group_column])
        )
        with self.session_factory() as session:
            rows = session.execute(stmt).mappings().all()
        return [_required_row(row) for row in rows]

    def upsert_lead(self, lead: dict[str, Any], *, session: Session | None = None) -> dict[str, Any]:
        db_table = _table("leads")
        payload = _prepare_payload("leads", lead)
        if session is None:
            with self.transaction() as owned_session:
                return self.upsert_lead(payload, session=owned_session)
        payload = self._merge_existing_lead_payload(payload, session=session)
        if self.engine.dialect.name == "postgresql":
            stmt = pg_insert(db_table).values(**payload)
            update_values = {key: stmt.excluded[key] for key in payload if key not in {"id", "created_at"}}
            session.execute(
                stmt.on_conflict_do_update(
                    constraint="uq_leads_tenant_campaign_fingerprint",
                    set_=update_values,
                )
            )
        else:
            existing = session.execute(
                select(db_table.c.id).where(
                    and_(
                        db_table.c.tenant_id == payload["tenant_id"],
                        db_table.c.campaign_id == payload["campaign_id"],
                        db_table.c.comment_fingerprint == payload["comment_fingerprint"],
                    )
                )
            ).scalar_one_or_none()
            if existing:
                session.execute(
                    update(db_table)
                    .where(db_table.c.id == existing)
                    .values(**{key: value for key, value in payload.items() if key not in {"id", "created_at"}})
                )
            else:
                session.execute(insert(db_table).values(**payload))
        row = session.execute(
            select(db_table).where(
                and_(
                    db_table.c.tenant_id == payload["tenant_id"],
                    db_table.c.campaign_id == payload["campaign_id"],
                    db_table.c.comment_fingerprint == payload["comment_fingerprint"],
                )
            )
        ).mappings().first()
        return _row(row) or _required_row(payload)

    def upsert_token_usage(self, usage: dict[str, Any], *, session: Session | None = None) -> dict[str, Any]:
        table = _table("token_usage")
        payload = _prepare_payload("token_usage", usage)
        execution_keyword_id = payload.get("execution_keyword_id")
        if not execution_keyword_id:
            return self.insert("token_usage", payload, session=session)
        if session is None:
            with self.transaction() as owned_session:
                return self.upsert_token_usage(payload, session=owned_session)
        update_values = {key: value for key, value in payload.items() if key not in {"id", "created_at"}}
        if self.engine.dialect.name == "postgresql":
            statement = pg_insert(table).values(**payload)
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=[table.c.execution_keyword_id],
                    index_where=table.c.execution_keyword_id.is_not(None),
                    set_=update_values,
                )
            )
        else:
            statement = sqlite_insert(table).values(**payload)
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=[table.c.execution_keyword_id],
                    index_where=table.c.execution_keyword_id.is_not(None),
                    set_=update_values,
                )
            )
        row = session.execute(
            select(table).where(table.c.execution_keyword_id == execution_keyword_id)
        ).mappings().first()
        return _row(row) or payload

    def claim_queue_item(self, *, worker_id: str | None = None) -> dict[str, Any] | None:
        queue = _table("execution_queue_items")
        now = utc_now()
        with self.session_factory.begin() as session:
            stmt = (
                select(queue.c.id)
                .where(
                    and_(
                        queue.c.status.in_(["queued", "retry_waiting"]),
                        queue.c.run_after <= now,
                    )
                )
                .order_by(queue.c.priority.asc(), queue.c.queued_at.asc())
                .limit(1)
            )
            if self.engine.dialect.name == "postgresql":
                stmt = stmt.with_for_update(skip_locked=True)
                item_id = session.execute(stmt).scalar_one_or_none()
                if not item_id:
                    return None
                session.execute(
                    update(queue)
                    .where(queue.c.id == item_id)
                    .values(
                        status="running",
                        started_at=now,
                        claimed_by=worker_id,
                        attempt_count=queue.c.attempt_count + 1,
                        attempt_token=uuid.uuid4().hex,
                        updated_at=now,
                    )
                )
            else:
                candidate = stmt.scalar_subquery()
                claimed = session.execute(
                    update(queue)
                    .where(
                        and_(
                            queue.c.id == candidate,
                            queue.c.status.in_(["queued", "retry_waiting"]),
                        )
                    )
                    .values(
                        status="running",
                        started_at=now,
                        claimed_by=worker_id,
                        attempt_count=queue.c.attempt_count + 1,
                        attempt_token=uuid.uuid4().hex,
                        updated_at=now,
                    )
                    .returning(queue.c.id)
                ).scalar_one_or_none()
                if not claimed:
                    return None
                item_id = claimed
        return self.get_by_id("execution_queue_items", item_id)

    def acquire_runtime_lock(self, runtime_id: str) -> Any | None:
        if self.engine.dialect.name != "postgresql":
            return True
        lock_id = int.from_bytes(hashlib.blake2b(runtime_id.encode("utf-8"), digest_size=8).digest(), "big", signed=True)
        connection = self.engine.connect()
        try:
            if connection.execute(text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": lock_id}).scalar():
                return connection, lock_id
        except Exception:
            connection.close()
            raise
        connection.close()
        return None

    def release_runtime_lock(self, lock_handle: Any) -> None:
        if self.engine.dialect.name != "postgresql" or lock_handle is True:
            return
        connection, lock_id = lock_handle
        try:
            connection.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": lock_id})
        finally:
            connection.close()

    def queue_counts(self, *, tenant_id: str) -> dict[str, int]:
        rows = self.query_all(
            """
            SELECT status, COUNT(*) AS count
            FROM execution_queue_items
            WHERE tenant_id = ?
            GROUP BY status
            """,
            [tenant_id],
        )
        return {str(row["status"]): int(row["count"]) for row in rows}

    def fail_stale_queue_items(
        self,
        *,
        stale_before: datetime,
        heartbeat_stale_before: datetime | None = None,
        retry_analysis_only: bool = False,
    ) -> int:
        queue = _table("execution_queue_items")
        executions = _table("executions")
        heartbeats = _table("worker_heartbeats")
        now = utc_now()
        heartbeat_stale_before = heartbeat_stale_before or stale_before
        with self.session_factory.begin() as session:
            stale_rows = session.execute(
                select(
                    queue.c.id,
                    queue.c.execution_id,
                    queue.c.tenant_id,
                    queue.c.attempt_count,
                    queue.c.max_attempts,
                    executions.c.cancel_requested,
                    executions.c.send_disabled,
                )
                .join(executions, executions.c.id == queue.c.execution_id)
                .where(
                    and_(
                        queue.c.status == "running",
                        queue.c.started_at.is_not(None),
                        queue.c.started_at <= stale_before,
                        or_(
                            queue.c.claimed_by.is_(None),
                            ~select(heartbeats.c.id).where(
                                and_(
                                    heartbeats.c.worker_id == queue.c.claimed_by,
                                    heartbeats.c.current_queue_item_id == queue.c.id,
                                    heartbeats.c.last_seen_at > heartbeat_stale_before,
                                    heartbeats.c.status.in_(["running", "online", "polling"]),
                                )
                            ).exists(),
                        ),
                    )
                )
            ).mappings().all()
            for row in stale_rows:
                cancelled = bool(row["cancel_requested"])
                retryable = (
                    retry_analysis_only
                    and bool(row["send_disabled"])
                    and int(row["attempt_count"] or 0) < int(row["max_attempts"] or 3)
                )
                queue_status = "cancelled" if cancelled else "retry_waiting" if retryable else "failed"
                execution_status = "cancelled" if cancelled else "queued" if retryable else "failed"
                stage = "cancelled" if cancelled else "retry_waiting" if retryable else "failed"
                delay = [30, 120, 300][min(max(int(row["attempt_count"] or 1) - 1, 0), 2)]
                session.execute(
                    update(queue)
                    .where(and_(queue.c.id == row["id"], queue.c.status == "running"))
                    .values(
                        status=queue_status,
                        run_after=now + timedelta(seconds=delay) if retryable and not cancelled else queue.c.run_after,
                        finished_at=now if queue_status in {"failed", "cancelled"} else None,
                        error_type="worker_lost",
                        error_message="worker heartbeat expired",
                        updated_at=now,
                    )
                )
                session.execute(
                    update(executions)
                    .where(and_(executions.c.id == row["execution_id"], executions.c.status == "running"))
                    .values(
                        status=execution_status,
                        stage=stage,
                        finished_at=now if execution_status in {"failed", "cancelled"} else None,
                        error_type="worker_lost",
                        error_message="worker heartbeat expired",
                        updated_at=now,
                    )
                )
        return len(stale_rows)

    def _merge_existing_lead_payload(self, payload: dict[str, Any], *, session: Session | None = None) -> dict[str, Any]:
        table = _table("leads")
        if session is not None:
            row = session.execute(
                select(table).where(
                    and_(
                        table.c.tenant_id == payload["tenant_id"],
                        table.c.campaign_id == payload["campaign_id"],
                        table.c.comment_fingerprint == payload["comment_fingerprint"],
                    )
                )
            ).mappings().first()
            existing = _row(row)
        else:
            existing = self.find_one(
                "leads",
                {
                    "tenant_id": payload["tenant_id"],
                    "campaign_id": payload["campaign_id"],
                    "comment_fingerprint": payload["comment_fingerprint"],
                },
            )
        if not existing:
            payload.setdefault("first_discovered_at", payload.get("discovered_at") or utc_now())
            payload.setdefault("last_discovered_at", payload.get("discovered_at") or utc_now())
            return payload
        merged_keywords = []
        for value in existing.get("matched_search_keywords") or []:
            if value not in merged_keywords:
                merged_keywords.append(value)
        for value in payload.get("matched_search_keywords") or []:
            if value not in merged_keywords:
                merged_keywords.append(value)
        payload["matched_search_keywords"] = merged_keywords
        payload["status"] = existing.get("status") or payload.get("status")
        payload["first_discovered_at"] = _coerce_value(existing.get("first_discovered_at") or existing.get("discovered_at") or payload.get("discovered_at"))
        payload["last_discovered_at"] = payload.get("discovered_at") or utc_now()
        return payload

    def table_counts(self, tables: list[str]) -> dict[str, int]:
        return {table: self.count(table) for table in tables}


def _id(prefix: str) -> str:
    return f"{prefix[:4]}_{uuid.uuid4().hex[:12]}"


def _table(name: str):
    if name not in TABLES:
        raise ValueError(f"unknown table: {name}")
    return TABLES[name]


def _prepare_payload(table: str, data: dict[str, Any]) -> dict[str, Any]:
    db_table = _table(table)
    payload = {key: _coerce_value(value) for key, value in data.items() if key in db_table.c}
    payload.setdefault("id", _id(table))
    now = utc_now()
    if "created_at" in db_table.c:
        payload.setdefault("created_at", now)
    if "updated_at" in db_table.c:
        payload.setdefault("updated_at", now)
    return payload


def _coerce_value(value: Any) -> Any:
    if isinstance(value, str):
        try:
            if "T" in value:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
        except ValueError:
            return value
    return value


def _row(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    for key, value in list(data.items()):
        if isinstance(value, datetime):
            data[key] = value.isoformat()
    return data


def _required_row(row: Any) -> dict[str, Any]:
    data = _row(row)
    if data is None:
        raise RuntimeError("expected database row")
    return data


def _criteria(db_table, *, tenant_id: str | None = None, filters: dict[str, Any] | None = None) -> list[Any]:
    criteria = []
    if tenant_id is not None and "tenant_id" in db_table.c:
        criteria.append(db_table.c.tenant_id == tenant_id)
    for key, value in (filters or {}).items():
        if value is not None and key in db_table.c:
            criteria.append(db_table.c[key] == value)
    return criteria


def _order_columns(db_table, order_by: list[str] | None) -> list[Any]:
    if order_by:
        return [db_table.c[name] for name in order_by if name in db_table.c]
    if "created_at" in db_table.c:
        return [db_table.c.created_at.desc()]
    return [db_table.c.id]


def _named_sql(sql: str, values: list[Any]) -> str:
    for index in range(len(values)):
        sql = sql.replace("?", f":p{index}", 1)
    return sql


def _named_values(values: list[Any]) -> dict[str, Any]:
    return {f"p{index}": value for index, value in enumerate(values)}
