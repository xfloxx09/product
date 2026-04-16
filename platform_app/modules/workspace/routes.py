from datetime import datetime

from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import case, func

from ...application.coaching_ops import (
    create_planned_case_from_form,
    create_session_from_form,
    session_action_completion_map,
)
from ...extensions import db
from ...models import (
    AgentCoachingCadence,
    AgentProfile,
    CoachingActionItem,
    CoachingCase,
    CoachingSession,
    DataSource,
    Team,
    TenantUser,
    UserInvitation,
)
from ...services.audit import log_audit_event
from ...services.coaching_workflow import build_case_summary
from ...services.coaching_sla import build_agent_sla_rows, cadence_map_for_agents
from ...services.mailer import send_action_item_reminder_email
from ...services.plan_catalog import build_usage_snapshot, evaluate_limit, get_plan_definition
from ...services.quality_insights import build_quality_risk_rows, build_team_quality_rows
from ...services.rbac import list_effective_roles_for_tenant, role_key_exists_for_tenant
from ...services.team_scope import get_team_scope_map_for_users, get_user_team_scope_ids, replace_user_team_scope
from ...services.tenant_context import permission_required, tenant_required


bp = Blueprint("workspace", __name__, url_prefix="/workspace")


@bp.route("/coaching-ops", methods=["GET", "POST"])
@login_required
@tenant_required
@permission_required("workspace.view")
def coaching_ops_hub():
    tenant = g.current_tenant or current_user.tenant
    scoped_team_ids = get_user_team_scope_ids(current_user)

    if request.method == "POST":
        if not role_key_exists_for_tenant(tenant.id, current_user.role) and current_user.role != "owner":
            flash("Your role is no longer valid for workflow changes.", "danger")
            return redirect(url_for("workspace.coaching_ops_hub", tenant=tenant.slug))
        try:
            coaching_case = create_planned_case_from_form(
                tenant_id=tenant.id,
                actor_user_id=current_user.id,
                form_data=request.form,
                scoped_team_ids=scoped_team_ids,
            )
        except ValueError as exc:
            if str(exc) == "invalid_agent":
                flash("Invalid agent for coaching case.", "danger")
            elif str(exc) == "team_scope_violation":
                flash("You can only create coaching cases for your assigned teams.", "danger")
            else:
                flash("Target date must use YYYY-MM-DD format.", "danger")
            return redirect(url_for("workspace.coaching_ops_hub", tenant=tenant.slug))
        log_audit_event(
            tenant.id,
            "workspace.coaching_case_created",
            {
                "case_id": coaching_case.id,
                "agent_id": coaching_case.agent_id,
                "source_type": coaching_case.source_type,
                "priority": coaching_case.priority,
            },
            actor_user_id=current_user.id,
        )
        db.session.commit()
        flash("Coaching case created.", "success")
        return redirect(url_for("workspace.coaching_ops_hub", tenant=tenant.slug))

    agents_q = AgentProfile.query.filter_by(tenant_id=tenant.id, status="active")
    cases_q = CoachingCase.query.filter_by(tenant_id=tenant.id)
    sessions_q = CoachingSession.query.filter_by(tenant_id=tenant.id)
    actions_q = CoachingActionItem.query.filter_by(tenant_id=tenant.id)
    if scoped_team_ids is not None:
        agents_q = agents_q.filter(AgentProfile.team_id.in_(scoped_team_ids))
        cases_q = cases_q.join(AgentProfile, AgentProfile.id == CoachingCase.agent_id).filter(
            AgentProfile.team_id.in_(scoped_team_ids)
        )
        sessions_q = sessions_q.join(AgentProfile, AgentProfile.id == CoachingSession.agent_id).filter(
            AgentProfile.team_id.in_(scoped_team_ids)
        )
        actions_q = actions_q.join(CoachingSession, CoachingSession.id == CoachingActionItem.coaching_session_id).join(
            AgentProfile, AgentProfile.id == CoachingSession.agent_id
        ).filter(AgentProfile.team_id.in_(scoped_team_ids))

    case_rows = cases_q.order_by(
        case((CoachingCase.status == "open", 0), (CoachingCase.status == "planned", 1), else_=2),
        CoachingCase.due_at.asc().nullslast(),
        CoachingCase.created_at.desc(),
    ).limit(40).all()
    case_summary = build_case_summary(case_rows)
    sessions = sessions_q.order_by(CoachingSession.occurred_at.desc()).limit(12).all()
    open_actions = actions_q.filter(CoachingActionItem.status == "open").order_by(
        CoachingActionItem.due_at.asc().nullslast(), CoachingActionItem.created_at.desc()
    ).limit(12).all()
    sla_rows = build_agent_sla_rows(tenant_id=tenant.id, scoped_team_ids=scoped_team_ids)[:8]
    quality_rows = build_quality_risk_rows(tenant_id=tenant.id, scoped_team_ids=scoped_team_ids)[:8]
    agents = agents_q.order_by(AgentProfile.full_name.asc()).all()

    return render_template(
        "workspace/coaching_ops_hub.html",
        tenant=tenant,
        agents=agents,
        case_rows=case_rows,
        case_summary=case_summary,
        sessions=sessions,
        open_actions=open_actions,
        sla_rows=sla_rows,
        quality_rows=quality_rows,
    )


