import json
from datetime import datetime, timedelta

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from ...extensions import db
from ...models import CsvImportProfile, DataSource, DataSourceAlertEvent, SyncJob, SyncJobError
from ...services.audit import log_audit_event
from ...services.connector_secrets import (
    clear_source_secret,
    get_source_secret,
    has_source_secret,
    upsert_source_secrets,
)
from ...services.connector_alerts import (
    evaluate_alert_dispatch_for_source,
    maybe_send_health_alerts_for_tenant,
    send_test_alert_for_source,
)
from ...services.mailer import build_data_source_health_alert_payload, build_data_source_signature_headers
from ...services.plan_catalog import is_feature_enabled
from ...services.sync_sources import (
    apply_connection_test_result,
    create_sync_job,
    due_sources_for_tenant,
    execute_health_checks_for_tenant,
    execute_due_sources_for_tenant,
    persist_sync_errors,
    run_data_source_sync,
    source_next_run_at,
    test_data_source_connection,
)
from ...services.tenant_context import permission_required


bp = Blueprint("datasources", __name__, url_prefix="/datasources")


def _safe_int(value, default):
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return default


def _analytics_window_to_start(window):
    now = datetime.utcnow()
    if window == "24h":
        return now - timedelta(hours=24)
    if window == "30d":
        return now - timedelta(days=30)
    # default
    return now - timedelta(days=7)


def _build_source_config_from_form(form, existing_config, default_mapping, default_transforms):
    cfg = dict(existing_config or {})
    existing_policy = dict(cfg.get("alert_policy") or {})

    def _checkbox(name):
        return bool(form.get(name))
    cfg["mapping"] = cfg.get("mapping") or default_mapping
    cfg["transforms"] = cfg.get("transforms") or default_transforms
    cfg["endpoint_url"] = (form.get("endpoint_url") or "").strip()
    cfg["api_auth_header"] = (form.get("api_auth_header") or "Authorization").strip()
    cfg["timeout_seconds"] = _safe_int(form.get("timeout_seconds"), cfg.get("timeout_seconds", 20))
    cfg["sftp_host"] = (form.get("sftp_host") or "").strip()
    cfg["sftp_port"] = _safe_int(form.get("sftp_port"), cfg.get("sftp_port", 22))
    cfg["sftp_username"] = (form.get("sftp_username") or "").strip()
    cfg["sftp_private_key_path"] = (form.get("sftp_private_key_path") or "").strip()
    cfg["sftp_path"] = (form.get("sftp_path") or "").strip()
    cfg["alert_webhook_url"] = (form.get("alert_webhook_url") or "").strip()
    cfg["alert_webhook_auth_header"] = (form.get("alert_webhook_auth_header") or "Authorization").strip()
    webhook_format = (form.get("alert_webhook_format") or "generic").strip().lower()
    if webhook_format not in {"generic", "slack", "teams"}:
        webhook_format = "generic"
    cfg["alert_webhook_format"] = webhook_format
    cfg["alert_webhook_signature_header"] = (
        form.get("alert_webhook_signature_header") or "X-CoachingOS-Signature"
    ).strip()
    cfg["alert_policy"] = {
        "on_degraded": _checkbox("alert_on_degraded"),
        "on_unhealthy": _checkbox("alert_on_unhealthy"),
        "channel_email": _checkbox("alert_channel_email"),
        "channel_webhook": _checkbox("alert_channel_webhook"),
        "cooldown_minutes": _safe_int(form.get("alert_cooldown_minutes"), existing_policy.get("cooldown_minutes", 180)),
    }
    return cfg


