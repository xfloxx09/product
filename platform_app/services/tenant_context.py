from functools import wraps

from flask import abort, g
from flask_login import current_user

from ..models import Tenant
from .policy import authorize_permission


def resolve_tenant_from_request(request):
    tenant_slug = request.headers.get("X-Tenant-Slug") or request.args.get("tenant")
    if not tenant_slug and current_user.is_authenticated:
        return current_user.tenant
    if not tenant_slug:
        return None
    return Tenant.query.filter_by(slug=tenant_slug, is_active=True).first()


def tenant_required(view_fn):
    @wraps(view_fn)
    def wrapper(*args, **kwargs):
        if not g.get("current_tenant"):
            abort(400, "Tenant context is required.")
        return view_fn(*args, **kwargs)

    return wrapper


def role_required(*allowed_roles):
    def decorator(view_fn):
        @wraps(view_fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if current_user.role not in allowed_roles:
                abort(403)
            return view_fn(*args, **kwargs)

        return wrapper

    return decorator


def permission_required(permission_name):
    def decorator(view_fn):
        @wraps(view_fn)
        def wrapper(*args, **kwargs):
            tenant = g.get("current_tenant")
            decision = authorize_permission(
                user=current_user,
                permission_name=permission_name,
                tenant_id=tenant.id if tenant else None,
            )
            if not decision.allowed:
                if decision.reason == "not_authenticated":
                    abort(401)
                abort(403)
            return view_fn(*args, **kwargs)

        return wrapper

    return decorator
