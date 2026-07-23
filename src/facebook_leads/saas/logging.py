from __future__ import annotations

import json
import logging
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
            "message": record.getMessage(),
        }
        return json.dumps(payload, ensure_ascii=True)


def configure_logging(service: str, level: str = "INFO") -> logging.LoggerAdapter:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger(f"facebook_leads.{service}")
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False
    return logging.LoggerAdapter(logger, {"service": service})