@bp.route("/", methods=["GET", "POST"])
@login_required
@permission_required("workspace.manage_integrations")
def list_sources():
    tenant = g.current_tenant or current_user.tenant
    default_profile = CsvImportProfile.query.filter_by(tenant_id=tenant.id, is_default=True).first()
    default_mapping = json.loads(default_profile.mapping_json) if default_profile else {}
    default_transforms = {
        "score_scale": "auto",
        "decimal_comma": False,
        "strip_percent": True,
        "date_format": "",
    }

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        source_type = (request.form.get("source_type") or "csv_upload").strip().lower()
        schedule = (request.form.get("schedule") or "manual").strip().lower()
        if source_type not in {"csv_upload", "sftp", "api"}:
            flash("Invalid source type.", "danger")
            return redirect(url_for("datasources.list_sources", tenant=tenant.slug))
        if source_type == "sftp" and not is_feature_enabled(tenant.plan, "source_sftp"):
            flash("SFTP connectors are available on Growth and Enterprise plans.", "warning")
            return redirect(url_for("datasources.list_sources", tenant=tenant.slug))
        if source_type == "api" and not is_feature_enabled(tenant.plan, "source_api"):
            flash("API connectors are available on Growth and Enterprise plans.", "warning")
            return redirect(url_for("datasources.list_sources", tenant=tenant.slug))
        if not name:
            flash("Name is required.", "danger")
            return redirect(url_for("datasources.list_sources", tenant=tenant.slug))
        if source_type == "csv_upload":
            schedule = "manual"

        cfg = _build_source_config_from_form(
            request.form,
            existing_config={},
            default_mapping=default_mapping,
            default_transforms=default_transforms,
        )
        source = DataSource(
            tenant_id=tenant.id,
            name=name,
            source_type=source_type,
            schedule=schedule if schedule in {"manual", "hourly", "daily"} else "manual",
            config_json=json.dumps(cfg),
        )
        db.session.add(source)
        db.session.flush()
        upsert_source_secrets(
            tenant_id=tenant.id,
            data_source_id=source.id,
            secrets_dict={
                "api_token": request.form.get("api_token"),
                "sftp_password": request.form.get("sftp_password"),
                "alert_webhook_token": request.form.get("alert_webhook_token"),
                "alert_webhook_signing_secret": request.form.get("alert_webhook_signing_secret"),
            },
        )
        log_audit_event(
            tenant.id,
            "datasource.created",
            {"name": name, "source_type": source_type},
            actor_user_id=current_user.id,
        )
        db.session.commit()
        flash("Data source created.", "success")
        return redirect(url_for("datasources.list_sources", tenant=tenant.slug))

    sources = DataSource.query.filter_by(tenant_id=tenant.id).order_by(DataSource.created_at.desc()).all()
    due_ids = {src.id for src in due_sources_for_tenant(tenant.id)}
    source_next_runs = {src.id: source_next_run_at(src) for src in sources}
    source_has_api_token = {
        src.id: has_source_secret(tenant_id=tenant.id, data_source_id=src.id, name="api_token")
        for src in sources
    }
    source_has_sftp_password = {
        src.id: has_source_secret(tenant_id=tenant.id, data_source_id=src.id, name="sftp_password")
        for src in sources
    }
    recent_jobs = (
        SyncJob.query.filter_by(tenant_id=tenant.id)
        .order_by(SyncJob.created_at.desc())
        .limit(20)
        .all()
    )
    connector_features = {
        "source_sftp": is_feature_enabled(tenant.plan, "source_sftp"),
        "source_api": is_feature_enabled(tenant.plan, "source_api"),
    }
    return render_template(
        "datasources/list.html",
        tenant=tenant,
        sources=sources,
        due_source_ids=due_ids,
        source_next_runs=source_next_runs,
        source_has_api_token=source_has_api_token,
        source_has_sftp_password=source_has_sftp_password,
        recent_jobs=recent_jobs,
        connector_features=connector_features,
    )


