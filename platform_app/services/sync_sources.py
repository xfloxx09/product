import json
from datetime import datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..extensions import db
from ..models import AgentProfile, DataSource, SyncJob, SyncJobError, Tenant
from .connector_secrets import get_source_secret
from .imports import process_csv_rows, read_csv_bytes, read_csv_upload
from .plan_catalog import get_limit


def run_data_source_sync(*, data_source, triggered_by_user_id, run_mode, upload_file=None):
    source_type = data_source.source_type
    config = json.loads(data_source.config_json or "{}")
    # Secrets are stored encrypted; fallback to config for backward compatibility.
    config["api_token"] = get_source_secret(
        tenant_id=data_source.tenant_id,
        data_source_id=data_source.id,
        name="api_token",
        default=config.get("api_token", ""),
    )
    config["sftp_password"] = get_source_secret(
        tenant_id=data_source.tenant_id,
        data_source_id=data_source.id,
        name="sftp_password",
        default=config.get("sftp_password", ""),
    )
    mapping = config.get("mapping", {})
    transforms = config.get("transforms", {})

    rows, headers = _read_rows_for_data_source(
        source_type=source_type,
        config=config,
        upload_file=upload_file,
    )
    tenant_plan = db.session.query(Tenant.plan).filter_by(id=data_source.tenant_id).scalar()
    active_members_limit = get_limit(tenant_plan, "active_members")
    current_active_members = AgentProfile.query.filter_by(tenant_id=data_source.tenant_id, status="active").count()
    summary, errors = process_csv_rows(
        tenant_id=data_source.tenant_id,
        coach_user_id=triggered_by_user_id,
        rows=rows,
        mapping=mapping,
        transforms=transforms,
        persist=run_mode == "apply",
        active_members_limit=active_members_limit,
        current_active_members=current_active_members,
    )
    return {
        "rows": rows,
        "headers": headers,
        "summary": summary,
        "errors": errors,
    }


def test_data_source_connection(*, data_source):
    """
    Validate connector reachability and credentials without writing data.
    Returns dict: {"ok": bool, "message": str, "details": dict}
    """
    source_type = data_source.source_type
    config = json.loads(data_source.config_json or "{}")
    config["api_token"] = get_source_secret(
        tenant_id=data_source.tenant_id,
        data_source_id=data_source.id,
        name="api_token",
        default=config.get("api_token", ""),
    )
    config["sftp_password"] = get_source_secret(
        tenant_id=data_source.tenant_id,
        data_source_id=data_source.id,
        name="sftp_password",
        default=config.get("sftp_password", ""),
    )

    if source_type == "csv_upload":
        return {
            "ok": True,
            "message": "CSV upload source is manual; no remote connection required.",
            "details": {"source_type": source_type},
        }

    try:
        payload = None
        if source_type == "api":
            payload = _fetch_csv_from_api(config)
        elif source_type == "sftp":
            payload = _fetch_csv_from_sftp(config)
        else:
            return {
                "ok": False,
                "message": f"Unsupported source type '{source_type}'.",
                "details": {"source_type": source_type},
            }

        rows, headers = read_csv_bytes(payload)
        return {
            "ok": True,
            "message": "Connection test successful.",
            "details": {
                "source_type": source_type,
                "headers": headers,
                "sample_row_count": min(len(rows), 3),
            },
        }
    except Exception as exc:
        return {
            "ok": False,
            "message": f"Connection test failed: {exc}",
            "details": {"source_type": source_type},
        }


def apply_connection_test_result(*, data_source, result, failure_threshold=3):
    data_source.last_connection_tested_at = datetime.utcnow()
    data_source.last_connection_status = "ok" if result.get("ok") else "failed"
    if result.get("ok"):
        data_source.last_connection_error = None
        data_source.connection_failure_count = 0
        data_source.health_status = "healthy"
    else:
        data_source.last_connection_error = str(result.get("message", "Connection test failed"))[:255]
        data_source.connection_failure_count = (data_source.connection_failure_count or 0) + 1
        if data_source.connection_failure_count >= max(1, int(failure_threshold)):
            data_source.health_status = "unhealthy"
        else:
            data_source.health_status = "degraded"


