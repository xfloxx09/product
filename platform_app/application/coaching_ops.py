from datetime import datetime

from sqlalchemy import case, func

from ..domain.contracts import can_transition
from ..domain.contracts import CASE_STATE_TRANSITIONS
from ..extensions import db
from ..models import (
    AgentProfile,
    CoachingActionItem,
    CoachingCase,
    CoachingSessionCoach,
    CoachingSession,
    DomainEvent,
    TenantUser,
)
from ..services.coaching_workflow import ensure_case_for_session


def _parse_iso_date(raw):
    value = (raw or "").strip()
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d")


def _parse_iso_datetime(raw):
    value = (raw or "").strip()
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%dT%H:%M")


def _get_list(form_data, key):
    if hasattr(form_data, "getlist"):
        return form_data.getlist(key)
    value = form_data.get(key)
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def create_planned_case_from_form(*, tenant_id, actor_user_id, form_data, scoped_team_ids=None):
    agent_id = form_data.get("agent_id")
    title = (form_data.get("title") or "").strip()
    summary = (form_data.get("summary") or "").strip() or None
    source_type = (form_data.get("source_type") or "manager_assigned").strip().lower()
    coaching_format = (form_data.get("coaching_format") or "one_to_one").strip().lower()
    if coaching_format not in {"one_to_one", "workshop"}:
        coaching_format = "one_to_one"
    delivery_mode = (form_data.get("delivery_mode") or "side_by_side").strip().lower()
    if delivery_mode not in {"side_by_side", "remote"}:
        delivery_mode = "side_by_side"
    priority = (form_data.get("priority") or "normal").strip().lower()
    assigned_to_user_id = form_data.get("assigned_to_user_id")
    assignment_notes = (form_data.get("assignment_notes") or "").strip() or None
    try:
        due_at = _parse_iso_date(form_data.get("due_at"))
    except ValueError as exc:
        raise ValueError("invalid_due_date") from exc
    try:
        planned_for = _parse_iso_datetime(form_data.get("planned_for"))
    except ValueError as exc:
        raise ValueError("invalid_planned_for") from exc

    agent_q = AgentProfile.query.filter_by(id=agent_id, tenant_id=tenant_id)
    if scoped_team_ids is not None:
        agent_q = agent_q.filter(AgentProfile.team_id.in_(scoped_team_ids))
    agent = agent_q.first()
    if not agent:
        raise ValueError("invalid_agent")
    if scoped_team_ids is not None and agent.team_id not in scoped_team_ids:
        raise ValueError("team_scope_violation")
    assigned_to = None
    if assigned_to_user_id:
        assigned_to = TenantUser.query.filter_by(
            id=assigned_to_user_id,
            tenant_id=tenant_id,
            is_active=True,
        ).first()
        if not assigned_to:
            raise ValueError("invalid_assignee")

    new_case = CoachingCase(
        tenant_id=tenant_id,
        program_id=agent.program_id,
        team_id=agent.team_id,
        agent_id=agent.id,
        requested_by_user_id=actor_user_id,
        assigned_to_user_id=assigned_to.id if assigned_to else actor_user_id,
        assigned_by_user_id=actor_user_id,
        title=title or f"Planned coaching for {agent.full_name}",
        summary=summary,
        source_type=source_type,
        coaching_format=coaching_format,
        delivery_mode=delivery_mode,
        priority=priority,
        status="planned",
        assignment_notes=assignment_notes,
        planned_for=planned_for,
        due_at=due_at,
        planned_at=planned_for or datetime.utcnow(),
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
    session_format = (form_data.get("session_format") or "one_to_one").strip().lower()
    if session_format not in {"one_to_one", "workshop"}:
        session_format = "one_to_one"
    delivery_mode = (form_data.get("delivery_mode") or "side_by_side").strip().lower()
    if delivery_mode not in {"side_by_side", "remote"}:
        delivery_mode = "side_by_side"
    channel = (form_data.get("channel") or "call").strip()
    session_status = (form_data.get("session_status") or "completed").strip().lower()
    if session_status not in {"planned", "completed", "cancelled"}:
        session_status = "completed"
    coach_user_id = form_data.get("coach_user_id")
    assignment_notes = (form_data.get("assignment_notes") or "").strip() or None
    score_raw = (form_data.get("score") or "").strip()
    notes = (form_data.get("notes") or "").strip() or None
    subject = (form_data.get("subject") or "").strip() or None
    coach_notes = (form_data.get("coach_notes") or "").strip() or None
    action_items_raw = (form_data.get("action_items") or "").strip()
    try:
        action_due_at = _parse_iso_date(form_data.get("action_due_at"))
    except ValueError as exc:
        raise ValueError("invalid_action_due_date") from exc
    try:
        planned_start_at = _parse_iso_datetime(form_data.get("planned_start_at"))
        planned_end_at = _parse_iso_datetime(form_data.get("planned_end_at"))
    except ValueError as exc:
        raise ValueError("invalid_planned_start") from exc

    agent_q = AgentProfile.query.filter_by(id=agent_id, tenant_id=tenant_id)
    if scoped_team_ids is not None:
        agent_q = agent_q.filter(AgentProfile.team_id.in_(scoped_team_ids))
    agent = agent_q.first()
    if not agent:
        raise ValueError("invalid_agent")
    if scoped_team_ids is not None and agent.team_id not in scoped_team_ids:
        raise ValueError("team_scope_violation")
    if session_status == "planned" and not planned_start_at:
        raise ValueError("missing_planned_start")
    if planned_start_at and planned_end_at and planned_end_at <= planned_start_at:
        raise ValueError("invalid_planned_window")
    primary_coach = TenantUser.query.filter_by(
        id=coach_user_id or actor_user_id,
        tenant_id=tenant_id,
        is_active=True,
    ).first()
    if not primary_coach:
        raise ValueError("invalid_coach")
    workshop_coach_ids = _get_list(form_data, "coach_user_ids")
    participant_ids = {primary_coach.id}
    for value in workshop_coach_ids:
        value = (value or "").strip()
        if not value:
            continue
        try:
            participant_ids.add(int(value))
        except ValueError as exc:
            raise ValueError("invalid_coach") from exc
    participant_coaches = (
        TenantUser.query.filter(
            TenantUser.tenant_id == tenant_id,
            TenantUser.is_active.is_(True),
            TenantUser.id.in_(participant_ids),
        ).all()
        if participant_ids
        else []
    )
    if len(participant_coaches) != len(participant_ids):
        raise ValueError("invalid_coach")

    score = None
    if score_raw and session_status == "completed":
        try:
            score = float(score_raw)
        except ValueError as exc:
            raise ValueError("invalid_score") from exc

    occurred_at = planned_start_at or datetime.utcnow()
    session = CoachingSession(
        tenant_id=tenant_id,
        agent_id=agent.id,
        coach_user_id=primary_coach.id,
        coaching_type=coaching_type,
        session_format=session_format,
        delivery_mode=delivery_mode,
        channel=channel,
        score=score,
        status=session_status,
        planned_start_at=planned_start_at,
        planned_end_at=planned_end_at,
        assigned_by_user_id=actor_user_id,
        assignment_notes=assignment_notes,
        occurred_at=occurred_at,
        notes=notes,
        subject=subject,
        coach_notes=coach_notes,
    )
    db.session.add(session)
    db.session.flush()
    for coach in participant_coaches:
        role = "lead" if coach.id == primary_coach.id else "co_coach"
        db.session.add(
            CoachingSessionCoach(
                tenant_id=tenant_id,
                coaching_session_id=session.id,
                coach_user_id=coach.id,
                role=role,
            )
        )
    coaching_case = ensure_case_for_session(session)
    if session_status == "planned" and can_transition(CASE_STATE_TRANSITIONS, coaching_case.status, "planned"):
        coaching_case.status = "planned"
        coaching_case.planned_at = planned_start_at or datetime.utcnow()
        coaching_case.assigned_to_user_id = primary_coach.id
        coaching_case.assigned_by_user_id = actor_user_id
        coaching_case.coaching_format = session_format
        coaching_case.delivery_mode = delivery_mode
        coaching_case.planned_for = planned_start_at
        if planned_start_at and not coaching_case.due_at:
            coaching_case.due_at = planned_start_at
    if session_status == "completed" and can_transition(CASE_STATE_TRANSITIONS, coaching_case.status, "completed"):
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
            event_type="coaching_session.planned" if session_status == "planned" else "coaching_session.submitted",
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

