from datetime import datetime, timedelta
import secrets

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ...extensions import db
from ...models import Tenant, TenantUser, UserInvitation
from ...services.audit import log_audit_event
from ...services.mailer import send_invitation_email
from ...services.rbac import list_effective_roles_for_tenant, role_key_exists_for_tenant
from ...services.tenant_context import permission_required


bp = Blueprint("auth", __name__, url_prefix="/auth")


def _build_invite_link(token):
    invite_link = url_for("auth.accept_invite", token=token, _external=True)
    if current_app.config.get("APP_BASE_URL"):
        invite_link = f"{current_app.config['APP_BASE_URL']}/auth/accept-invite/{token}"
    return invite_link


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("workspace.dashboard"))

    if request.method == "POST":
        tenant_slug = (request.form.get("tenant_slug") or "").strip().lower()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        tenant = Tenant.query.filter_by(slug=tenant_slug, is_active=True).first()
        if not tenant:
            flash("Workspace not found.", "danger")
            return render_template("auth/login.html")

        user = TenantUser.query.filter_by(tenant_id=tenant.id, email=email, is_active=True).first()
        if not user or not user.check_password(password):
            flash("Invalid credentials.", "danger")
            return render_template("auth/login.html")

        login_user(user, remember=True)
        log_audit_event(tenant.id, "auth.login_success", {"email": email}, actor_user_id=user.id)
        db.session.commit()
        return redirect(url_for("workspace.dashboard"))

    return render_template("auth/login.html")


