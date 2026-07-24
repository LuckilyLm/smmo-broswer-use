from __future__ import annotations

from enum import StrEnum

from .models import TenantContext


class Permission(StrEnum):
    PLATFORM_ACCOUNT_WRITE = "platform_account_write"
    RUNTIME_CONTROL = "runtime_control"
    CAMPAIGN_WRITE = "campaign_write"
    KEYWORD_WRITE = "keyword_write"
    SCHEDULE_WRITE = "schedule_write"
    REPLY_RULE_WRITE = "reply_rule_write"
    EXECUTION_RUN = "execution_run"
    EXECUTION_CANCEL = "execution_cancel"
    TENANT_SETTINGS_WRITE = "tenant_settings_write"


_ALL_PERMISSIONS = frozenset(Permission)
ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "owner": _ALL_PERMISSIONS,
    "admin": _ALL_PERMISSIONS,
    "member": frozenset({Permission.EXECUTION_RUN}),
    "viewer": frozenset(),
    "scheduler": frozenset({Permission.EXECUTION_RUN}),
}


def require_permission(context: TenantContext, permission: Permission) -> None:
    if permission not in ROLE_PERMISSIONS.get(context.role, frozenset()):
        raise PermissionError("permission denied")
