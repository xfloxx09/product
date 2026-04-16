from ..extensions import db
from ..models import Tenant, TenantUser
from .connector_alerts import maybe_send_health_alerts_for_tenant
from .sync_sources import execute_due_sources_for_tenant, execute_health_checks_for_tenant


def run_scheduled_sync_batch(*, app):
    tenants = Tenant.query.filter_by(is_active=True).all()
    totals = {"due": 0, "executed": 0, "failed": 0, "throttled": 0}
    for tenant in tenants:
        system_user = TenantUser.query.filter_by(tenant_id=tenant.id, is_active=True).first()
        if not system_user:
            continue
        result = execute_due_sources_for_tenant(
            tenant_id=tenant.id,
            actor_user_id=system_user.id,
            batch_size=app.config["DATASOURCE_SCHEDULE_BATCH_SIZE"],
            max_retries=app.config["DATASOURCE_MAX_RETRIES"],
        )
        totals["due"] += result["due_count"]
        totals["executed"] += result["executed"]
        totals["failed"] += result["failed"]
        totals["throttled"] += result["throttled"]
    db.session.commit()
    return totals


def run_health_check_batch(*, app):
    tenants = Tenant.query.filter_by(is_active=True).all()
    totals = {"checked": 0, "degraded": 0, "unhealthy": 0, "alerts_sent": 0}
    for tenant in tenants:
        result = execute_health_checks_for_tenant(
            tenant_id=tenant.id,
            batch_size=app.config["DATASOURCE_HEALTH_CHECK_BATCH_SIZE"],
            failure_threshold=app.config["DATASOURCE_HEALTH_FAILURE_THRESHOLD"],
        )
        alert_result = maybe_send_health_alerts_for_tenant(
            tenant=tenant,
            sources=result.get("sources_checked", []),
            cooldown_minutes=app.config["DATASOURCE_ALERT_COOLDOWN_MINUTES"],
            email_enabled=app.config["DATASOURCE_ALERT_EMAIL_ENABLED"],
            webhook_enabled=app.config["DATASOURCE_ALERT_WEBHOOK_ENABLED"],
            webhook_timeout_seconds=app.config["DATASOURCE_ALERT_WEBHOOK_TIMEOUT_SECONDS"],
            default_on_degraded=app.config["DATASOURCE_ALERT_DEFAULT_ON_DEGRADED"],
            default_on_unhealthy=app.config["DATASOURCE_ALERT_DEFAULT_ON_UNHEALTHY"],
        )
        totals["checked"] += result["checked"]
        totals["degraded"] += result["degraded"]
        totals["unhealthy"] += result["unhealthy"]
        totals["alerts_sent"] += alert_result["sent"]
    db.session.commit()
    return totals