def execute_health_checks_for_tenant(*, tenant_id, batch_size=25, failure_threshold=3):
    sources = (
        DataSource.query.filter_by(tenant_id=tenant_id, is_active=True)
        .order_by(DataSource.updated_at.asc())
        .limit(batch_size)
        .all()
    )
    checked = 0
    healthy = 0
    degraded = 0
    unhealthy = 0
    failed = 0
    for source in sources:
        result = test_data_source_connection(data_source=source)
        apply_connection_test_result(
            data_source=source,
            result=result,
            failure_threshold=failure_threshold,
        )
        checked += 1
        if result.get("ok"):
            healthy += 1
        else:
            failed += 1
            if source.health_status == "unhealthy":
                unhealthy += 1
            else:
                degraded += 1
    return {
        "checked": checked,
        "healthy": healthy,
        "degraded": degraded,
        "unhealthy": unhealthy,
        "failed": failed,
        "sources_checked": sources,
    }


def _read_rows_for_data_source(*, source_type, config, upload_file):
    if source_type == "csv_upload":
        if upload_file is None:
            raise ValueError("CSV upload is required for csv upload sources.")
        return read_csv_upload(upload_file)
    if source_type == "api":
        payload = _fetch_csv_from_api(config)
        return read_csv_bytes(payload)
    if source_type == "sftp":
        payload = _fetch_csv_from_sftp(config)
        return read_csv_bytes(payload)
    raise ValueError(f"Unsupported source type '{source_type}'.")


def _fetch_csv_from_api(config):
    endpoint = (config.get("endpoint_url") or "").strip()
    if not endpoint:
        raise ValueError("API endpoint_url is missing in data source config.")
    auth_header = (config.get("api_auth_header") or "Authorization").strip()
    api_token = (config.get("api_token") or "").strip()
    timeout_seconds = int(config.get("timeout_seconds") or 20)
    headers = {"Accept": "text/csv"}
    if api_token:
        if auth_header.lower() == "authorization" and not api_token.lower().startswith("bearer "):
            headers[auth_header] = f"Bearer {api_token}"
        else:
            headers[auth_header] = api_token
    req = Request(endpoint, headers=headers, method="GET")
    try:
        with urlopen(req, timeout=timeout_seconds) as resp:
            return resp.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ValueError(f"API connector request failed: {exc}") from exc