@bp.get("/dashboard")
@login_required
@permission_required("workspace.view")
def dashboard():
    tenant = current_user.tenant
    scoped_team_ids = get_user_team_scope_ids(current_user)
    agents_q = AgentProfile.query.filter_by(tenant_id=tenant.id)
    sessions_q = CoachingSession.query.filter_by(tenant_id=tenant.id)
    teams_q = Team.query.filter_by(tenant_id=tenant.id)
    sources_q = DataSource.query.filter_by(tenant_id=tenant.id, is_active=True)
    if scoped_team_ids is not None:
        agents_q = agents_q.filter(AgentProfile.team_id.in_(scoped_team_ids))
        teams_q = teams_q.filter(Team.id.in_(scoped_team_ids))
        sessions_q = sessions_q.join(AgentProfile, AgentProfile.id == CoachingSession.agent_id).filter(
            AgentProfile.team_id.in_(scoped_team_ids)
        )
    total_agents = agents_q.count()
    total_sessions = sessions_q.count()
    avg_score = (
        db.session.query(func.avg(CoachingSession.score))
        .join(AgentProfile, AgentProfile.id == CoachingSession.agent_id)
        .filter(CoachingSession.tenant_id == tenant.id, CoachingSession.score.isnot(None))
        .filter(AgentProfile.team_id.in_(scoped_team_ids) if scoped_team_ids is not None else True)
        .scalar()
    )
    team_count = teams_q.count()
    unhealthy_sources = sources_q.filter_by(health_status="unhealthy").count()
    degraded_sources = sources_q.filter_by(health_status="degraded").count()
    recent_sessions = (
        sessions_q
        .order_by(CoachingSession.occurred_at.desc())
        .limit(10)
        .all()
    )
    team_performance_rows = (
        db.session.query(
            Team.id.label("team_id"),
            Team.name.label("team_name"),
            func.count(CoachingSession.id).label("session_count"),
            func.avg(CoachingSession.score).label("avg_score"),
            func.count(AgentProfile.id.distinct()).label("agent_count"),
        )
        .join(AgentProfile, AgentProfile.team_id == Team.id)
        .outerjoin(CoachingSession, CoachingSession.agent_id == AgentProfile.id)
        .filter(Team.tenant_id == tenant.id)
        .filter(Team.id.in_(scoped_team_ids) if scoped_team_ids is not None else True)
        .group_by(Team.id, Team.name)
        .order_by(func.avg(CoachingSession.score).desc().nullslast(), Team.name.asc())
        .limit(12)
        .all()
    )
    quality_risk_rows = build_quality_risk_rows(tenant_id=tenant.id, scoped_team_ids=scoped_team_ids)
    critical_quality_count = len([row for row in quality_risk_rows if row["risk_status"] == "critical_drop"])
    declining_quality_count = len([row for row in quality_risk_rows if row["risk_status"] == "declining"])
    sla_rows = build_agent_sla_rows(tenant_id=tenant.id, scoped_team_ids=scoped_team_ids)
    overdue_coaching_count = len([row for row in sla_rows if row["status"] == "overdue"])
    never_coached_count = len([row for row in sla_rows if row["status"] == "never_coached"])
    plan_definition = get_plan_definition(tenant.plan)
    usage = build_usage_snapshot(tenant)
    active_members_limit = evaluate_limit(tenant.plan, "active_members", usage["active_members"])

    return render_template(
        "workspace/dashboard.html",
        tenant=tenant,
        total_agents=total_agents,
        total_sessions=total_sessions,
        avg_score=round(avg_score, 2) if avg_score is not None else None,
        team_count=team_count,
        unhealthy_sources=unhealthy_sources,
        degraded_sources=degraded_sources,
        recent_sessions=recent_sessions,
        team_performance_rows=team_performance_rows,
        plan_definition=plan_definition,
        usage=usage,
        active_members_limit=active_members_limit,
        scoped_team_ids=scoped_team_ids,
        overdue_coaching_count=overdue_coaching_count,
        never_coached_count=never_coached_count,
        critical_quality_count=critical_quality_count,
        declining_quality_count=declining_quality_count,
    )


