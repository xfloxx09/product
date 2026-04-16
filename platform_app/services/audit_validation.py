from ..models import AuditEvent, CoachingCase, CoachingSession, TenantUser


def audit_coverage_snapshot(*, tenant_id):
    case_count = CoachingCase.query.filter_by(tenant_id=tenant_id).count()
    session_count = CoachingSession.query.filter_by(tenant_id=tenant_id).count()
    user_count = TenantUser.query.filter_by(tenant_id=tenant_id).count()
    case_audits = AuditEvent.query.filter(
        AuditEvent.tenant_id == tenant_id,
        AuditEvent.event_type.like("workspace.coaching_case_%"),
    ).count()
    session_audits = AuditEvent.query.filter(
        AuditEvent.tenant_id == tenant_id,
        AuditEvent.event_type.like("workspace.session_%"),
    ).count()
    user_audits = AuditEvent.query.filter(
        AuditEvent.tenant_id == tenant_id,
        AuditEvent.event_type.like("workspace.user_%"),
    ).count()
    return {
        "case_audit_ratio": round(case_audits / case_count, 4) if case_count else 1.0,
        "session_audit_ratio": round(session_audits / session_count, 4) if session_count else 1.0,
        "user_audit_ratio": round(user_audits / user_count, 4) if user_count else 1.0,
        "audit_events_total": AuditEvent.query.filter_by(tenant_id=tenant_id).count(),
    }