@bp.route("/<int:source_id>/settings", methods=["GET", "POST"])
@login_required
@permission_required("workspace.manage_integrations")
def source_settings(source_id):
    tenant = g.current_tenant or current_user.tenant
    source = DataSource.query.filter_by(id=source_id, tenant_id=tenant.id).first_or_404()
    cfg = json.loads(source.config_json or "{}")
    default_profile = CsvImportProfile.query.filter_by(tenant_id=tenant.id, is_default=True).first()
    default_mapping = json.loads(default_profile.mapping_json) if default_profile else {}
    default_transforms = {
        "score_scale": "auto",
        "decimal_comma": False,
        "strip_percent": True,
        "date_format": "",
    }

    if request.method == "POST":
        action = (request.form.get("action") or "update_config").strip()
        if action == "update_config":
            source.name = (request.form.get("name") or source.name).strip()
            source.schedule = (request.form.get("schedule") or source.schedule).strip().lower()
            if source.source_type == "csv_upload":
                source.schedule = "manual"
            if source.schedule not in {"manual", "hourly", "daily"}:
                source.schedule = "manual"
            source.is_active = bool(request.form.get("is_active"))
            cfg = _build_source_config_from_form(
                request.form,
                existing_config=cfg,
                default_mapping=default_mapping,
                default_transforms=default_transforms,
            )
            source.config_json = json.dumps(cfg)
            log_audit_event(
                tenant.id,
                "datasource.config_updated",
                {"data_source_id": source.id, "source_type": source.source_type},
                actor_user_id=current_user.id,
            )
            db.session.commit()
            flash("Data source configuration updated.", "success")
        elif action == "rotate_secrets":
            new_api_token = (request.form.get("api_token") or "").strip()
            new_sftp_password = (request.form.get("sftp_password") or "").strip()
            new_webhook_token = (request.form.get("alert_webhook_token") or "").strip()
            new_webhook_signing_secret = (request.form.get("alert_webhook_signing_secret") or "").strip()
            clear_api = bool(request.form.get("clear_api_token"))
            clear_sftp = bool(request.form.get("clear_sftp_password"))
            clear_webhook = bool(request.form.get("clear_alert_webhook_token"))
            clear_webhook_signing = bool(request.form.get("clear_alert_webhook_signing_secret"))

            rotated = []
            if new_api_token:
                upsert_source_secrets(
                    tenant_id=tenant.id,
                    data_source_id=source.id,
                    secrets_dict={"api_token": new_api_token},
                )
                rotated.append("api_token")
            if new_sftp_password:
                upsert_source_secrets(
                    tenant_id=tenant.id,
                    data_source_id=source.id,
                    secrets_dict={"sftp_password": new_sftp_password},
                )
                rotated.append("sftp_password")
            if clear_api:
                clear_source_secret(
                    tenant_id=tenant.id,
                    data_source_id=source.id,
                    name="api_token",
                )
                rotated.append("api_token_cleared")
            if clear_sftp:
                clear_source_secret(
                    tenant_id=tenant.id,
                    data_source_id=source.id,
                    name="sftp_password",
                )
                rotated.append("sftp_password_cleared")
            if new_webhook_token:
                upsert_source_secrets(
                    tenant_id=tenant.id,
                    data_source_id=source.id,
                    secrets_dict={"alert_webhook_token": new_webhook_token},
                )
                rotated.append("alert_webhook_token")
            if new_webhook_signing_secret:
                upsert_source_secrets(
                    tenant_id=tenant.id,
                    data_source_id=source.id,
                    secrets_dict={"alert_webhook_signing_secret": new_webhook_signing_secret},
                )
                rotated.append("alert_webhook_signing_secret")
            if clear_webhook:
                clear_source_secret(
                    tenant_id=tenant.id,
                    data_source_id=source.id,
                    name="alert_webhook_token",
                )
                rotated.append("alert_webhook_token_cleared")
            if clear_webhook_signing:
                clear_source_secret(
                    tenant_id=tenant.id,
                    data_source_id=source.id,
                    name="alert_webhook_signing_secret",
                )
                rotated.append("alert_webhook_signing_secret_cleared")

            if rotated:
                source.last_secret_rotated_at = datetime.utcnow()
                log_audit_event(
                    tenant.id,
                    "datasource.secrets_rotated",
                    {"data_source_id": source.id, "changes": rotated},
                    actor_user_id=current_user.id,
                )
                db.session.commit()
                flash("Connector secrets updated.", "success")
            else:
                flash("No secret changes submitted.", "warning")
        elif action == "test_connection":
            result = test_data_source_connection(data_source=source)
            apply_connection_test_result(
                data_source=source,
                result=result,
                failure_threshold=current_app.config["DATASOURCE_HEALTH_FAILURE_THRESHOLD"],
            )
            log_audit_event(
                tenant.id,
                "datasource.connection_tested",
                {
                    "data_source_id": source.id,
                    "source_type": source.source_type,
                    "ok": result["ok"],
                    "message": result["message"],
                },
                actor_user_id=current_user.id,
            )
            db.session.commit()
            flash(result["message"], "success" if result["ok"] else "danger")
        elif action == "send_test_alert":
            test_status = (request.form.get("test_alert_status") or "unhealthy").strip().lower()
            if test_status not in {"degraded", "unhealthy"}:
                test_status = "unhealthy"
            test_error = (request.form.get("test_alert_error") or "Manual test alert").strip()
            result = send_test_alert_for_source(
                tenant=tenant,
                source=source,
                health_status=test_status,
                error_message=test_error,
                email_enabled=current_app.config["DATASOURCE_ALERT_EMAIL_ENABLED"],
                webhook_enabled=current_app.config["DATASOURCE_ALERT_WEBHOOK_ENABLED"],
                webhook_timeout_seconds=current_app.config["DATASOURCE_ALERT_WEBHOOK_TIMEOUT_SECONDS"],
            )
            log_audit_event(
                tenant.id,
                "datasource.test_alert_sent",
                {
                    "data_source_id": source.id,
                    "status": test_status,
                    "delivery_attempted": result["delivery_attempted"],
                    "delivery_failed": result["delivery_failed"],
                    "sent_email": result["sent_email"],
                    "sent_webhook": result["sent_webhook"],
                },
                actor_user_id=current_user.id,
            )
            db.session.commit()
            if result["delivery_attempted"] and not result["delivery_failed"]:
                flash(
                    f"Test alert sent (email {result['sent_email']}, webhook {result['sent_webhook']}).",
                    "success",
                )
            elif result["delivery_attempted"] and result["delivery_failed"]:
                flash("Test alert attempted but at least one channel failed.", "danger")
            else:
                flash("No alert channels configured/enabled for this source.", "warning")
        return redirect(url_for("datasources.source_settings", source_id=source.id, tenant=tenant.slug))

    has_api = has_source_secret(tenant_id=tenant.id, data_source_id=source.id, name="api_token")
    has_sftp = has_source_secret(tenant_id=tenant.id, data_source_id=source.id, name="sftp_password")
    has_webhook_token = has_source_secret(tenant_id=tenant.id, data_source_id=source.id, name="alert_webhook_token")
    has_webhook_signing_secret = has_source_secret(
        tenant_id=tenant.id,
        data_source_id=source.id,
        name="alert_webhook_signing_secret",
    )
    recent_alert_events = (
        DataSourceAlertEvent.query.filter_by(tenant_id=tenant.id, data_source_id=source.id)
        .order_by(DataSourceAlertEvent.created_at.desc())
        .limit(20)
        .all()
    )
    alert_events = []
    for event in recent_alert_events:
        try:
            email_result = json.loads(event.email_result_json or "{}")
        except json.JSONDecodeError:
            email_result = {}
        try:
            webhook_result = json.loads(event.webhook_result_json or "{}")
        except json.JSONDecodeError:
            webhook_result = {}
        alert_events.append(
            {
                "id": event.id,
                "created_at": event.created_at,
                "trigger_type": event.trigger_type,
                "health_status": event.health_status,
                "error_message": event.error_message,
                "delivery_attempted": event.delivery_attempted,
                "delivery_failed": event.delivery_failed,
                "sent_email": event.sent_email,
                "sent_webhook": event.sent_webhook,
                "email_result": email_result,
                "webhook_result": webhook_result,
            }
        )
    return render_template(
        "datasources/settings.html",
        tenant=tenant,
        source=source,
        config=cfg,
        has_api=has_api,
        has_sftp=has_sftp,
        has_webhook_token=has_webhook_token,
        has_webhook_signing_secret=has_webhook_signing_secret,
        alert_events=alert_events,
    )


