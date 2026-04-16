import re

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ...extensions import db
from ...models import Tenant, TenantUser
from ...services.audit import log_audit_event
from ...services.plan_catalog import list_plan_definitions, normalize_plan
from ...services.provisioning import seed_tenant_defaults


bp = Blueprint("onboarding", __name__, url_prefix="/onboarding")


def _slugify(value):
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:100]


@bp.route("/start", methods=["GET", "POST"])
def start():
    plans = list_plan_definitions()
    if request.method == "POST":
        company_name = (request.form.get("company_name") or "").strip()
        contact_email = (request.form.get("contact_email") or "").strip()
        owner_name = (request.form.get("owner_name") or "").strip()
        owner_email = (request.form.get("owner_email") or "").strip().lower()
        owner_password = request.form.get("owner_password") or ""
        plan = normalize_plan(request.form.get("plan"))
        industry = (request.form.get("industry") or "telecom").strip().lower()
        slug = _slugify(request.form.get("slug") or company_name)

        if not company_name or not contact_email or not slug or not owner_name or not owner_email:
            flash("Please provide all required fields.", "danger")
            return render_template("onboarding/start.html", plans=plans)

        if len(owner_password) < 10:
            flash("Owner password must be at least 10 characters.", "danger")
            return render_template("onboarding/start.html", plans=plans)

        existing_slug = Tenant.query.filter_by(slug=slug).first()
        if existing_slug:
            flash("This workspace slug already exists. Please choose another one.", "warning")
            return render_template("onboarding/start.html", plans=plans)

        tenant = Tenant(
            name=company_name,
            contact_email=contact_email,
            slug=slug,
            plan=plan,
            industry=industry if industry in {"telecom", "energy", "generic"} else "generic",
        )
        db.session.add(tenant)
        db.session.flush()

        owner = TenantUser(
            tenant_id=tenant.id,
            full_name=owner_name,
            email=owner_email,
            role="owner",
        )
        owner.set_password(owner_password)
        db.session.add(owner)

        seed_tenant_defaults(tenant)
        log_audit_event(
            tenant.id,
            "onboarding.workspace_created",
            {"slug": tenant.slug, "industry": tenant.industry, "plan": tenant.plan},
            actor_user_id=None,
        )
        db.session.commit()

        flash("Workspace and owner account created. Next step: checkout.", "success")
        return redirect(url_for("billing.checkout_placeholder", tenant=tenant.slug, plan=tenant.plan))

    return render_template("onboarding/start.html", plans=plans)
