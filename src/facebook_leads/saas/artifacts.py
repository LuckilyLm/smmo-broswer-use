from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any


SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_.-]+$")


def safe_artifact_path(root: str | Path, *components: str) -> Path:
    base = Path(root).resolve()
    for component in components:
        if not component or component in {".", ".."} or not SAFE_COMPONENT.fullmatch(component):
            raise ValueError("unsafe artifact path component")
    target = base.joinpath(*components).resolve()
    if target != base and base not in target.parents:
        raise ValueError("artifact path escapes root")
    return target


def atomic_write_json(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def load_json_safe(path: str | Path, *, default: Any = None, logger: logging.Logger | logging.LoggerAdapter | None = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        if logger:
            logger.warning("artifact_corrupt", extra={"error_type": type(exc).__name__})
        return default