@bp.route("/<int:source_id>/run", methods=["GET", "POST"])
@login_required
@permission_required("workspace.manage_integrations")
def run_source(source_id):
    tenant = g.current_tenant or current_user.tenant
    source = DataSource.query.filter_by(id=source_id, tenant_id=tenant.id).first_or_404()
    if request.method == "POST":
        run_mode = (request.form.get("run_mode") or "dry_run").strip().lower()
        if run_mode not in {"dry_run", "apply"}:
            run_mode = "dry_run"
        upload = request.files.get("csv_file")
        if source.source_type == "csv_upload" and (not upload or not upload.filename):
            flash("CSV file is required for csv upload source.", "danger")
            return redirect(url_for("datasources.run_source", source_id=source.id, tenant=tenant.slug))

        job = create_sync_job(
            data_source=source,
            triggered_by_user_id=current_user.id,
            run_mode=run_mode,
            source_filename=upload.filename if upload else None,
        )
        try:
            result = run_data_source_sync(
                data_source=source,
                triggered_by_user_id=current_user.id,
                run_mode=run_mode,
                upload_file=upload,
            )
            summary = result["summary"]
            errors = result["errors"]
            job.total_rows = len(result["rows"])
            job.success_rows = summary.get("created_sessions", 0)
            job.failed_rows = len(errors)
            base_status = "completed_with_errors" if errors else "completed"
            job.status = f"{run_mode}_{base_status}"
            job.summary_json = json.dumps(
                {
                    "headers": result["headers"],
                    "result": summary,
                    "source_type": source.source_type,
                    "run_mode": run_mode,
                }
            )
            persist_sync_errors(job, errors)
            source.last_synced_at = datetime.utcnow()
            source.last_error = None
            source.failure_count = 0
            job.finished_at = datetime.utcnow()
            log_audit_event(
                tenant.id,
                "datasource.sync_completed",
                {
                    "data_source_id": source.id,
                    "job_id": job.id,
                    "run_mode": run_mode,
                    "rows": job.total_rows,
                    "failed_rows": job.failed_rows,
                },
                actor_user_id=current_user.id,
            )
            db.session.commit()
            flash("Sync job completed.", "success")
            return redirect(url_for("datasources.job_detail", job_id=job.id, tenant=tenant.slug))
        except Exception as exc:
            job.status = "failed"
            job.finished_at = datetime.utcnow()
            job.summary_json = json.dumps({"error": str(exc)})
            source.last_error = str(exc)[:255]
            source.failure_count = (source.failure_count or 0) + 1
            log_audit_event(
                tenant.id,
                "datasource.sync_failed",
                {"data_source_id": source.id, "job_id": job.id, "error": str(exc)},
                actor_user_id=current_user.id,
            )
            db.session.commit()
            flash(f"Sync failed: {exc}", "danger")
            return redirect(url_for("datasources.run_source", source_id=source.id, tenant=tenant.slug))

    return render_template("datasources/run.html", tenant=tenant, source=source)


