from ..models import AgentProfile, CoachingSession, Team


def _score_values_for_sessions(sessions):
    return [float(session.score) for session in sessions if session.score is not None]


def _avg(values):
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def build_quality_risk_rows(*, tenant_id, scoped_team_ids=None, recent_window=3, baseline_window=3):
    agents_q = AgentProfile.query.filter_by(tenant_id=tenant_id)
    if scoped_team_ids is not None:
        agents_q = agents_q.filter(AgentProfile.team_id.in_(scoped_team_ids))
    agents = agents_q.order_by(AgentProfile.full_name.asc()).all()

    rows = []
    for agent in agents:
        sessions = (
            CoachingSession.query.filter_by(tenant_id=tenant_id, agent_id=agent.id)
            .filter(CoachingSession.score.isnot(None))
            .order_by(CoachingSession.occurred_at.desc())
            .limit(recent_window + baseline_window)
            .all()
        )
        recent_scores = _score_values_for_sessions(sessions[:recent_window])
        baseline_scores = _score_values_for_sessions(sessions[recent_window : recent_window + baseline_window])
        recent_avg = _avg(recent_scores)
        baseline_avg = _avg(baseline_scores)
        trend_delta = None
        risk_status = "stable"
        if recent_avg is None:
            risk_status = "no_signal"
        elif baseline_avg is None:
            risk_status = "watch"
        else:
            trend_delta = round(recent_avg - baseline_avg, 2)
            if trend_delta <= -10:
                risk_status = "critical_drop"
            elif trend_delta <= -5:
                risk_status = "declining"
            elif trend_delta >= 5:
                risk_status = "improving"
            else:
                risk_status = "stable"
        rows.append(
            {
                "agent": agent,
                "session_count": len(sessions),
                "recent_avg": recent_avg,
                "baseline_avg": baseline_avg,
                "trend_delta": trend_delta,
                "risk_status": risk_status,
            }
        )
    priority = {
        "critical_drop": 0,
        "declining": 1,
        "watch": 2,
        "stable": 3,
        "improving": 4,
        "no_signal": 5,
    }
    rows.sort(key=lambda row: (priority.get(row["risk_status"], 99), row["agent"].full_name.lower()))
    return rows


def build_team_quality_rows(*, tenant_id, scoped_team_ids=None, recent_window=5):
    teams_q = Team.query.filter_by(tenant_id=tenant_id)
    if scoped_team_ids is not None:
        teams_q = teams_q.filter(Team.id.in_(scoped_team_ids))
    teams = teams_q.order_by(Team.name.asc()).all()

    rows = []
    for team in teams:
        agent_ids = [agent.id for agent in AgentProfile.query.filter_by(tenant_id=tenant_id, team_id=team.id).all()]
        sessions = (
            CoachingSession.query.filter(CoachingSession.tenant_id == tenant_id, CoachingSession.agent_id.in_(agent_ids) if agent_ids else False)
            .filter(CoachingSession.score.isnot(None))
            .order_by(CoachingSession.occurred_at.desc())
            .limit(recent_window)
            .all()
        )
        scores = _score_values_for_sessions(sessions)
        rows.append(
            {
                "team": team,
                "recent_avg": _avg(scores),
                "session_count": len(scores),
            }
        )
    rows.sort(key=lambda row: (row["recent_avg"] is None, -(row["recent_avg"] or 0), row["team"].name.lower()))
    return rows
