from dataclasses import dataclass

from .rbac import user_has_permission
from .team_scope import get_user_team_scope_ids


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str = "ok"


def authorize_permission(*, user, permission_name, tenant_id=None):
    if not user or not getattr(user, "is_authenticated", False):
        return PolicyDecision(False, "not_authenticated")
    if not getattr(user, "is_active", False):
        return PolicyDecision(False, "inactive_user")
    if tenant_id is not None and getattr(user, "tenant_id", None) != tenant_id:
        return PolicyDecision(False, "cross_tenant_blocked")
    if not user_has_permission(user, permission_name):
        return PolicyDecision(False, "missing_permission")
    return PolicyDecision(True)


def authorize_team_scope(*, user, team_id):
    if team_id is None:
        return PolicyDecision(True)
    scoped_ids = get_user_team_scope_ids(user)
    if scoped_ids is None:
        return PolicyDecision(True)
    if team_id not in scoped_ids:
        return PolicyDecision(False, "team_scope_violation")
    return PolicyDecision(True)

