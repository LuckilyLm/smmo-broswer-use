from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": getattr(record, "service", "saas"),
            "tenant_id": getattr(record, "tenant_id", None),
            "campaign_id": getattr(record, "campaign_id", None),
            "execution_id": getattr(record, "execution_id", None),
            "runtime_id": getattr(record, "runtime_id", None),
            "queue_item_id": getattr(record, "queue_item_id", None),
            "message": _sanitize_text(record.getMessage()),
        }
        return json.dumps(sanitize(payload), ensure_ascii=True)


def configure_logging(service: str, level: str = "INFO") -> logging.LoggerAdapter:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger(f"facebook_leads.{service}")
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False
    return logging.LoggerAdapter(logger, {"service": service})


SENSITIVE_KEYS = {
    "password",
    "session",
    "session_token",
    "cookie",
    "authorization",
    "cdp_url",
    "profile_path",
    "websocketdebuggerurl",
}


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if str(key).lower() in SENSITIVE_KEYS else sanitize(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize(item) for item in value)
    if isinstance(value, str):
        return _sanitize_text(value)
    return value


def log_context(logger: logging.LoggerAdapter, **context: Any) -> logging.LoggerAdapter:
    allowed = {"tenant_id", "campaign_id", "execution_id", "runtime_id", "queue_item_id"}
    extra = logger.extra if isinstance(logger.extra, dict) else {}
    return logging.LoggerAdapter(logger.logger, {**extra, **{key: value for key, value in context.items() if key in allowed}})


def _sanitize_text(value: str) -> str:
    value = re.sub(r"(https?://(?:127\.0\.0\.1|localhost):\d+)", "[REDACTED_CDP]", value)
    value = re.sub(r"(?i)(authorization|cookie|password|session_token)=\S+", r"\1=[REDACTED]", value)
    return value
