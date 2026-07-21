from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def create_diagnostic_dir(base_dir: str | Path = "artifacts/facebook_leads") -> Path:
    path = Path(base_dir) / datetime.now().strftime("%Y%m%d_%H%M%S")
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


async def save_failure_screenshot(page, directory: Path) -> str | None:
    path = directory / "failure.png"
    try:
        await page.screenshot(path=str(path), full_page=True)
    except Exception:
        return None
    return str(path)

