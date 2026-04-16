from flask import Blueprint, g, jsonify, request
from flask_login import current_user, login_required

from ...application.api_queries import (
    list_action_items,
    list_agents,
    list_cases,
    list_data_source_health,
    list_import_jobs,
    list_programs,
    list_scorecards,
    list_sessions,
    list_sync_jobs,
    paginated_response,
)
from ...models import AgentProfile, CoachingSession
from ...services.audit_validation import audit_coverage_snapshot
from ...services.data_governance import governance_snapshot
from ...services.kpi_metrics import operations_kpis
from ...services.tenant_context import permission_required


bp = Blueprint("api", __name__, url_prefix="/api/v1")


@bp.get("/tenant-summary")
@login_required
@permission_required("workspace.view")
def tenant_summary():
    tenant = g.current_tenant or current_user.tenant
    if tenant.id != current_user.tenant_id:
        return jsonify({"error": "cross_tenant_blocked"}), 403

    return jsonify(
        {
            "tenant": tenant.slug,
            "agents": AgentProfile.query.filter_by(tenant_id=tenant.id).count(),
            "sessions": CoachingSession.query.filter_by(tenant_id=tenant.id).count(),
        }
    )


@bp.get("/kpi/operations")
@login_required
@permission_required("workspace.view")
def operations_kpi_view():
    tenant = g.current_tenant or current_user.tenant
    if tenant.id != current_user.tenant_id:
        return jsonify({"error": "cross_tenant_blocked"}), 403
    return jsonify({"tenant": tenant.slug, "kpis": operations_kpis(tenant_id=tenant.id)})


@bp.get("/governance/snapshot")
@login_required
@permission_required("settings.manage")
def governance_snapshot_view():
    tenant = g.current_tenant or current_user.tenant
    if tenant.id != current_user.tenant_id:
        return jsonify({"error": "cross_tenant_blocked"}), 403
    return jsonify({"tenant": tenant.slug, "governance": governance_snapshot(tenant_id=tenant.id)})


@bp.get("/governance/audit-coverage")
@login_required
@permission_required("settings.manage")
def audit_coverage_view():
    tenant = g.current_tenant or current_user.tenant
    if tenant.id != current_user.tenant_id:
        return jsonify({"error": "cross_tenant_blocked"}), 403
    return jsonify({"tenant": tenant.slug, "audit_coverage": audit_coverage_snapshot(tenant_id=tenant.id)})


@bp.get("/coaching-sessions")
@login_required
@permission_required("workspace.view")
def coaching_sessions():
    tenant = g.current_tenant or current_user.tenant
    if tenant.id != current_user.tenant_id:
        return jsonify({"error": "cross_tenant_blocked"}), 403

    total, limit, offset, rows = list_sessions(tenant_id=tenant.id, args=request.args)
    items = [
        {
            "id": r.id,
            "agent_id": r.agent_id,
            "agent": r.agent.full_name,
            "coach_id": r.coach_user_id,
            "coach": r.coach.full_name,
            "type": r.coaching_type,
            "channel": r.channel,
            "subject": r.subject,
            "score": r.score,
            "occurred_at": r.occurred_at.isoformat(),
        }
        for r in rows
    ]
    return jsonify(
        paginated_response(
            request=request,
            tenant_slug=tenant.slug,
            total=total,
            limit=limit,
            offset=offset,
            items=items,
        )
    )


@bp.get("/agents")
@login_required
@permission_required("workspace.view")
def agents():
    tenant = g.current_tenant or current_user.tenant
    if tenant.id != current_user.tenant_id:
        return jsonify({"error": "cross_tenant_blocked"}), 403
    total, limit, offset, rows = list_agents(tenant_id=tenant.id, args=request.args)
    return jsonify(
        paginated_response(
            request=request,
            tenant_slug=tenant.slug,
            total=total,
            limit=limit,
            offset=offset,
            items=[
                {
                    "id": row.id,
                    "employee_code": row.employee_code,
                    "full_name": row.full_name,
                    "status": row.status,
                    "team_id": row.team_id,
                    "program_id": row.program_id,
                    "skill_profile_id": row.skill_profile_id,
                }
                for row in rows
            ],
        )
    )


@bp.get("/coaching-cases")
@login_required
@permission_required("workspace.view")
def coaching_cases():
    tenant = g.current_tenant or current_user.tenant
    if tenant.id != current_user.tenant_id:
        return jsonify({"error": "cross_tenant_blocked"}), 403
    total, limit, offset, rows = list_cases(tenant_id=tenant.id, args=request.args)
    return jsonify(
        paginated_response(
            request=request,
            tenant_slug=tenant.slug,
            total=total,
            limit=limit,
            offset=offset,
            items=[
                {
                    "id": row.id,
                    "agent_id": row.agent_id,
                    "program_id": row.program_id,
                    "status": row.status,
                    "priority": row.priority,
                    "source_type": row.source_type,
                    "due_at": row.due_at.isoformat() if row.due_at else None,
                    "opened_at": row.opened_at.isoformat() if row.opened_at else None,
                    "closed_at": row.closed_at.isoformat() if row.closed_at else None,
                }
                for row in rows
            ],
        )
    )


@bp.get("/sessions")
@login_required
@permission_required("workspace.view")
def sessions_v1():
    return coaching_sessions()


