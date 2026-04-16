from datetime import datetime

from ..models import AgentProfile, CoachingActionItem, CoachingSession


def operations_kpis(*, tenant_id):
    sessions = CoachingSession.query.filter_by(tenant_id=tenant_id).all()
    session_ids = [s.id for s in sessions]
    actions = (
        CoachingActionItem.query.filter(
            CoachingActionItem.tenant_id == tenant_id,
            CoachingActionItem.coaching_session_id.in_(session_ids) if session_ids else False,
        ).all()
    )
    active_agents = AgentProfile.query.filter_by(tenant_id=tenant_id, status="active").count()
    sessions_with_actions = {a.coaching_session_id for a in actions}
    completed_actions = [a for a in actions if a.status == "completed"]
    now = datetime.utcnow()
    overdue_actions = [a for a in actions if a.status == "open" and a.due_at and a.due_at < now]
    closure_rate = (len(sessions_with_actions) / len(sessions)) if sessions else 0.0
    action_completion_rate = (len(completed_actions) / len(actions)) if actions else 0.0
    return {
        "active_agents": active_agents,
        "session_count": len(sessions),
        "action_item_count": len(actions),
        "sessions_with_action_rate": round(closure_rate, 4),
        "action_completion_rate": round(action_completion_rate, 4),
        "overdue_action_count": len(overdue_actions),
    }

