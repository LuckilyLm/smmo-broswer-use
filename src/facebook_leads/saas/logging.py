from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

_STANDARD_LOG_RECORD_KEYS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class ContextLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg: Any, kwargs: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        adapter_extra = self.extra if isinstance(self.extra, dict) else {}
        call_extra = kwargs.get("extra") if isinstance(kwargs.get("extra"), dict) else {}
        kwargs["extra"] = {**adapter_extra, **call_extra}
        return msg, kwargs


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
        for key, value in record.__dict__.items():
            if key in _STANDARD_LOG_RECORD_KEYS or key in payload:
                continue
            payload[str(key)] = sanitize(value)
        if record.exc_info:
            payload["exception_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
            payload["exception"] = _sanitize_text(self.formatException(record.exc_info))
        return json.dumps(sanitize(payload), ensure_ascii=True)


def configure_logging(service: str, level: str = "INFO") -> ContextLoggerAdapter:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger(f"facebook_leads.{service}")
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False
    return ContextLoggerAdapter(logger, {"service": service})


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


def log_context(logger: logging.LoggerAdapter, **context: Any) -> ContextLoggerAdapter:
    allowed = {"tenant_id", "campaign_id", "execution_id", "runtime_id", "queue_item_id"}
    extra = logger.extra if isinstance(logger.extra, dict) else {}
    return ContextLoggerAdapter(logger.logger, {**extra, **{key: value for key, value in context.items() if key in allowed}})


def _sanitize_text(value: str) -> str:
    value = re.sub(r"(https?://(?:127\.0\.0\.1|localhost):\d+)", "[REDACTED_CDP]", value)
    value = re.sub(r"(?i)(authorization|cookie|password|session_token)=\S+", r"\1=[REDACTED]", value)
    return value