@bp.get("/action-items")
@login_required
@permission_required("workspace.manage_sessions")
def action_items():
    tenant = g.current_tenant or current_user.tenant
    if tenant.id != current_user.tenant_id:
        return jsonify({"error": "cross_tenant_blocked"}), 403
    total, limit, offset, rows = list_action_items(tenant_id=tenant.id, args=request.args)
    return jsonify(
        paginated_response(
            request=request,
            tenant_slug=tenant.slug,
            total=total,
            limit=limit,
            offset=offset,
            items=[
                {
                    "id": row.id,
                    "coaching_session_id": row.coaching_session_id,
                    "status": row.status,
                    "priority": row.priority,
                    "title": row.title,
                    "due_at": row.due_at.isoformat() if row.due_at else None,
                    "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                }
                for row in rows
            ],
        )
    )


@bp.get("/sync-jobs")
@login_required
@permission_required("workspace.manage_integrations")
def sync_jobs():
    tenant = g.current_tenant or current_user.tenant
    if tenant.id != current_user.tenant_id:
        return jsonify({"error": "cross_tenant_blocked"}), 403

    total, limit, offset, rows = list_sync_jobs(tenant_id=tenant.id, args=request.args)
    return jsonify(
        paginated_response(
            request=request,
            tenant_slug=tenant.slug,
            total=total,
            limit=limit,
            offset=offset,
            items=[
                {
                    "id": row.id,
                    "data_source_id": row.data_source_id,
                    "status": row.status,
                    "run_mode": row.run_mode,
                    "attempt_count": row.attempt_count,
                    "total_rows": row.total_rows,
                    "success_rows": row.success_rows,
                    "failed_rows": row.failed_rows,
                    "started_at": row.started_at.isoformat() if row.started_at else None,
                    "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ],
        )
    )


@bp.get("/imports/jobs")
@login_required
@permission_required("workspace.manage_imports")
def import_jobs():
    tenant = g.current_tenant or current_user.tenant
    if tenant.id != current_user.tenant_id:
        return jsonify({"error": "cross_tenant_blocked"}), 403
    total, limit, offset, rows = list_import_jobs(tenant_id=tenant.id, args=request.args)
    return jsonify(
        paginated_response(
            request=request,
            tenant_slug=tenant.slug,
            total=total,
            limit=limit,
            offset=offset,
            items=[
                {
                    "id": row.id,
                    "profile_id": row.profile_id,
                    "status": row.status,
                    "run_mode": row.run_mode,
                    "source_filename": row.source_filename,
                    "total_rows": row.total_rows,
                    "success_rows": row.success_rows,
                    "failed_rows": row.failed_rows,
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ],
        )
    )


@bp.get("/programs")
@login_required
@permission_required("workspace.view")
def programs():
    tenant = g.current_tenant or current_user.tenant
    if tenant.id != current_user.tenant_id:
        return jsonify({"error": "cross_tenant_blocked"}), 403
    total, limit, offset, rows = list_programs(tenant_id=tenant.id, args=request.args)
    return jsonify(
        paginated_response(
            request=request,
            tenant_slug=tenant.slug,
            total=total,
            limit=limit,
            offset=offset,
            items=[
                {
                    "id": row.id,
                    "key": row.key,
                    "name": row.name,
                    "channel": row.channel,
                    "industry": row.industry,
                    "client_name": row.client_name,
                    "is_active": row.is_active,
                }
                for row in rows
            ],
        )
    )


@bp.get("/scorecards")
@login_required
@permission_required("workspace.view")
def scorecards():
    tenant = g.current_tenant or current_user.tenant
    if tenant.id != current_user.tenant_id:
        return jsonify({"error": "cross_tenant_blocked"}), 403
    total, limit, offset, rows = list_scorecards(tenant_id=tenant.id, args=request.args)
    return jsonify(
        paginated_response(
            request=request,
            tenant_slug=tenant.slug,
            total=total,
            limit=limit,
            offset=offset,
            items=[
                {
                    "id": row.id,
                    "name": row.name,
                    "program_id": row.program_id,
                    "is_default": row.is_default,
                }
                for row in rows
            ],
        )
    )


@bp.get("/data-source-health")
@login_required
@permission_required("workspace.manage_integrations")
def data_source_health():
    tenant = g.current_tenant or current_user.tenant
    if tenant.id != current_user.tenant_id:
        return jsonify({"error": "cross_tenant_blocked"}), 403

    total, limit, offset, sources, summary = list_data_source_health(tenant_id=tenant.id, args=request.args)
    payload = paginated_response(
        request=request,
        tenant_slug=tenant.slug,
        total=total,
        limit=limit,
        offset=offset,
        items=[
            {
                "id": s.id,
                "name": s.name,
                "type": s.source_type,
                "health_status": s.health_status,
                "connection_failure_count": s.connection_failure_count,
                "last_connection_status": s.last_connection_status,
                "last_connection_tested_at": (
                    s.last_connection_tested_at.isoformat() if s.last_connection_tested_at else None
                ),
                "last_connection_error": s.last_connection_error,
                "last_health_alerted_at": (
                    s.last_health_alerted_at.isoformat() if s.last_health_alerted_at else None
                ),
                "last_health_alert_status": s.last_health_alert_status,
            }
            for s in sources
        ],
    )
    payload["summary"] = summary
    return jsonify(payload)