@bp.route("/teams", methods=["GET", "POST"])
@login_required
@permission_required("workspace.manage_teams")
def manage_teams():
    tenant = current_user.tenant
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        manager_name = (request.form.get("manager_name") or "").strip() or None
        if not name:
            flash("Team name is required.", "danger")
            return redirect(url_for("workspace.manage_teams"))

        exists = Team.query.filter_by(tenant_id=tenant.id, name=name).first()
        if exists:
            flash("Team already exists.", "warning")
            return redirect(url_for("workspace.manage_teams"))

        db.session.add(Team(tenant_id=tenant.id, name=name, manager_name=manager_name))
        log_audit_event(
            tenant.id,
            "workspace.team_created",
            {"name": name, "manager_name": manager_name},
            actor_user_id=current_user.id,
        )
        db.session.commit()
        flash("Team created.", "success")
        return redirect(url_for("workspace.manage_teams"))

    teams = Team.query.filter_by(tenant_id=tenant.id).order_by(Team.name.asc()).all()
    return render_template("workspace/teams.html", teams=teams, tenant=tenant)


@bp.route("/agents", methods=["GET", "POST"])
@login_required
@permission_required("workspace.manage_agents")
def manage_agents():
    tenant = current_user.tenant
    scoped_team_ids = get_user_team_scope_ids(current_user)
    if request.method == "POST":
        action = (request.form.get("action") or "create_agent").strip().lower()
        if action == "toggle_status":
            agent_id = request.form.get("agent_id")
            desired_status = (request.form.get("desired_status") or "").strip().lower()
            if desired_status not in {"active", "inactive"}:
                flash("Invalid status action.", "danger")
                return redirect(url_for("workspace.manage_agents"))

            agent = AgentProfile.query.filter_by(id=agent_id, tenant_id=tenant.id).first()
            if not agent:
                flash("Agent not found.", "danger")
                return redirect(url_for("workspace.manage_agents"))
            if scoped_team_ids is not None and (not agent.team_id or agent.team_id not in scoped_team_ids):
                flash("You can only manage agents from your assigned teams.", "danger")
                return redirect(url_for("workspace.manage_agents"))
            if agent.status == desired_status:
                flash("Agent already has that status.", "info")
                return redirect(url_for("workspace.manage_agents"))
            if desired_status == "active":
                usage = build_usage_snapshot(tenant)
                active_members_limit = evaluate_limit(tenant.plan, "active_members", usage["active_members"])
                if not active_members_limit["allowed"]:
                    flash(
                        "Active member limit reached for your current plan. Upgrade plan to activate more members.",
                        "warning",
                    )
                    return redirect(url_for("workspace.manage_agents"))

            agent.status = desired_status
            log_audit_event(
                tenant.id,
                "workspace.agent_status_updated",
                {"agent_id": agent.id, "employee_code": agent.employee_code, "status": desired_status},
                actor_user_id=current_user.id,
            )
            db.session.commit()
            flash("Agent status updated.", "success")
            return redirect(url_for("workspace.manage_agents"))
        if action == "set_cadence":
            agent_id = request.form.get("agent_id")
            cadence_raw = (request.form.get("cadence_days") or "").strip()
            try:
                cadence_days = max(1, int(cadence_raw))
            except ValueError:
                flash("Cadence days must be a valid number.", "danger")
                return redirect(url_for("workspace.manage_agents"))
            agent = AgentProfile.query.filter_by(id=agent_id, tenant_id=tenant.id).first()
            if not agent:
                flash("Agent not found.", "danger")
                return redirect(url_for("workspace.manage_agents"))
            if scoped_team_ids is not None and (not agent.team_id or agent.team_id not in scoped_team_ids):
                flash("You can only manage agents from your assigned teams.", "danger")
                return redirect(url_for("workspace.manage_agents"))
            cadence = AgentCoachingCadence.query.filter_by(tenant_id=tenant.id, agent_id=agent.id).first()
            if not cadence:
                cadence = AgentCoachingCadence(tenant_id=tenant.id, agent_id=agent.id)
                db.session.add(cadence)
            cadence.cadence_days = cadence_days
            log_audit_event(
                tenant.id,
                "workspace.agent_cadence_updated",
                {"agent_id": agent.id, "employee_code": agent.employee_code, "cadence_days": cadence_days},
                actor_user_id=current_user.id,
            )
            db.session.commit()
            flash("Coaching cadence updated.", "success")
            return redirect(url_for("workspace.manage_agents"))

        usage = build_usage_snapshot(tenant)
        active_members_limit = evaluate_limit(tenant.plan, "active_members", usage["active_members"])
        if not active_members_limit["allowed"]:
            flash(
                "Active member limit reached for your current plan. Upgrade plan to activate more members.",
                "warning",
            )
            return redirect(url_for("workspace.manage_agents"))

        full_name = (request.form.get("full_name") or "").strip()
        employee_code = (request.form.get("employee_code") or "").strip()
        team_id = request.form.get("team_id")
        if not full_name or not employee_code:
            flash("Agent name and code are required.", "danger")
            return redirect(url_for("workspace.manage_agents"))

        team = None
        if team_id:
            team = Team.query.filter_by(id=team_id, tenant_id=tenant.id).first()
            if not team:
                flash("Invalid team selected.", "danger")
                return redirect(url_for("workspace.manage_agents"))
            if scoped_team_ids is not None and team.id not in scoped_team_ids:
                flash("You can only create agents inside your assigned teams.", "danger")
                return redirect(url_for("workspace.manage_agents"))
        elif scoped_team_ids is not None:
            flash("Please select one of your assigned teams.", "danger")
            return redirect(url_for("workspace.manage_agents"))

        db.session.add(
            AgentProfile(
                tenant_id=tenant.id,
                full_name=full_name,
                employee_code=employee_code,
                team_id=team.id if team else None,
            )
        )
        log_audit_event(
            tenant.id,
            "workspace.agent_created",
            {"full_name": full_name, "employee_code": employee_code},
            actor_user_id=current_user.id,
        )
        db.session.commit()
        flash("Agent created.", "success")
        return redirect(url_for("workspace.manage_agents"))

    agents_q = AgentProfile.query.filter_by(tenant_id=tenant.id)
    teams_q = Team.query.filter_by(tenant_id=tenant.id)
    if scoped_team_ids is not None:
        agents_q = agents_q.filter(AgentProfile.team_id.in_(scoped_team_ids))
        teams_q = teams_q.filter(Team.id.in_(scoped_team_ids))
    agents = agents_q.order_by(AgentProfile.full_name.asc()).all()
    teams = teams_q.order_by(Team.name.asc()).all()
    usage = build_usage_snapshot(tenant)
    active_members_limit = evaluate_limit(tenant.plan, "active_members", usage["active_members"])
    cadence_rows = cadence_map_for_agents(tenant.id, [agent.id for agent in agents])
    return render_template(
        "workspace/agents.html",
        agents=agents,
        teams=teams,
        tenant=tenant,
        active_members_limit=active_members_limit,
        cadence_rows=cadence_rows,
    )


