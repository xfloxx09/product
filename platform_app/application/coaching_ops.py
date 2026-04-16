from datetime import datetime

from sqlalchemy import case, func

from ..domain.contracts import can_transition
from ..domain.contracts import CASE_STATE_TRANSITIONS
from ..extensions import db
from ..models import (
    AgentProfile,
    CoachingActionItem,
    CoachingCase,
    CoachingSession,
    DomainEvent,
)
from ..services.coaching_workflow import ensure_case_for_session


def _parse_iso_date(raw):
    value = (raw or "").strip()
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d")


def create_planned_case_from_form(*, tenant_id, actor_user_id, form_data, scoped_team_ids=None):
    agent_id = form_data.get("agent_id")
    title = (form_data.get("title") or "").strip()
    summary = (form_data.get("summary") or "").strip() or None
    source_type = (form_data.get("source_type") or "manager_assigned").strip().lower()
    priority = (form_data.get("priority") or "normal").strip().lower()
    try:
        due_at = _parse_iso_date(form_data.get("due_at"))
    except ValueError as exc:
        raise ValueError("invalid_due_date") from exc

    agent_q = AgentProfile.query.filter_by(id=agent_id, tenant_id=tenant_id)
    if scoped_team_ids is not None:
        agent_q = agent_q.filter(AgentProfile.team_id.in_(scoped_team_ids))
    agent = agent_q.first()
    if not agent:
        raise ValueError("invalid_agent")
    if scoped_team_ids is not None and agent.team_id not in scoped_team_ids:
        raise ValueError("team_scope_violation")

    new_case = CoachingCase(
        tenant_id=tenant_id,
        program_id=agent.program_id,
        team_id=agent.team_id,
        agent_id=agent.id,
        requested_by_user_id=actor_user_id,
        assigned_to_user_id=actor_user_id,
        title=title or f"Planned coaching for {agent.full_name}",
        summary=summary,
        source_type=source_type,
        priority=priority,
        status="planned",
        due_at=due_at,
        planned_at=datetime.utcnow(),
    )
    db.session.add(new_case)
    db.session.flush()
    db.session.add(
        DomainEvent(
            tenant_id=tenant_id,
            aggregate_type="coaching_case",
            aggregate_id=new_case.id,
            event_type="coaching_case.planned",
            payload_json='{"source":"workspace.coaching_ops_hub"}',
        )
    )
    return new_case


def create_session_from_form(*, tenant_id, actor_user_id, form_data, scoped_team_ids=None):
    agent_id = form_data.get("agent_id")
    coaching_type = (form_data.get("coaching_type") or "quality").strip()
    channel = (form_data.get("channel") or "call").strip()
    score_raw = (form_data.get("score") or "").strip()
    notes = (form_data.get("notes") or "").strip() or None
    subject = (form_data.get("subject") or "").strip() or None
    coach_notes = (form_data.get("coach_notes") or "").strip() or None
    action_items_raw = (form_data.get("action_items") or "").strip()
    try:
        action_due_at = _parse_iso_date(form_data.get("action_due_at"))
    except ValueError as exc:
        raise ValueError("invalid_action_due_date") from exc

    agent_q = AgentProfile.query.filter_by(id=agent_id, tenant_id=tenant_id)
    if scoped_team_ids is not None:
        agent_q = agent_q.filter(AgentProfile.team_id.in_(scoped_team_ids))
    agent = agent_q.first()
    if not agent:
        raise ValueError("invalid_agent")
    if scoped_team_ids is not None and agent.team_id not in scoped_team_ids:
        raise ValueError("team_scope_violation")

    score = None
    if score_raw:
        try:
            score = float(score_raw)
        except ValueError as exc:
            raise ValueError("invalid_score") from exc

    session = CoachingSession(
        tenant_id=tenant_id,
        agent_id=agent.id,
        coach_user_id=actor_user_id,
        coaching_type=coaching_type,
        channel=channel,
        score=score,
        notes=notes,
        subject=subject,
        coach_notes=coach_notes,
    )
    db.session.add(session)
    db.session.flush()
    coaching_case = ensure_case_for_session(session)
    if can_transition(CASE_STATE_TRANSITIONS, coaching_case.status, "completed"):
        coaching_case.status = "completed"
        coaching_case.completed_at = session.occurred_at
        coaching_case.closed_at = session.occurred_at
    action_titles = [line.strip() for line in action_items_raw.splitlines() if line.strip()]
    for title in action_titles[:10]:
        db.session.add(
            CoachingActionItem(
                tenant_id=tenant_id,
                coaching_session_id=session.id,
                owner_user_id=actor_user_id,
                title=title[:255],
                due_at=action_due_at,
            )
        )
    db.session.add(
        DomainEvent(
            tenant_id=tenant_id,
            aggregate_type="coaching_session",
            aggregate_id=session.id,
            event_type="coaching_session.submitted",
            payload_json='{"source":"workspace.sessions"}',
        )
    )
    return session, coaching_case, len(action_titles[:10])


def session_action_completion_map(*, tenant_id, session_ids):
    rows = (
        db.session.query(
            CoachingActionItem.coaching_session_id,
            func.count(CoachingActionItem.id).label("total_count"),
            func.sum(case((CoachingActionItem.status == "completed", 1), else_=0)).label("completed_count"),
        )
        .filter(
            CoachingActionItem.tenant_id == tenant_id,
            CoachingActionItem.coaching_session_id.in_(session_ids) if session_ids else False,
        )
        .group_by(CoachingActionItem.coaching_session_id)
        .all()
    )
    return {
        row.coaching_session_id: {"total": int(row.total_count or 0), "completed": int(row.completed_count or 0)}
        for row in rows
    }

