import json

from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ...extensions import db
from ...models import AgentProfile, CsvImportJob, CsvImportProfile, CsvImportRowError
from ...services.audit import log_audit_event
from ...services.imports import persist_import_errors, process_csv_rows, read_csv_upload
from ...services.plan_catalog import get_limit
from ...services.tenant_context import permission_required


bp = Blueprint("imports", __name__, url_prefix="/imports")


@bp.get("/mapper")
@login_required
@permission_required("workspace.manage_imports")
def mapper():
    """UI placeholder for tenant-specific CSV field mapping."""
    expected_fields = [
        "employee_id",
        "employee_name",
        "team_name",
        "coach_name",
        "coaching_date",
        "score",
    ]
    tenant = g.current_tenant or current_user.tenant
    profile = CsvImportProfile.query.filter_by(tenant_id=tenant.id, is_default=True).first()
    mapping = json.loads(profile.mapping_json) if profile else {}
    return render_template(
        "imports/mapper.html",
        expected_fields=expected_fields,
        mapping=mapping,
        tenant=tenant,
    )


@bp.route("/jobs/new", methods=["GET", "POST"])
@login_required
@permission_required("workspace.manage_imports")
def new_job():
    tenant = g.current_tenant or current_user.tenant
    profile = CsvImportProfile.query.filter_by(tenant_id=tenant.id, is_default=True).first()
    mapping = json.loads(profile.mapping_json) if profile else {}

    if request.method == "POST":
        upload = request.files.get("csv_file")
        run_mode = (request.form.get("run_mode") or "dry_run").strip().lower()
        transforms = {
            "score_scale": (request.form.get("score_scale") or "auto").strip(),
            "decimal_comma": bool(request.form.get("decimal_comma")),
            "strip_percent": bool(request.form.get("strip_percent", "1")),
            "date_format": (request.form.get("date_format") or "").strip(),
        }
        if run_mode not in {"dry_run", "apply"}:
            run_mode = "dry_run"
        if not upload or not upload.filename:
            flash("Please upload a CSV file.", "danger")
            return redirect(url_for("imports.new_job", tenant=tenant.slug))

        rows, headers = read_csv_upload(upload)
        if len(rows) == 0:
            flash("CSV file has no data rows.", "warning")
            return redirect(url_for("imports.new_job", tenant=tenant.slug))

        job = CsvImportJob(
            tenant_id=tenant.id,
            created_by_user_id=current_user.id,
            profile_id=profile.id if profile else None,
            source_filename=upload.filename,
            status="processing",
            run_mode=run_mode,
            total_rows=len(rows),
            mapping_snapshot_json=json.dumps(mapping),
            transformation_json=json.dumps(transforms),
            summary_json=json.dumps({"headers": headers}),
        )
        db.session.add(job)
        db.session.flush()

        summary, errors = process_csv_rows(
            tenant_id=tenant.id,
            coach_user_id=current_user.id,
            rows=rows,
            mapping=mapping,
            transforms=transforms,
            persist=run_mode == "apply",
            active_members_limit=get_limit(tenant.plan, "active_members"),
            current_active_members=AgentProfile.query.filter_by(tenant_id=tenant.id, status="active").count(),
        )
        job.success_rows = summary["created_sessions"]
        job.failed_rows = len(errors)
        base_status = "completed_with_errors" if errors else "completed"
        job.status = f"{run_mode}_{base_status}"
        job.summary_json = json.dumps(
            {
                "headers": headers,
                "result": summary,
                "run_mode": run_mode,
            }
        )
        if errors:
            db.session.add_all(persist_import_errors(job, errors))
        log_audit_event(
            tenant.id,
            "imports.job_processed",
            {
                "job_id": job.id,
                "filename": upload.filename,
                "run_mode": run_mode,
                "total_rows": job.total_rows,
                "success_rows": job.success_rows,
                "failed_rows": job.failed_rows,
            },
            actor_user_id=current_user.id,
        )
        db.session.commit()

        flash(
            "Import simulation completed." if run_mode == "dry_run" else "Import job applied successfully.",
            "success",
        )
        return redirect(url_for("imports.job_detail", job_id=job.id, tenant=tenant.slug))

    recent_jobs = (
        CsvImportJob.query.filter_by(tenant_id=tenant.id)
        .order_by(CsvImportJob.created_at.desc())
        .limit(20)
        .all()
    )
    return render_template(
        "imports/new_job.html",
        tenant=tenant,
        mapping=mapping,
        recent_jobs=recent_jobs,
    )


@bp.get("/jobs/<int:job_id>")
@login_required
@permission_required("workspace.manage_imports")
def job_detail(job_id):
    tenant = g.current_tenant or current_user.tenant
    job = CsvImportJob.query.filter_by(id=job_id, tenant_id=tenant.id).first_or_404()
    errors = (
        CsvImportRowError.query.filter_by(import_job_id=job.id)
        .order_by(CsvImportRowError.row_number.asc())
        .limit(100)
        .all()
    )
    summary = json.loads(job.summary_json or "{}")
    return render_template(
        "imports/job_detail.html",
        tenant=tenant,
        job=job,
        errors=errors,
        summary=summary,
    )