@bp.route("/sessions", methods=["GET", "POST"])
@login_required
@tenant_required
@permission_required("workspace.manage_sessions")
def manage_sessions():
    tenant = g.current_tenant or current_user.tenant
    scoped_team_ids = get_user_team_scope_ids(current_user)
    if tenant.id != current_user.tenant_id:
        flash("Cross-tenant access is blocked.", "danger")
        return redirect(url_for("workspace.dashboard"))

    if request.method == "POST":
        try:
            session, coaching_case, action_count = create_session_from_form(
                tenant_id=tenant.id,
                actor_user_id=current_user.id,
                form_data=request.form,
                scoped_team_ids=scoped_team_ids,
            )
        except ValueError as exc:
            if str(exc) == "invalid_agent":
                flash("Invalid agent.", "danger")
            elif str(exc) == "team_scope_violation":
                flash("You can only create sessions for your assigned teams.", "danger")
            elif str(exc) == "invalid_score":
                flash("Score must be a number.", "danger")
            else:
                flash("Action due date must use YYYY-MM-DD format.", "danger")
            return redirect(url_for("workspace.manage_sessions", tenant=tenant.slug))
        log_audit_event(
            tenant.id,
            "workspace.session_created",
            {
                "session_id": session.id,
                "agent_id": agent.id,
                "case_id": coaching_case.id,
                "coaching_type": session.coaching_type,
                "channel": session.channel,
                "score": session.score,
                "action_item_count": action_count,
            },
            actor_user_id=current_user.id,
        )
        db.session.commit()
        flash("Coaching session saved.", "success")
        return redirect(url_for("workspace.manage_sessions", tenant=tenant.slug))

    sessions_q = CoachingSession.query.filter_by(tenant_id=tenant.id)
    agents_q = AgentProfile.query.filter_by(tenant_id=tenant.id)
    if scoped_team_ids is not None:
        agents_q = agents_q.filter(AgentProfile.team_id.in_(scoped_team_ids))
        sessions_q = sessions_q.join(AgentProfile, AgentProfile.id == CoachingSession.agent_id).filter(
            AgentProfile.team_id.in_(scoped_team_ids)
        )
    sessions = sessions_q.order_by(CoachingSession.occurred_at.desc()).limit(30).all()
    agents = agents_q.order_by(AgentProfile.full_name.asc()).all()
    session_ids = [session.id for session in sessions]
    session_action_summary = session_action_completion_map(tenant_id=tenant.id, session_ids=session_ids)
    return render_template(
        "workspace/sessions.html",
        sessions=sessions,
        agents=agents,
        tenant=tenant,
        session_action_summary=session_action_summary,
    )