@bp.post("/run-due")
@login_required
@permission_required("workspace.manage_integrations")
def run_due_sources():
    tenant = g.current_tenant or current_user.tenant
    result = execute_due_sources_for_tenant(
        tenant_id=tenant.id,
        actor_user_id=current_user.id,
        batch_size=current_app.config["DATASOURCE_SCHEDULE_BATCH_SIZE"],
        max_retries=current_app.config["DATASOURCE_MAX_RETRIES"],
    )

    if result["due_count"]:
        log_audit_event(
            tenant.id,
            "datasource.run_due_triggered",
            result,
            actor_user_id=current_user.id,
        )
        db.session.commit()

    flash(
        "Due sources checked: "
        f"{result['due_count']} (executed {result['executed']}, "
        f"skipped {result['skipped']}, failed {result['failed']}, throttled {result['throttled']}).",
        "info",
    )
    return redirect(url_for("datasources.list_sources", tenant=tenant.slug))


@bp.post("/check-health")
@login_required
@permission_required("workspace.manage_integrations")
def check_health():
    tenant = g.current_tenant or current_user.tenant
    result = execute_health_checks_for_tenant(
        tenant_id=tenant.id,
        batch_size=current_app.config["DATASOURCE_HEALTH_CHECK_BATCH_SIZE"],
        failure_threshold=current_app.config["DATASOURCE_HEALTH_FAILURE_THRESHOLD"],
    )
    alert_result = maybe_send_health_alerts_for_tenant(
        tenant=tenant,
        sources=result.get("sources_checked", []),
        cooldown_minutes=current_app.config["DATASOURCE_ALERT_COOLDOWN_MINUTES"],
        email_enabled=current_app.config["DATASOURCE_ALERT_EMAIL_ENABLED"],
        webhook_enabled=current_app.config["DATASOURCE_ALERT_WEBHOOK_ENABLED"],
        webhook_timeout_seconds=current_app.config["DATASOURCE_ALERT_WEBHOOK_TIMEOUT_SECONDS"],
        default_on_degraded=current_app.config["DATASOURCE_ALERT_DEFAULT_ON_DEGRADED"],
        default_on_unhealthy=current_app.config["DATASOURCE_ALERT_DEFAULT_ON_UNHEALTHY"],
    )
    log_audit_event(
        tenant.id,
        "datasource.health_checks_run",
        {
            "checked": result["checked"],
            "healthy": result["healthy"],
            "degraded": result["degraded"],
            "unhealthy": result["unhealthy"],
            "failed": result["failed"],
            "alerts": alert_result,
        },
        actor_user_id=current_user.id,
    )
    db.session.commit()
    flash(
        "Health checks: "
        f"checked {result['checked']}, healthy {result['healthy']}, "
        f"degraded {result['degraded']}, unhealthy {result['unhealthy']}, "
        f"alerts sent {alert_result['sent']} (email {alert_result['sent_email']}, "
        f"webhook {alert_result['sent_webhook']}).",
        "info",
    )
    return redirect(url_for("datasources.list_sources", tenant=tenant.slug))


