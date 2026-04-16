from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..extensions import db
from ..models import CoachingCase, CoachingSession


OPEN_CASE_STATUSES = {"open", "planned", "in_progress", "follow_up"}


def ensure_case_for_session(session: CoachingSession) -> CoachingCase:
    if session.coaching_case_id and session.coaching_case:
        return session.coaching_case

    case = CoachingCase(
        tenant_id=session.tenant_id,
        team_id=session.agent.team_id if session.agent else None,
        agent_id=session.agent_id,
        requested_by_user_id=session.coach_id,
        assigned_to_user_id=session.coach_id,
        title=f"Coaching review for {session.agent.full_name if session.agent else 'member'}",
        summary=session.notes,
        source_type="ad_hoc",
        priority="normal",
        status="completed",
        completed_at=session.occurred_at,
    )
    db.session.add(case)
    db.session.flush()
    session.coaching_case_id = case.id
    return case


def create_planned_case(*, tenant_id, agent, requested_by_user_id=None, assigned_to_user_id=None, title=None, summary=None, source_type="manager_assigned", priority="normal", due_at=None) -> CoachingCase:
    case = CoachingCase(
        tenant_id=tenant_id,
        team_id=agent.team_id if agent else None,
        agent_id=agent.id,
        requested_by_user_id=requested_by_user_id,
        assigned_to_user_id=assigned_to_user_id,
        title=title or f"Planned coaching for {agent.full_name}",
        summary=summary,
        source_type=source_type,
        priority=priority,
        status="planned",
        due_at=due_at,
    )
    db.session.add(case)
    db.session.flush()
    return case


def mark_case_completed(case: CoachingCase, *, completed_at=None, summary=None) -> CoachingCase:
    case.status = "completed"
    case.completed_at = completed_at or datetime.now(timezone.utc)
    if summary:
        case.summary = summary
    return case


def build_case_summary(case_rows):
    summary = {
        "open": 0,
        "planned": 0,
        "in_progress": 0,
        "follow_up": 0,
        "completed": 0,
        "due_soon": 0,
        "overdue": 0,
    }
    now = datetime.now(timezone.utc)
    due_soon_cutoff = now + timedelta(days=7)
    for case in case_rows:
        summary[case.status] = summary.get(case.status, 0) + 1
        if case.status in OPEN_CASE_STATUSES and case.due_at:
            due_at = case.due_at if case.due_at.tzinfo else case.due_at.replace(tzinfo=timezone.utc)
            if due_at < now:
                summary["overdue"] += 1
            elif due_at <= due_soon_cutoff:
                summary["due_soon"] += 1
    return summary