@bp.route("/sessions/<int:session_id>", methods=["GET", "POST"])
@login_required
@tenant_required
@permission_required("workspace.manage_sessions")
def session_detail(session_id):
    tenant = g.current_tenant or current_user.tenant
    scoped_team_ids = get_user_team_scope_ids(current_user)
    session_q = CoachingSession.query.filter_by(id=session_id, tenant_id=tenant.id)
    if scoped_team_ids is not None:
        session_q = session_q.join(AgentProfile, AgentProfile.id == CoachingSession.agent_id).filter(
            AgentProfile.team_id.in_(scoped_team_ids)
        )
    session = session_q.first_or_404()

    if request.method == "POST":
        action = (request.form.get("action") or "").strip().lower()
        if action == "add_action_item":
            title = (request.form.get("title") or "").strip()
            due_raw = (request.form.get("due_at") or "").strip()
            if not title:
                flash("Action item title is required.", "danger")
                return redirect(url_for("workspace.session_detail", session_id=session.id, tenant=tenant.slug))
            due_at = None
            if due_raw:
                try:
                    due_at = datetime.strptime(due_raw, "%Y-%m-%d")
                except ValueError:
                    flash("Due date must use YYYY-MM-DD format.", "danger")
                    return redirect(url_for("workspace.session_detail", session_id=session.id, tenant=tenant.slug))
            db.session.add(
                CoachingActionItem(
                    tenant_id=tenant.id,
                    coaching_session_id=session.id,
                    owner_user_id=current_user.id,
                    title=title[:255],
                    due_at=due_at,
                )
            )
            log_audit_event(
                tenant.id,
                "workspace.session_action_item_added",
                {"session_id": session.id, "title": title[:255]},
                actor_user_id=current_user.id,
            )
            db.session.commit()
            flash("Action item added.", "success")
            return redirect(url_for("workspace.session_detail", session_id=session.id, tenant=tenant.slug))
        if action == "toggle_action_status":
            item_id = request.form.get("item_id")
            item = CoachingActionItem.query.filter_by(
                id=item_id,
                tenant_id=tenant.id,
                coaching_session_id=session.id,
            ).first()
            if not item:
                flash("Action item not found.", "danger")
                return redirect(url_for("workspace.session_detail", session_id=session.id, tenant=tenant.slug))
            if item.status == "completed":
                item.status = "open"
                item.completed_at = None
            else:
                item.status = "completed"
                item.completed_at = datetime.utcnow()
            log_audit_event(
                tenant.id,
                "workspace.session_action_item_status_changed",
                {"session_id": session.id, "item_id": item.id, "status": item.status},
                actor_user_id=current_user.id,
            )
            db.session.commit()
            flash("Action item updated.", "success")
            return redirect(url_for("workspace.session_detail", session_id=session.id, tenant=tenant.slug))
        if action == "send_reminder":
            item_id = request.form.get("item_id")
            item = CoachingActionItem.query.filter_by(
                id=item_id,
                tenant_id=tenant.id,
                coaching_session_id=session.id,
            ).first()
            if not item:
                flash("Action item not found.", "danger")
                return redirect(url_for("workspace.session_detail", session_id=session.id, tenant=tenant.slug))
            if not item.owner or not item.owner.email:
                flash("No action owner email is available for reminders.", "warning")
                return redirect(url_for("workspace.session_detail", session_id=session.id, tenant=tenant.slug))
            try:
                send_action_item_reminder_email(
                    to_email=item.owner.email,
                    recipient_name=item.owner.full_name,
                    workspace_slug=tenant.slug,
                    session_agent_name=session.agent.full_name,
                    action_title=item.title,
                    due_at=item.due_at.strftime("%Y-%m-%d") if item.due_at else None,
                )
                log_audit_event(
                    tenant.id,
                    "workspace.session_action_item_reminder_sent",
                    {"session_id": session.id, "item_id": item.id},
                    actor_user_id=current_user.id,
                )
                db.session.commit()
                flash("Reminder sent.", "success")
            except Exception as exc:
                flash(f"Reminder failed: {exc}", "danger")
            return redirect(url_for("workspace.session_detail", session_id=session.id, tenant=tenant.slug))

    action_items = (
        CoachingActionItem.query.filter_by(tenant_id=tenant.id, coaching_session_id=session.id)
        .order_by(CoachingActionItem.created_at.desc())
        .all()
    )
    return render_template("workspace/session_detail.html", tenant=tenant, session=session, action_items=action_items)


