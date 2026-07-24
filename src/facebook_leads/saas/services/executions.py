from __future__ import annotations


class ExecutionService:
    @staticmethod
    def safe_limit(limit: int) -> int:
        return min(max(int(limit), 1), 200)
