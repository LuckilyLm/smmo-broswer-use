from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def main() -> None:
    migrate_command = [sys.executable, "scripts/saas_migrate.py"]
    if not os.getenv("DATABASE_URL"):
        migrate_command.extend(["--db-path", "artifacts/saas/saas.sqlite"])
    subprocess.run(migrate_command, cwd=ROOT, check=True)
    commands = [
        [sys.executable, "-m", "uvicorn", "src.facebook_leads.saas.api:app", "--reload", "--port", "8000"],
        [sys.executable, "scripts/saas_scheduler.py"],
        [sys.executable, "scripts/saas_worker.py"],
    ]
    processes = [subprocess.Popen(command, cwd=ROOT) for command in commands]
    try:
        for process in processes:
            process.wait()
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()


if __name__ == "__main__":
    main()
