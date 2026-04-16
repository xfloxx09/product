from datetime import datetime, timedelta

from ..extensions import db
from ..models import CoachingActionItem, CoachingSession, DataSource


def governance_snapshot(*, tenant_id):
    pii_action_items = CoachingActionItem.query.filter(
        CoachingActionItem.tenant_id == tenant_id,
        CoachingActionItem.pii_tags_json != "[]",
    ).count()
    pii_data_sources = DataSource.query.filter(
        DataSource.tenant_id == tenant_id,
        DataSource.pii_tags_json != "[]",
    ).count()
    retained_notes = CoachingSession.query.filter(
        CoachingSession.tenant_id == tenant_id,
        CoachingSession.coach_notes.isnot(None),
    ).count()
    return {
        "pii_tagged_action_items": pii_action_items,
        "pii_tagged_data_sources": pii_data_sources,
        "sessions_with_coach_notes": retained_notes,
    }


def enforce_notes_retention(*, tenant_id, retention_days):
    threshold = datetime.utcnow() - timedelta(days=max(1, int(retention_days)))
    candidates = CoachingSession.query.filter(
        CoachingSession.tenant_id == tenant_id,
        CoachingSession.occurred_at < threshold,
        CoachingSession.coach_notes.isnot(None),
    ).all()
    for row in candidates:
        row.coach_notes = None
    db.session.flush()
    return len(candidates)