@bp.get("/actions")
@login_required
@permission_required("workspace.manage_sessions")
def action_dashboard():
    tenant = current_user.tenant
    scoped_team_ids = get_user_team_scope_ids(current_user)
    status_filter = (request.args.get("status") or "open").strip().lower()
    if status_filter not in {"open", "overdue", "completed", "all"}:
        status_filter = "open"

    actions_q = CoachingActionItem.query.filter_by(tenant_id=tenant.id).join(
        CoachingSession, CoachingSession.id == CoachingActionItem.coaching_session_id
    ).join(
        AgentProfile, AgentProfile.id == CoachingSession.agent_id
    )
    if scoped_team_ids is not None:
        actions_q = actions_q.filter(AgentProfile.team_id.in_(scoped_team_ids))

    now = datetime.utcnow()
    if status_filter == "open":
        actions_q = actions_q.filter(CoachingActionItem.status == "open")
    elif status_filter == "completed":
        actions_q = actions_q.filter(CoachingActionItem.status == "completed")
    elif status_filter == "overdue":
        actions_q = actions_q.filter(
            CoachingActionItem.status == "open",
            CoachingActionItem.due_at.isnot(None),
            CoachingActionItem.due_at < now,
        )

    actions = actions_q.order_by(
        CoachingActionItem.due_at.asc().nulls_last(),
        CoachingActionItem.created_at.desc(),
    ).limit(100).all()

    summary_q = CoachingActionItem.query.filter_by(tenant_id=tenant.id).join(
        CoachingSession, CoachingSession.id == CoachingActionItem.coaching_session_id
    ).join(
        AgentProfile, AgentProfile.id == CoachingSession.agent_id
    )
    if scoped_team_ids is not None:
        summary_q = summary_q.filter(AgentProfile.team_id.in_(scoped_team_ids))
    open_count = summary_q.filter(CoachingActionItem.status == "open").count()
    completed_count = summary_q.filter(CoachingActionItem.status == "completed").count()
    overdue_count = summary_q.filter(
        CoachingActionItem.status == "open",
        CoachingActionItem.due_at.isnot(None),
        CoachingActionItem.due_at < now,
    ).count()

    return render_template(
        "workspace/actions.html",
        tenant=tenant,
        actions=actions,
        status_filter=status_filter,
        open_count=open_count,
        completed_count=completed_count,
        overdue_count=overdue_count,
    )


@bp.get("/coaching-sla")
@login_required
@permission_required("workspace.view")
def coaching_sla_dashboard():
    tenant = current_user.tenant
    scoped_team_ids = get_user_team_scope_ids(current_user)
    status_filter = (request.args.get("status") or "overdue").strip().lower()
    if status_filter not in {"overdue", "never_coached", "on_track", "inactive", "all"}:
        status_filter = "overdue"
    all_rows = build_agent_sla_rows(tenant_id=tenant.id, scoped_team_ids=scoped_team_ids)
    rows = all_rows if status_filter == "all" else [row for row in all_rows if row["status"] == status_filter]
    summary = {
        "overdue": len([row for row in all_rows if row["status"] == "overdue"]),
        "never_coached": len([row for row in all_rows if row["status"] == "never_coached"]),
        "on_track": len([row for row in all_rows if row["status"] == "on_track"]),
        "inactive": len([row for row in all_rows if row["status"] == "inactive"]),
    }
    return render_template(
        "workspace/coaching_sla.html",
        tenant=tenant,
        rows=rows,
        status_filter=status_filter,
        summary=summary,
    )


