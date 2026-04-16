from flask import Blueprint, g, jsonify
from flask_login import current_user, login_required

from ...models import AgentProfile, CoachingSession, DataSource, SyncJob
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


@bp.get("/coaching-sessions")
@login_required
@permission_required("workspace.view")
def coaching_sessions():
    tenant = g.current_tenant or current_user.tenant
    if tenant.id != current_user.tenant_id:
        return jsonify({"error": "cross_tenant_blocked"}), 403

    rows = (
        CoachingSession.query.filter_by(tenant_id=tenant.id)
        .order_by(CoachingSession.occurred_at.desc())
        .limit(100)
        .all()
    )
    return jsonify(
        [
            {
                "id": r.id,
                "agent": r.agent.full_name,
                "coach": r.coach.full_name,
                "type": r.coaching_type,
                "channel": r.channel,
                "score": r.score,
                "occurred_at": r.occurred_at.isoformat(),
            }
            for r in rows
        ]
    )


@bp.get("/sync-jobs")
@login_required
@permission_required("workspace.manage_integrations")
def sync_jobs():
    tenant = g.current_tenant or current_user.tenant
    if tenant.id != current_user.tenant_id:
        return jsonify({"error": "cross_tenant_blocked"}), 403

    rows = (
        SyncJob.query.filter_by(tenant_id=tenant.id)
        .order_by(SyncJob.created_at.desc())
        .limit(100)
        .all()
    )
    return jsonify(
        [
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
        ]
    )


@bp.get("/data-source-health")
@login_required
@permission_required("workspace.manage_integrations")
def data_source_health():
    tenant = g.current_tenant or current_user.tenant
    if tenant.id != current_user.tenant_id:
        return jsonify({"error": "cross_tenant_blocked"}), 403

    sources = (
        DataSource.query.filter_by(tenant_id=tenant.id, is_active=True)
        .order_by(DataSource.updated_at.desc())
        .all()
    )
    return jsonify(
        {
            "tenant": tenant.slug,
            "summary": {
                "healthy": sum(1 for s in sources if s.health_status == "healthy"),
                "degraded": sum(1 for s in sources if s.health_status == "degraded"),
                "unhealthy": sum(1 for s in sources if s.health_status == "unhealthy"),
                "unknown": sum(1 for s in sources if s.health_status == "unknown"),
            },
            "sources": [
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
        }
    )
