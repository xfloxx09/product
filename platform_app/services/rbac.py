import json

from flask import g, has_request_context
from sqlalchemy.exc import SQLAlchemyError

from ..models import TenantRole

ROLE_PERMISSIONS = {
    "owner": {
        "workspace.view",
        "workspace.manage_teams",
        "workspace.manage_agents",
        "workspace.manage_sessions",
        "workspace.manage_imports",
        "workspace.manage_integrations",
        "workspace.manage_users",
        "settings.manage",
        "billing.manage",
    },
    "admin": {
        "workspace.view",
        "workspace.manage_teams",
        "workspace.manage_agents",
        "workspace.manage_sessions",
        "workspace.manage_imports",
        "workspace.manage_integrations",
        "workspace.manage_users",
        "settings.manage",
        "billing.manage",
    },
    "manager": {
        "workspace.view",
        "workspace.manage_teams",
        "workspace.manage_agents",
        "workspace.manage_sessions",
        "workspace.manage_imports",
        "workspace.manage_integrations",
    },
    "coach": {
        "workspace.view",
        "workspace.manage_sessions",
    },
    "viewer": {
        "workspace.view",
    },
}


ALL_PERMISSIONS = sorted({perm for perms in ROLE_PERMISSIONS.values() for perm in perms})


def _system_role_definitions():
    return {
        role_key: {
            "role_key": role_key,
            "display_name": role_key.replace("_", " ").title(),
            "permissions": sorted(list(perms)),
            "is_system": True,
        }
        for role_key, perms in ROLE_PERMISSIONS.items()
    }


def list_effective_roles_for_tenant(tenant_id):
    roles = _system_role_definitions()
    try:
        overrides = TenantRole.query.filter_by(tenant_id=tenant_id).all()
    except SQLAlchemyError:
        return sorted(roles.values(), key=lambda x: x["display_name"].lower())

    for row in overrides:
        role_key = (row.role_key or "").strip().lower()
        if not role_key:
            continue
        try:
            stored_permissions = json.loads(row.permissions_json or "[]")
        except ValueError:
            stored_permissions = []
        normalized = sorted([p for p in stored_permissions if p in ALL_PERMISSIONS])
        roles[role_key] = {
            "role_key": role_key,
            "display_name": (row.display_name or role_key).strip() or role_key,
            "permissions": normalized,
            "is_system": bool(row.is_system),
        }
    return sorted(roles.values(), key=lambda x: x["display_name"].lower())


def role_key_exists_for_tenant(tenant_id, role_key):
    role = (role_key or "").strip().lower()
    if not role:
        return False
    return any(r["role_key"] == role for r in list_effective_roles_for_tenant(tenant_id))


def role_permissions_for_tenant(tenant_id, role_key):
    role = (role_key or "").strip().lower()
    if not role:
        return set()
    if has_request_context():
        cache = getattr(g, "_rbac_permissions_cache", None)
        if cache is None:
            cache = {}
            g._rbac_permissions_cache = cache
        cache_key = f"{tenant_id}:{role}"
        if cache_key in cache:
            return cache[cache_key]
    for definition in list_effective_roles_for_tenant(tenant_id):
        if definition["role_key"] == role:
            permissions = set(definition["permissions"])
            if has_request_context():
                g._rbac_permissions_cache[f"{tenant_id}:{role}"] = permissions
            return permissions
    if has_request_context():
        g._rbac_permissions_cache[f"{tenant_id}:{role}"] = set()
    return set()


def user_has_permission(user, permission_name):
    if not user or not getattr(user, "is_active", False):
        return False
    role = getattr(user, "role", "") or ""
    if role == "owner":
        return True
    tenant_id = getattr(user, "tenant_id", None)
    if tenant_id is None:
        return permission_name in ROLE_PERMISSIONS.get(role, set())
    return permission_name in role_permissions_for_tenant(tenant_id, role)
