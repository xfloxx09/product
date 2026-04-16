import json

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError

from ...extensions import db
from ...models import PlanDefinition, ScorecardTemplate, TenantRole, TenantUser
from ...services.audit import log_audit_event
from ...services.plan_catalog import PLAN_CATALOG, list_plan_definitions
from ...services.rbac import ALL_PERMISSIONS, list_effective_roles_for_tenant
from ...services.tenant_context import permission_required


bp = Blueprint("settings", __name__, url_prefix="/settings")


@bp.route("/workspace", methods=["GET", "POST"])
@login_required
@permission_required("settings.manage")
def workspace_settings():
    tenant = current_user.tenant
    scorecard = ScorecardTemplate.query.filter_by(tenant_id=tenant.id, is_default=True).first()

    if request.method == "POST":
        industry = (request.form.get("industry") or "generic").strip().lower()
        locale = (request.form.get("locale") or "de").strip().lower()
        scorecard_name = (request.form.get("scorecard_name") or "").strip()
        scorecard_json = (request.form.get("scorecard_json") or "").strip()

        if industry not in {"telecom", "energy", "generic"}:
            flash("Invalid industry value.", "danger")
            return redirect(url_for("settings.workspace_settings"))

        tenant.industry = industry
        tenant.locale = locale

        if scorecard and scorecard_json:
            try:
                json.loads(scorecard_json)
            except ValueError:
                flash("Scorecard JSON is invalid.", "danger")
                return redirect(url_for("settings.workspace_settings"))
            scorecard.name = scorecard_name or scorecard.name
            scorecard.config_json = scorecard_json

        log_audit_event(
            tenant.id,
            "settings.workspace_updated",
            {"industry": tenant.industry, "locale": tenant.locale},
            actor_user_id=current_user.id,
        )
        db.session.commit()
        flash("Workspace settings updated.", "success")
        return redirect(url_for("settings.workspace_settings"))

    return render_template(
        "settings/workspace.html",
        tenant=tenant,
        scorecard=scorecard,
    )


@bp.route("/plans", methods=["GET", "POST"])
@login_required
@permission_required("settings.manage")
def plan_catalog_settings():
    tenant = current_user.tenant
    feature_keys = list(next(iter(PLAN_CATALOG.values())).get("features", {}).keys())

    if request.method == "POST":
        updated_plan_ids = []
        try:
            for default_plan in list_plan_definitions():
                plan_id = default_plan["id"]
                name = (request.form.get(f"{plan_id}_name") or "").strip()
                price = (request.form.get(f"{plan_id}_price") or "").strip()
                active_members_raw = (request.form.get(f"{plan_id}_active_members") or "").strip()
                if active_members_raw:
                    try:
                        active_members = max(1, int(active_members_raw))
                    except ValueError:
                        flash(f"Invalid active member limit for '{plan_id}'.", "danger")
                        return redirect(url_for("settings.plan_catalog_settings"))
                else:
                    active_members = None

                features = {}
                for key in feature_keys:
                    features[key] = bool(request.form.get(f"{plan_id}_feature_{key}"))

                config = {
                    "name": name or default_plan["name"],
                    "price": price or default_plan["price"],
                    "limits": {"active_members": active_members},
                    "features": features,
                }

                row = PlanDefinition.query.filter_by(plan_id=plan_id).first()
                if not row:
                    row = PlanDefinition(plan_id=plan_id)
                    db.session.add(row)
                row.config_json = json.dumps(config)
                updated_plan_ids.append(plan_id)

            log_audit_event(
                tenant.id,
                "settings.plan_catalog_updated",
                {"plans_updated": updated_plan_ids},
                actor_user_id=current_user.id,
            )
            db.session.commit()
            flash("Plan catalog updated.", "success")
        except SQLAlchemyError:
            db.session.rollback()
            flash("Plan catalog table not ready yet. Run database initialization/migration first.", "danger")
        return redirect(url_for("settings.plan_catalog_settings"))

    plans = list_plan_definitions()
    return render_template(
        "settings/plan_catalog.html",
        tenant=tenant,
        plans=plans,
        feature_keys=feature_keys,
    )


@bp.route("/roles", methods=["GET", "POST"])
@login_required
@permission_required("settings.manage")
def role_settings():
    tenant = current_user.tenant
    if request.method == "POST":
        try:
            action = (request.form.get("action") or "upsert").strip().lower()
            if action == "delete":
                role_key = (request.form.get("role_key") or "").strip().lower()
                if role_key in {"owner", "admin", "manager", "coach", "viewer"}:
                    flash("Default roles cannot be deleted.", "warning")
                    return redirect(url_for("settings.role_settings"))
                role = TenantRole.query.filter_by(tenant_id=tenant.id, role_key=role_key).first()
                if not role:
                    flash("Role not found.", "warning")
                    return redirect(url_for("settings.role_settings"))
                in_use = TenantUser.query.filter_by(tenant_id=tenant.id, role=role_key).count() > 0
                if in_use:
                    flash("Role is assigned to users and cannot be deleted.", "danger")
                    return redirect(url_for("settings.role_settings"))
                db.session.delete(role)
                log_audit_event(
                    tenant.id,
                    "settings.role_deleted",
                    {"role_key": role_key},
                    actor_user_id=current_user.id,
                )
                db.session.commit()
                flash("Role deleted.", "success")
                return redirect(url_for("settings.role_settings"))

            role_key = (request.form.get("role_key") or "").strip().lower()
            display_name = (request.form.get("display_name") or "").strip()
            if not role_key or len(role_key) < 2:
                flash("Role key must be at least 2 characters.", "danger")
                return redirect(url_for("settings.role_settings"))
            if not display_name:
                flash("Display name is required.", "danger")
                return redirect(url_for("settings.role_settings"))
            if not role_key.replace("_", "").replace("-", "").isalnum():
                flash("Role key must be alphanumeric (dashes/underscores allowed).", "danger")
                return redirect(url_for("settings.role_settings"))
            selected_permissions = sorted(
                [perm for perm in request.form.getlist("permissions") if perm in ALL_PERMISSIONS]
            )
            role = TenantRole.query.filter_by(tenant_id=tenant.id, role_key=role_key).first()
            if not role:
                role = TenantRole(
                    tenant_id=tenant.id,
                    role_key=role_key,
                    is_system=role_key in {"owner", "admin", "manager", "coach", "viewer"},
                )
                db.session.add(role)
            if role_key == "owner" and "settings.manage" not in selected_permissions:
                selected_permissions.append("settings.manage")
            role.display_name = display_name
            role.permissions_json = json.dumps(selected_permissions)
            log_audit_event(
                tenant.id,
                "settings.role_upserted",
                {"role_key": role_key, "permissions": selected_permissions},
                actor_user_id=current_user.id,
            )
            db.session.commit()
            flash("Role saved.", "success")
            return redirect(url_for("settings.role_settings"))
        except SQLAlchemyError:
            db.session.rollback()
            flash("Role table not ready yet. Run database initialization/migration first.", "danger")
            return redirect(url_for("settings.role_settings"))

    roles = list_effective_roles_for_tenant(tenant.id)
    return render_template(
        "settings/roles.html",
        tenant=tenant,
        roles=roles,
        all_permissions=ALL_PERMISSIONS,
    )
