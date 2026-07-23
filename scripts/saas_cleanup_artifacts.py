from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path


def cleanup(root: Path, *, retention_days: int, execute: bool = False) -> list[Path]:
    root = root.resolve()
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    candidates: list[Path] = []
    tenants_root = root / "tenants"
    if not tenants_root.exists():
        return candidates
    for path in tenants_root.glob("*/executions/*"):
        resolved = path.resolve()
        if not resolved.is_dir() or root not in resolved.parents:
            continue
        modified = datetime.fromtimestamp(resolved.stat().st_mtime, timezone.utc)
        if modified <= cutoff:
            candidates.append(resolved)
    if execute:
        for path in candidates:
            shutil.rmtree(path)
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(description="List or remove expired tenant execution artifacts.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--retention-days", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true", help="Retained for explicit documentation; dry-run is always the default.")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.retention_days < 1:
        raise SystemExit("--retention-days must be at least 1")
    for path in cleanup(args.root, retention_days=args.retention_days, execute=args.execute):
        print(("DELETE " if args.execute else "WOULD_DELETE ") + str(path))


if __name__ == "__main__":
    main()