@bp.get("/jobs/<int:job_id>")
@login_required
@permission_required("workspace.manage_integrations")
def job_detail(job_id):
    tenant = g.current_tenant or current_user.tenant
    job = SyncJob.query.filter_by(id=job_id, tenant_id=tenant.id).first_or_404()
    errors = (
        SyncJobError.query.filter_by(sync_job_id=job.id)
        .order_by(SyncJobError.row_number.asc())
        .limit(100)
        .all()
    )
    summary = json.loads(job.summary_json or "{}")
    return render_template("datasources/job_detail.html", tenant=tenant, job=job, errors=errors, summary=summary)


@bp.route("/<int:source_id>/webhook-verification", methods=["GET", "POST"])
@login_required
@permission_required("workspace.manage_integrations")
def webhook_verification(source_id):
    tenant = g.current_tenant or current_user.tenant
    source = DataSource.query.filter_by(id=source_id, tenant_id=tenant.id).first_or_404()
    cfg = json.loads(source.config_json or "{}")

    payload_format = (cfg.get("alert_webhook_format") or "generic").strip().lower()
    if payload_format not in {"generic", "slack", "teams"}:
        payload_format = "generic"
    health_status = "unhealthy"
    error_message = "Verification sample alert"

    if request.method == "POST":
        payload_format = (request.form.get("payload_format") or payload_format).strip().lower()
        if payload_format not in {"generic", "slack", "teams"}:
            payload_format = "generic"
        health_status = (request.form.get("health_status") or "unhealthy").strip().lower()
        if health_status not in {"degraded", "unhealthy"}:
            health_status = "unhealthy"
        error_message = (request.form.get("error_message") or "Verification sample alert").strip()

    payload = build_data_source_health_alert_payload(
        payload_format=payload_format,
        workspace_slug=tenant.slug,
        source_name=source.name,
        health_status=health_status,
        error_message=error_message,
    )
    payload_json = json.dumps(payload, indent=2)

    signature_header = (cfg.get("alert_webhook_signature_header") or "X-CoachingOS-Signature").strip()
    signing_secret = get_source_secret(
        tenant_id=tenant.id,
        data_source_id=source.id,
        name="alert_webhook_signing_secret",
        default="",
    )
    signature_headers = {}
    if signing_secret:
        signature_headers = build_data_source_signature_headers(
            payload_json=payload_json,
            signing_secret=signing_secret,
            signature_header=signature_header,
        )

    return render_template(
        "datasources/webhook_verification.html",
        tenant=tenant,
        source=source,
        payload_format=payload_format,
        health_status=health_status,
        error_message=error_message,
        payload_json=payload_json,
        signature_header=signature_header,
        signature_headers=signature_headers,
        has_signing_secret=bool(signing_secret),
    )