@bp.get("/quality-insights")
@login_required
@permission_required("workspace.view")
def quality_insights_dashboard():
    tenant = current_user.tenant
    scoped_team_ids = get_user_team_scope_ids(current_user)
    status_filter = (request.args.get("status") or "all").strip().lower()
    if status_filter not in {"critical_drop", "declining", "watch", "stable", "improving", "no_signal", "all"}:
        status_filter = "all"
    risk_rows = build_quality_risk_rows(tenant_id=tenant.id, scoped_team_ids=scoped_team_ids)
    if status_filter != "all":
        risk_rows = [row for row in risk_rows if row["risk_status"] == status_filter]
    summary_source = build_quality_risk_rows(tenant_id=tenant.id, scoped_team_ids=scoped_team_ids)
    summary = {
        "critical_drop": len([row for row in summary_source if row["risk_status"] == "critical_drop"]),
        "declining": len([row for row in summary_source if row["risk_status"] == "declining"]),
        "watch": len([row for row in summary_source if row["risk_status"] == "watch"]),
        "stable": len([row for row in summary_source if row["risk_status"] == "stable"]),
        "improving": len([row for row in summary_source if row["risk_status"] == "improving"]),
    }
    team_rows = build_team_quality_rows(tenant_id=tenant.id, scoped_team_ids=scoped_team_ids)
    return render_template(
        "workspace/quality_insights.html",
        tenant=tenant,
        risk_rows=risk_rows,
        status_filter=status_filter,
        summary=summary,
        team_rows=team_rows,
    )


@bp.get("/teams/<int:team_id>/dashboard")
@login_required
@permission_required("workspace.view")
def team_dashboard(team_id):
    tenant = current_user.tenant
    scoped_team_ids = get_user_team_scope_ids(current_user)
    if scoped_team_ids is not None and team_id not in scoped_team_ids:
        flash("You do not have access to that team dashboard.", "danger")
        return redirect(url_for("workspace.dashboard"))

    team = Team.query.filter_by(id=team_id, tenant_id=tenant.id).first_or_404()
    agents = AgentProfile.query.filter_by(tenant_id=tenant.id, team_id=team.id).order_by(AgentProfile.full_name.asc()).all()
    agent_ids = [agent.id for agent in agents]
    sessions_q = CoachingSession.query.filter(
        CoachingSession.tenant_id == tenant.id,
        CoachingSession.agent_id.in_(agent_ids) if agent_ids else False,
    )
    total_sessions = sessions_q.count()
    avg_score = (
        db.session.query(func.avg(CoachingSession.score))
        .filter(
            CoachingSession.tenant_id == tenant.id,
            CoachingSession.agent_id.in_(agent_ids) if agent_ids else False,
            CoachingSession.score.isnot(None),
        )
        .scalar()
    )
    recent_sessions = sessions_q.order_by(CoachingSession.occurred_at.desc()).limit(15).all()
    active_agents = [agent for agent in agents if agent.status == "active"]
    sla_rows = build_agent_sla_rows(tenant_id=tenant.id, scoped_team_ids={team.id})
    quality_rows = build_quality_risk_rows(tenant_id=tenant.id, scoped_team_ids={team.id})

    return render_template(
        "workspace/team_dashboard.html",
        tenant=tenant,
        team=team,
        agents=agents,
        active_agents=active_agents,
        total_sessions=total_sessions,
        avg_score=round(avg_score, 2) if avg_score is not None else None,
        recent_sessions=recent_sessions,
        sla_rows=sla_rows,
        quality_rows=quality_rows,
    )


