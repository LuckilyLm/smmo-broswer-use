from __future__ import annotations

from ..config import ProductionConfig
from ..runtime import BrowserRuntimeError


class RuntimeService:
    def __init__(self, config: ProductionConfig | None) -> None:
        self.config = config

    def require_available(self) -> None:
        if self.config is not None and not self.config.runtime_available:
            raise BrowserRuntimeError(
                "local_browser_runtime_not_supported",
                "local browser runtime is not supported on this service node",
            )