def _fetch_csv_from_sftp(config):
    host = (config.get("sftp_host") or "").strip()
    port = int(config.get("sftp_port") or 22)
    username = (config.get("sftp_username") or "").strip()
    password = (config.get("sftp_password") or "").strip()
    private_key_path = (config.get("sftp_private_key_path") or "").strip()
    remote_path = (config.get("sftp_path") or "").strip()
    timeout_seconds = int(config.get("timeout_seconds") or 20)
    if not host or not username or not remote_path:
        raise ValueError("SFTP config requires sftp_host, sftp_username and sftp_path.")
    try:
        import paramiko  # optional runtime dependency
    except ImportError as exc:
        raise ValueError("SFTP connector requires 'paramiko' package.") from exc

    transport = None
    sftp = None
    try:
        transport = paramiko.Transport((host, port))
        transport.banner_timeout = timeout_seconds
        transport.auth_timeout = timeout_seconds
        if private_key_path:
            key = paramiko.RSAKey.from_private_key_file(private_key_path)
            transport.connect(username=username, pkey=key)
        else:
            transport.connect(username=username, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        with sftp.open(remote_path, "rb") as remote_file:
            return remote_file.read()
    except Exception as exc:
        raise ValueError(f"SFTP connector failed: {exc}") from exc
    finally:
        if sftp is not None:
            sftp.close()
        if transport is not None:
            transport.close()


def persist_sync_errors(sync_job, errors):
    records = []
    for row_number, payload, message in errors:
        records.append(
            SyncJobError(
                sync_job_id=sync_job.id,
                row_number=row_number,
                error_message=message,
                row_payload_json=json.dumps(payload),
            )
        )
    if records:
        db.session.add_all(records)
    return len(records)


def source_next_run_at(source, now=None):
    now = now or datetime.utcnow()
    if source.schedule == "manual":
        return None
    if not source.last_synced_at:
        return now
    if source.schedule == "hourly":
        return source.last_synced_at + timedelta(hours=1)
    if source.schedule == "daily":
        return source.last_synced_at + timedelta(days=1)
    return None


def source_is_due(source, now=None):
    now = now or datetime.utcnow()
    next_run = source_next_run_at(source, now=now)
    return bool(next_run and next_run <= now)


def due_sources_for_tenant(tenant_id, now=None, limit=25):
    now = now or datetime.utcnow()
    candidates = (
        DataSource.query.filter_by(tenant_id=tenant_id, is_active=True)
        .filter(DataSource.schedule.in_(["hourly", "daily"]))
        .order_by(DataSource.updated_at.asc())
        .all()
    )
    due = [s for s in candidates if source_is_due(s, now=now)]
    return due[:limit]


def create_sync_job(*, data_source, triggered_by_user_id, run_mode, source_filename=None):
    last_failed = (
        SyncJob.query.filter_by(data_source_id=data_source.id, status="failed")
        .order_by(SyncJob.created_at.desc())
        .first()
    )
    attempt_count = (last_failed.attempt_count + 1) if last_failed else 1
    job = SyncJob(
        tenant_id=data_source.tenant_id,
        data_source_id=data_source.id,
        triggered_by_user_id=triggered_by_user_id,
        run_mode=run_mode,
        status="processing",
        attempt_count=attempt_count,
        started_at=datetime.utcnow(),
        source_filename=source_filename,
    )
    db.session.add(job)
    db.session.flush()
    return job


def execute_due_sources_for_tenant(*, tenant_id, actor_user_id, batch_size=25, max_retries=3):
    due_sources = due_sources_for_tenant(tenant_id, limit=batch_size)
    executed = 0
    skipped = 0
    failed = 0
    throttled = 0
    for source in due_sources:
        if source.failure_count >= max_retries:
            throttled += 1
            continue
        job = None
        try:
            job = create_sync_job(
                data_source=source,
                triggered_by_user_id=actor_user_id,
                run_mode="apply",
                source_filename=None,
            )
            if source.source_type == "csv_upload":
                job.status = "skipped_requires_file"
                job.finished_at = datetime.utcnow()
                job.summary_json = json.dumps({"reason": "csv_upload source requires uploaded file"})
                skipped += 1
                executed += 1
                continue
            result = run_data_source_sync(
                data_source=source,
                triggered_by_user_id=actor_user_id,
                run_mode="apply",
                upload_file=None,
            )
            summary = result["summary"]
            errors = result["errors"]
            job.total_rows = len(result["rows"])
            job.success_rows = summary.get("created_sessions", 0)
            job.failed_rows = len(errors)
            base_status = "completed_with_errors" if errors else "completed"
            job.status = f"apply_{base_status}"
            job.summary_json = json.dumps(
                {
                    "headers": result["headers"],
                    "result": summary,
                    "source_type": source.source_type,
                    "run_mode": "apply",
                }
            )
            persist_sync_errors(job, errors)
            source.last_synced_at = datetime.utcnow()
            source.last_error = None
            source.failure_count = 0
            executed += 1
            job.finished_at = datetime.utcnow()
        except Exception as exc:
            failed += 1
            if job is not None:
                job.status = "failed"
                job.finished_at = datetime.utcnow()
                job.summary_json = json.dumps({"error": str(exc)})
            source.last_error = str(exc)[:255]
            source.failure_count = (source.failure_count or 0) + 1
    return {
        "due_count": len(due_sources),
        "executed": executed,
        "skipped": skipped,
        "failed": failed,
        "throttled": throttled,
    }