@bp.route("/register-owner", methods=["GET", "POST"])
def register_owner():
    if request.method == "POST":
        tenant_slug = (request.form.get("tenant_slug") or "").strip().lower()
        full_name = (request.form.get("full_name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        tenant = Tenant.query.filter_by(slug=tenant_slug, is_active=True).first()
        if not tenant:
            flash("Workspace not found.", "danger")
            return render_template("auth/register_owner.html")

        if len(password) < 10:
            flash("Use a stronger password with at least 10 characters.", "warning")
            return render_template("auth/register_owner.html")

        exists = TenantUser.query.filter_by(tenant_id=tenant.id, email=email).first()
        if exists:
            flash("User already exists for this workspace.", "warning")
            return render_template("auth/register_owner.html")

        user = TenantUser(
            tenant_id=tenant.id,
            email=email,
            full_name=full_name,
            role="owner",
        )
        user.set_password(password)
        db.session.add(user)
        log_audit_event(tenant.id, "auth.owner_registered", {"email": email}, actor_user_id=None)
        db.session.commit()

        flash("Owner account created. Please login.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register_owner.html")


@bp.post("/logout")
@login_required
def logout():
    tenant_id = current_user.tenant_id
    actor_user_id = current_user.id
    logout_user()
    log_audit_event(tenant_id, "auth.logout", {}, actor_user_id=actor_user_id)
    db.session.commit()
    flash("You have been logged out.", "info")
    return redirect(url_for("public.home"))


@bp.route("/invite-user", methods=["GET", "POST"])
@login_required
@permission_required("workspace.manage_users")
def invite_user():
    tenant = current_user.tenant
    available_roles = list_effective_roles_for_tenant(tenant.id)
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        full_name = (request.form.get("full_name") or "").strip()
        role = (request.form.get("role") or "coach").strip().lower()

        if not role_key_exists_for_tenant(tenant.id, role):
            flash("Invalid role selected.", "danger")
            return redirect(url_for("auth.invite_user"))

        if not email or not full_name:
            flash("Email and full name are required.", "danger")
            return redirect(url_for("auth.invite_user"))

        user_exists = TenantUser.query.filter_by(tenant_id=tenant.id, email=email).first()
        if user_exists:
            flash("This user already exists in your workspace.", "warning")
            return redirect(url_for("auth.invite_user"))

        token = secrets.token_urlsafe(32)
        invite = UserInvitation(
            tenant_id=tenant.id,
            invited_by_user_id=current_user.id,
            email=email,
            full_name=full_name,
            role=role,
            token=token,
            expires_at=datetime.utcnow() + timedelta(hours=current_app.config["INVITE_TTL_HOURS"]),
        )
        db.session.add(invite)
        invite_link = _build_invite_link(token)
        delivery_status = "queued"
        try:
            delivery = send_invitation_email(email, full_name, invite_link, tenant.slug)
            delivery_status = str(delivery.get("status"))
        except Exception as exc:
            delivery_status = f"failed:{exc}"

        log_audit_event(
            tenant.id,
            "auth.user_invited",
            {"email": email, "role": role, "delivery_status": delivery_status},
            actor_user_id=current_user.id,
        )
        db.session.commit()

        flash(f"Invitation created. Share this link: {invite_link}", "success")
        return redirect(url_for("auth.invite_user"))

    active_invites = (
        UserInvitation.query.filter_by(tenant_id=tenant.id, accepted_at=None, revoked_at=None)
        .order_by(UserInvitation.created_at.desc())
        .limit(25)
        .all()
    )
    invite_links = {invite.id: _build_invite_link(invite.token) for invite in active_invites}
    return render_template(
        "auth/invite_user.html",
        active_invites=active_invites,
        invite_links=invite_links,
        tenant=tenant,
        available_roles=available_roles,
    )


@bp.post("/invite-user/<int:invite_id>/resend")
@login_required
@permission_required("workspace.manage_users")
def resend_invite(invite_id):
    tenant = current_user.tenant
    invite = UserInvitation.query.filter_by(id=invite_id, tenant_id=tenant.id).first_or_404()
    if invite.accepted_at or invite.revoked_at:
        flash("Invite is already closed.", "warning")
        return redirect(url_for("auth.invite_user"))

    invite.expires_at = datetime.utcnow() + timedelta(hours=current_app.config["INVITE_TTL_HOURS"])
    invite_link = _build_invite_link(invite.token)
    try:
        send_invitation_email(invite.email, invite.full_name, invite_link, tenant.slug)
        flash("Invitation resent.", "success")
    except Exception:
        flash("Invitation resend failed. Check mail configuration.", "danger")

    log_audit_event(
        tenant.id,
        "auth.user_invite_resent",
        {"email": invite.email, "invite_id": invite.id},
        actor_user_id=current_user.id,
    )
    db.session.commit()
    return redirect(url_for("auth.invite_user"))


@bp.post("/invite-user/<int:invite_id>/revoke")
@login_required
@permission_required("workspace.manage_users")
def revoke_invite(invite_id):
    tenant = current_user.tenant
    invite = UserInvitation.query.filter_by(id=invite_id, tenant_id=tenant.id).first_or_404()
    if invite.accepted_at:
        flash("Invite already accepted; cannot revoke.", "warning")
        return redirect(url_for("auth.invite_user"))
    if invite.revoked_at:
        flash("Invite already revoked.", "info")
        return redirect(url_for("auth.invite_user"))

    invite.revoked_at = datetime.utcnow()
    log_audit_event(
        tenant.id,
        "auth.user_invite_revoked",
        {"email": invite.email, "invite_id": invite.id},
        actor_user_id=current_user.id,
    )
    db.session.commit()
    flash("Invitation revoked.", "success")
    return redirect(url_for("auth.invite_user"))


@bp.route("/accept-invite/<token>", methods=["GET", "POST"])
def accept_invite(token):
    invite = UserInvitation.query.filter_by(token=token).first()
    if not invite or invite.accepted_at is not None or invite.revoked_at is not None:
        flash("Invitation is invalid or already used.", "danger")
        return redirect(url_for("auth.login"))
    if invite.expires_at < datetime.utcnow():
        flash("Invitation has expired.", "danger")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        password = request.form.get("password") or ""
        if len(password) < 10:
            flash("Password must be at least 10 characters.", "danger")
            return render_template("auth/accept_invite.html", invite=invite)

        existing_user = TenantUser.query.filter_by(tenant_id=invite.tenant_id, email=invite.email).first()
        if existing_user:
            flash("User already exists. Please login.", "warning")
            return redirect(url_for("auth.login"))

        tenant = Tenant.query.filter_by(id=invite.tenant_id, is_active=True).first()
        if not tenant:
            flash("Workspace not found.", "danger")
            return redirect(url_for("auth.login"))
        assigned_role = invite.role if role_key_exists_for_tenant(tenant.id, invite.role) else "viewer"
        if assigned_role != invite.role:
            flash("Invited role was changed by admin; applying current default role.", "warning")

        user = TenantUser(
            tenant_id=invite.tenant_id,
            email=invite.email,
            full_name=invite.full_name,
            role=assigned_role,
        )
        user.set_password(password)
        invite.accepted_at = datetime.utcnow()
        db.session.add(user)
        log_audit_event(
            invite.tenant_id,
            "auth.invite_accepted",
            {"email": invite.email, "role": invite.role},
            actor_user_id=None,
        )
        db.session.commit()
        flash("Account created successfully. Please login.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/accept_invite.html", invite=invite)
