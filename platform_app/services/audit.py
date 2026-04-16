import json

from flask_login import current_user

from ..extensions import db
from ..models import AuditEvent


def log_audit_event(tenant_id, event_type, details=None, actor_user_id=None):
    actor_id = actor_user_id
    if actor_id is None and current_user and getattr(current_user, "is_authenticated", False):
        actor_id = current_user.id

    event = AuditEvent(
        tenant_id=tenant_id,
        actor_user_id=actor_id,
        event_type=event_type,
        details_json=json.dumps(details or {}),
    )
    db.session.add(event)