@bp.get("/alerts")
@login_required
@permission_required("workspace.manage_integrations")
def alert_analytics():
    tenant = g.current_tenant or current_user.tenant
    window = (request.args.get("window") or "7d").strip().lower()
    if window not in {"24h", "7d", "30d"}:
        window = "7d"
    since_at = _analytics_window_to_start(window)

    scoped = DataSourceAlertEvent.query.filter(
        DataSourceAlertEvent.tenant_id == tenant.id,
        DataSourceAlertEvent.created_at >= since_at,
    )
    total_events = scoped.count()
    attempted_count = scoped.filter(DataSourceAlertEvent.delivery_attempted.is_(True)).count()
    failed_count = scoped.filter(DataSourceAlertEvent.delivery_failed.is_(True)).count()
    success_count = scoped.filter(
        DataSourceAlertEvent.delivery_attempted.is_(True),
        DataSourceAlertEvent.delivery_failed.is_(False),
    ).count()
    skipped_count = scoped.filter(DataSourceAlertEvent.delivery_attempted.is_(False)).count()
    manual_count = scoped.filter(DataSourceAlertEvent.trigger_type == "manual_test").count()
    automatic_count = scoped.filter(DataSourceAlertEvent.trigger_type == "automatic").count()

    channel_totals = scoped.with_entities(
        func.coalesce(func.sum(DataSourceAlertEvent.sent_email), 0),
        func.coalesce(func.sum(DataSourceAlertEvent.sent_webhook), 0),
    ).first()
    sent_email_total = int(channel_totals[0] or 0)
    sent_webhook_total = int(channel_totals[1] or 0)

    failure_rate_pct = round((failed_count / attempted_count) * 100, 1) if attempted_count else 0.0
    success_rate_pct = round((success_count / attempted_count) * 100, 1) if attempted_count else 0.0

    top_failing_sources = (
        db.session.query(
            DataSource.id.label("source_id"),
            DataSource.name.label("source_name"),
            func.count(DataSourceAlertEvent.id).label("failed_events"),
        )
        .join(DataSource, DataSource.id == DataSourceAlertEvent.data_source_id)
        .filter(
            DataSourceAlertEvent.tenant_id == tenant.id,
            DataSourceAlertEvent.created_at >= since_at,
            DataSourceAlertEvent.delivery_failed.is_(True),
        )
        .group_by(DataSource.id, DataSource.name)
        .order_by(func.count(DataSourceAlertEvent.id).desc(), DataSource.name.asc())
        .limit(8)
        .all()
    )

    recent_failures = (
        db.session.query(
            DataSourceAlertEvent.created_at,
            DataSourceAlertEvent.trigger_type,
            DataSourceAlertEvent.health_status,
            DataSourceAlertEvent.error_message,
            DataSourceAlertEvent.sent_email,
            DataSourceAlertEvent.sent_webhook,
            DataSource.name.label("source_name"),
        )
        .join(DataSource, DataSource.id == DataSourceAlertEvent.data_source_id)
        .filter(
            DataSourceAlertEvent.tenant_id == tenant.id,
            DataSourceAlertEvent.created_at >= since_at,
            DataSourceAlertEvent.delivery_failed.is_(True),
        )
        .order_by(DataSourceAlertEvent.created_at.desc())
        .limit(20)
        .all()
    )

    trend_days = 1 if window == "24h" else (30 if window == "30d" else 7)
    trend_start = datetime.utcnow() - timedelta(days=trend_days - 1)
    trend_rows = (
        scoped.filter(DataSourceAlertEvent.created_at >= trend_start)
        .with_entities(DataSourceAlertEvent.created_at, DataSourceAlertEvent.delivery_failed)
        .all()
    )
    buckets = {}
    for row in trend_rows:
        day_key = row.created_at.strftime("%Y-%m-%d")
        if day_key not in buckets:
            buckets[day_key] = {"label": day_key, "total": 0, "failed": 0}
        buckets[day_key]["total"] += 1
        if row.delivery_failed:
            buckets[day_key]["failed"] += 1
    trend = [buckets[key] for key in sorted(buckets.keys())]

    return render_template(
        "datasources/alert_analytics.html",
        tenant=tenant,
        window=window,
        since_at=since_at,
        total_events=total_events,
        attempted_count=attempted_count,
        success_count=success_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
        manual_count=manual_count,
        automatic_count=automatic_count,
        sent_email_total=sent_email_total,
        sent_webhook_total=sent_webhook_total,
        success_rate_pct=success_rate_pct,
        failure_rate_pct=failure_rate_pct,
        top_failing_sources=top_failing_sources,
        recent_failures=recent_failures,
        trend=trend,
    )


@bp.route("/<int:source_id>/alert-policy-simulator", methods=["GET", "POST"])
@login_required
@permission_required("workspace.manage_integrations")
def alert_policy_simulator(source_id):
    tenant = g.current_tenant or current_user.tenant
    source = DataSource.query.filter_by(id=source_id, tenant_id=tenant.id).first_or_404()

    simulate_status = "unhealthy"
    if request.method == "POST":
        simulate_status = (request.form.get("simulate_status") or "unhealthy").strip().lower()
    if simulate_status not in {"degraded", "unhealthy"}:
        simulate_status = "unhealthy"

    evaluation = evaluate_alert_dispatch_for_source(
        source=source,
        health_status=simulate_status,
        cooldown_minutes=current_app.config["DATASOURCE_ALERT_COOLDOWN_MINUTES"],
        default_on_degraded=current_app.config["DATASOURCE_ALERT_DEFAULT_ON_DEGRADED"],
        default_on_unhealthy=current_app.config["DATASOURCE_ALERT_DEFAULT_ON_UNHEALTHY"],
    )

    return render_template(
        "datasources/alert_policy_simulator.html",
        tenant=tenant,
        source=source,
        simulate_status=simulate_status,
        evaluation=evaluation,
    )
