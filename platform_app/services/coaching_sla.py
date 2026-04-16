from datetime import datetime, timedelta

from sqlalchemy import func

from ..extensions import db
from ..models import AgentCoachingCadence, AgentProfile, CoachingSession


def cadence_map_for_agents(tenant_id, agent_ids):
    ids = [agent_id for agent_id in agent_ids if agent_id]
    if not ids:
        return {}
    rows = AgentCoachingCadence.query.filter(
        AgentCoachingCadence.tenant_id == tenant_id,
        AgentCoachingCadence.agent_id.in_(ids),
    ).all()
    return {row.agent_id: row for row in rows}


def build_agent_sla_rows(*, tenant_id, scoped_team_ids=None, default_cadence_days=30):
    agents_q = AgentProfile.query.filter_by(tenant_id=tenant_id)
    if scoped_team_ids is not None:
        agents_q = agents_q.filter(AgentProfile.team_id.in_(scoped_team_ids))
    agents = agents_q.order_by(AgentProfile.full_name.asc()).all()
    agent_ids = [agent.id for agent in agents]
    cadence_rows = cadence_map_for_agents(tenant_id, agent_ids)

    last_session_rows = (
        db.session.query(
            CoachingSession.agent_id,
            func.max(CoachingSession.occurred_at).label("last_session_at"),
        )
        .filter(
            CoachingSession.tenant_id == tenant_id,
            CoachingSession.agent_id.in_(agent_ids) if agent_ids else False,
        )
        .group_by(CoachingSession.agent_id)
        .all()
    )
    last_session_map = {row.agent_id: row.last_session_at for row in last_session_rows}
    now = datetime.utcnow()
    result = []
    for agent in agents:
        cadence_days = int((cadence_rows.get(agent.id).cadence_days if cadence_rows.get(agent.id) else default_cadence_days) or default_cadence_days)
        last_session_at = last_session_map.get(agent.id)
        due_at = (last_session_at + timedelta(days=cadence_days)) if last_session_at else None
        overdue_days = 0
        status = "on_track"
        if agent.status != "active":
            status = "inactive"
        elif last_session_at is None:
            status = "never_coached"
        elif due_at and due_at < now:
            status = "overdue"
            overdue_days = max(1, (now - due_at).days)
        result.append(
            {
                "agent": agent,
                "cadence_days": cadence_days,
                "last_session_at": last_session_at,
                "due_at": due_at,
                "status": status,
                "overdue_days": overdue_days,
            }
        )
    return result
