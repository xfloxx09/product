import uuid

from ..models import (
    AgentProfile,
    CoachingActionItem,
    CoachingCase,
    CoachingSession,
    CsvImportJob,
    DataSource,
    Program,
    ScorecardTemplate,
    SyncJob,
)


def _pagination_params(args):
    limit = max(1, min(200, int(args.get("limit", 50))))
    offset = max(0, int(args.get("offset", 0)))
    return limit, offset


def _request_id(request):
    return request.headers.get("X-Request-Id") or str(uuid.uuid4())


def list_agents(*, tenant_id, args):
    limit, offset = _pagination_params(args)
    query = AgentProfile.query.filter_by(tenant_id=tenant_id).order_by(AgentProfile.full_name.asc())
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    return total, limit, offset, rows


def list_sessions(*, tenant_id, args):
    limit, offset = _pagination_params(args)
    query = CoachingSession.query.filter_by(tenant_id=tenant_id).order_by(CoachingSession.occurred_at.desc())
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    return total, limit, offset, rows


def list_cases(*, tenant_id, args):
    limit, offset = _pagination_params(args)
    query = CoachingCase.query.filter_by(tenant_id=tenant_id).order_by(CoachingCase.created_at.desc())
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    return total, limit, offset, rows


def list_action_items(*, tenant_id, args):
    limit, offset = _pagination_params(args)
    query = CoachingActionItem.query.filter_by(tenant_id=tenant_id).order_by(CoachingActionItem.created_at.desc())
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    return total, limit, offset, rows


def list_sync_jobs(*, tenant_id, args):
    limit, offset = _pagination_params(args)
    query = SyncJob.query.filter_by(tenant_id=tenant_id).order_by(SyncJob.created_at.desc())
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    return total, limit, offset, rows


def list_import_jobs(*, tenant_id, args):
    limit, offset = _pagination_params(args)
    query = CsvImportJob.query.filter_by(tenant_id=tenant_id).order_by(CsvImportJob.created_at.desc())
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    return total, limit, offset, rows


def list_programs(*, tenant_id, args):
    limit, offset = _pagination_params(args)
    query = Program.query.filter_by(tenant_id=tenant_id).order_by(Program.name.asc())
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    return total, limit, offset, rows


def list_scorecards(*, tenant_id, args):
    limit, offset = _pagination_params(args)
    query = ScorecardTemplate.query.filter_by(tenant_id=tenant_id).order_by(ScorecardTemplate.name.asc())
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    return total, limit, offset, rows


def list_data_source_health(*, tenant_id, args):
    limit, offset = _pagination_params(args)
    query = DataSource.query.filter_by(tenant_id=tenant_id, is_active=True).order_by(DataSource.updated_at.desc())
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    summary = {
        "healthy": sum(1 for s in rows if s.health_status == "healthy"),
        "degraded": sum(1 for s in rows if s.health_status == "degraded"),
        "unhealthy": sum(1 for s in rows if s.health_status == "unhealthy"),
        "unknown": sum(1 for s in rows if s.health_status == "unknown"),
    }
    return total, limit, offset, rows, summary


def paginated_response(*, request, tenant_slug, total, limit, offset, items):
    return {
        "request_id": _request_id(request),
        "tenant": tenant_slug,
        "pagination": {"total": total, "limit": limit, "offset": offset},
        "items": items,
    }

