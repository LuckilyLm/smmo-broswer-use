from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

from src.facebook_leads.facebook.orchestrator import (  # noqa: E402
    build_config_from_env,
    config_preview,
    exit_code_for_result,
    run_facebook_leads_job,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one Facebook Leads Phase 6 analysis and batch-plan job. No replies are sent.")
    parser.add_argument("--cdp-url", default=None)
    parser.add_argument("--keyword", default=None)
    parser.add_argument("--max-contents", type=int, default=None)
    parser.add_argument("--max-comments", type=int, default=None)
    parser.add_argument("--llm-review", action="store_true", default=None)
    parser.add_argument("--no-llm-review", action="store_true")
    parser.add_argument("--max-leads", type=int, default=None)
    parser.add_argument("--min-confidence", type=float, default=None)
    parser.add_argument("--daily-limit", type=int, default=None)
    parser.add_argument("--interval-seconds", type=float, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--print-config", action="store_true")
    parser.add_argument("--resume", default=None)
    parser.add_argument("--target-policy", choices=["owned_only", "allowlist", "discovery_only"], default=None)
    parser.add_argument("--allow-source-url", action="append", default=[])
    parser.add_argument("--owned-source-id", action="append", default=[])
    parser.add_argument("--tenant-id", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = build_config_from_env(args)
    if args.print_config:
        print(json.dumps(config_preview(config), indent=2, ensure_ascii=False))
        raise SystemExit(0)
    result = asyncio.run(run_facebook_leads_job(config))
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    raise SystemExit(exit_code_for_result(result))


if __name__ == "__main__":
    main()