@bp.route("/users", methods=["GET", "POST"])
@login_required
@permission_required("workspace.manage_users")
def manage_users():
    tenant = current_user.tenant
    if request.method == "POST":
        action = (request.form.get("action") or "").strip().lower()
        target_user_id = request.form.get("user_id")
        target = TenantUser.query.filter_by(id=target_user_id, tenant_id=tenant.id).first()
        if not target:
            flash("User not found.", "danger")
            return redirect(url_for("workspace.manage_users"))

        if action == "change_role":
            new_role = (request.form.get("new_role") or "").strip().lower()
            if not role_key_exists_for_tenant(tenant.id, new_role):
                flash("Invalid role selected.", "danger")
                return redirect(url_for("workspace.manage_users"))
            if target.id == current_user.id and new_role != target.role:
                flash("You cannot change your own role from this screen.", "warning")
                return redirect(url_for("workspace.manage_users"))
            if target.role == "owner" and new_role != "owner":
                owners_count = TenantUser.query.filter_by(tenant_id=tenant.id, role="owner", is_active=True).count()
                if owners_count <= 1:
                    flash("At least one active owner is required.", "danger")
                    return redirect(url_for("workspace.manage_users"))
            if target.role == new_role:
                flash("User already has this role.", "info")
                return redirect(url_for("workspace.manage_users"))

            old_role = target.role
            target.role = new_role
            log_audit_event(
                tenant.id,
                "workspace.user_role_changed",
                {"user_id": target.id, "email": target.email, "old_role": old_role, "new_role": new_role},
                actor_user_id=current_user.id,
            )
            db.session.commit()
            flash("User role updated.", "success")
            return redirect(url_for("workspace.manage_users"))

        if action == "set_team_scope":
            if target.id == current_user.id:
                flash("You cannot change your own delegation scope.", "warning")
                return redirect(url_for("workspace.manage_users"))
            if target.role == "owner":
                flash("Owner must keep global access scope.", "warning")
                return redirect(url_for("workspace.manage_users"))
            selected_team_ids = request.form.getlist("scope_team_ids")
            valid_team_ids = {
                str(t.id)
                for t in Team.query.filter_by(tenant_id=tenant.id)
                .filter(Team.id.in_(selected_team_ids))
                .all()
            }
            if not valid_team_ids:
                flash("Select at least one valid team or clear scope for global access.", "warning")
                return redirect(url_for("workspace.manage_users"))
            ok = replace_user_team_scope(
                tenant_id=tenant.id,
                user_id=target.id,
                team_ids=list(valid_team_ids),
            )
            if not ok:
                flash("Team scope table is not ready yet. Run DB initialization/migration first.", "danger")
                return redirect(url_for("workspace.manage_users"))
            log_audit_event(
                tenant.id,
                "workspace.user_scope_updated",
                {"user_id": target.id, "email": target.email, "team_ids": sorted(list(valid_team_ids))},
                actor_user_id=current_user.id,
            )
            db.session.commit()
            flash("User team scope updated.", "success")
            return redirect(url_for("workspace.manage_users"))

        if action == "clear_team_scope":
            if target.id == current_user.id:
                flash("You cannot change your own delegation scope.", "warning")
                return redirect(url_for("workspace.manage_users"))
            ok = replace_user_team_scope(
                tenant_id=tenant.id,
                user_id=target.id,
                team_ids=[],
            )
            if not ok:
                flash("Team scope table is not ready yet. Run DB initialization/migration first.", "danger")
                return redirect(url_for("workspace.manage_users"))
            log_audit_event(
                tenant.id,
                "workspace.user_scope_cleared",
                {"user_id": target.id, "email": target.email},
                actor_user_id=current_user.id,
            )
            db.session.commit()
            flash("User now has global team scope.", "success")
            return redirect(url_for("workspace.manage_users"))

        if action == "toggle_active":
            desired = (request.form.get("desired_active") or "").strip()
            desired_active = desired == "1"
            if target.id == current_user.id and not desired_active:
                flash("You cannot deactivate your own account.", "warning")
                return redirect(url_for("workspace.manage_users"))
            if target.role == "owner" and not desired_active:
                owners_count = TenantUser.query.filter_by(tenant_id=tenant.id, role="owner", is_active=True).count()
                if owners_count <= 1:
                    flash("At least one active owner is required.", "danger")
                    return redirect(url_for("workspace.manage_users"))
            if bool(target.is_active) == desired_active:
                flash("User already has this account status.", "info")
                return redirect(url_for("workspace.manage_users"))

            target.is_active = desired_active
            log_audit_event(
                tenant.id,
                "workspace.user_status_changed",
                {"user_id": target.id, "email": target.email, "is_active": bool(target.is_active)},
                actor_user_id=current_user.id,
            )
            db.session.commit()
            flash("User account status updated.", "success")
            return redirect(url_for("workspace.manage_users"))

        flash("Unknown action.", "danger")
        return redirect(url_for("workspace.manage_users"))

    users = TenantUser.query.filter_by(tenant_id=tenant.id).order_by(TenantUser.created_at.desc()).all()
    invites = (
        UserInvitation.query.filter_by(tenant_id=tenant.id, accepted_at=None)
        .order_by(UserInvitation.created_at.desc())
        .limit(25)
        .all()
    )
    role_definitions = list_effective_roles_for_tenant(tenant.id)
    role_labels = {r["role_key"]: r["display_name"] for r in role_definitions}
    role_options = [(r["role_key"], r["display_name"]) for r in role_definitions]
    teams = Team.query.filter_by(tenant_id=tenant.id).order_by(Team.name.asc()).all()
    scope_map = get_team_scope_map_for_users(tenant.id, [u.id for u in users])
    return render_template(
        "workspace/users.html",
        users=users,
        invites=invites,
        tenant=tenant,
        role_labels=role_labels,
        role_options=role_options,
        teams=teams,
        scope_map=scope_map,
    )
