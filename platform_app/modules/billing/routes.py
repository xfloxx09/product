import hashlib
import hmac
import json
from datetime import datetime, timedelta
from urllib.error import HTTPError, URLError

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ...extensions import db
from ...models import Subscription, Tenant
from ...services.audit import log_audit_event
from ...services.plan_catalog import get_plan_definition, list_plan_definitions, normalize_plan
from ...services.stripe_client import create_billing_portal_session, create_checkout_session
from ...services.tenant_context import permission_required


bp = Blueprint("billing", __name__, url_prefix="/billing")


def _price_id_for_plan(plan):
    mapping = {
        "starter": current_app.config.get("STRIPE_PRICE_STARTER", ""),
        "growth": current_app.config.get("STRIPE_PRICE_GROWTH", ""),
        "enterprise": current_app.config.get("STRIPE_PRICE_ENTERPRISE", ""),
    }
    return mapping.get(plan, "")


def _verify_mock_stripe_signature(raw_body, signature_header, secret):
    """
    Basic HMAC check for development hardening.
    Expected header format: t=<unix_ts>,v1=<hex_hmac>.
    """
    if not secret:
        return False
    if not signature_header or "," not in signature_header:
        return False
    parts = {}
    for item in signature_header.split(","):
        if "=" in item:
            k, v = item.split("=", 1)
            parts[k.strip()] = v.strip()
    ts = parts.get("t")
    sig = parts.get("v1")
    if not ts or not sig:
        return False
    signed_payload = f"{ts}.{raw_body.decode('utf-8')}".encode("utf-8")
    computed = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, sig)


@bp.route("/checkout", methods=["GET", "POST"])
def checkout_placeholder():
    tenant = request.args.get("tenant", "")
    selected_plan = normalize_plan(request.args.get("plan"))
    plans = list_plan_definitions()

    if request.method == "POST":
        tenant_slug = (request.form.get("tenant") or "").strip().lower()
        plan = normalize_plan(request.form.get("plan"))

        tenant_obj = Tenant.query.filter_by(slug=tenant_slug).first()
        if not tenant_obj:
            flash("Tenant not found.", "danger")
            return redirect(url_for("billing.checkout_placeholder", tenant=tenant_slug))

        subscription = Subscription.query.filter_by(tenant_id=tenant_obj.id).first()
        if not subscription:
            subscription = Subscription(tenant_id=tenant_obj.id)
            db.session.add(subscription)

        tenant_obj.plan = plan
        stripe_key = current_app.config.get("STRIPE_SECRET_KEY", "")
        price_id = _price_id_for_plan(tenant_obj.plan)
        success_url = current_app.config.get("STRIPE_CHECKOUT_SUCCESS_URL") or url_for(
            "billing.checkout_success",
            _external=True,
        )
        cancel_url = current_app.config.get("STRIPE_CHECKOUT_CANCEL_URL") or url_for(
            "billing.checkout_placeholder",
            tenant=tenant_obj.slug,
            _external=True,
        )

        # Live flow when Stripe keys and price ids are present.
        if stripe_key and price_id:
            try:
                session = create_checkout_session(
                    api_key=stripe_key,
                    price_id=price_id,
                    tenant_slug=tenant_obj.slug,
                    customer_email=tenant_obj.contact_email,
                    success_url=success_url,
                    cancel_url=cancel_url,
                )
                checkout_url = session.get("url")
                if checkout_url:
                    subscription.status = "pending_checkout"
                    log_audit_event(
                        tenant_obj.id,
                        "billing.checkout_session_created",
                        {"plan": tenant_obj.plan, "session_id": session.get("id")},
                        actor_user_id=current_user.id if current_user.is_authenticated else None,
                    )
                    db.session.commit()
                    return redirect(checkout_url)
            except (HTTPError, URLError, TimeoutError) as exc:
                flash(f"Stripe checkout failed, using mock activation: {exc}", "warning")

        # Mock fallback if Stripe is not configured or live call failed.
        subscription.status = "active"
        subscription.current_period_end = datetime.utcnow() + timedelta(days=30)
        subscription.provider_customer_id = subscription.provider_customer_id or f"mock_cus_{tenant_obj.slug}"
        subscription.provider_subscription_id = subscription.provider_subscription_id or f"mock_sub_{tenant_obj.slug}"

        log_audit_event(
            tenant_obj.id,
            "billing.subscription_activated",
            {"plan": tenant_obj.plan, "status": subscription.status},
            actor_user_id=current_user.id if current_user.is_authenticated else None,
        )
        db.session.commit()
        flash("Subscription activated (mock mode).", "success")
        return redirect(url_for("auth.login"))

    return render_template(
        "billing/checkout_placeholder.html",
        tenant=tenant,
        selected_plan=selected_plan,
        plans=plans,
    )


@bp.post("/webhooks/stripe")
def stripe_webhook_placeholder():
    secret = current_app.config.get("STRIPE_WEBHOOK_SECRET", "")
    signature = request.headers.get("Stripe-Signature", "")
    raw_body = request.get_data() or b""
    if secret and not _verify_mock_stripe_signature(raw_body, signature, secret):
        return {"received": False, "error": "invalid_signature"}, 400
    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except ValueError:
        payload = {}
    event_type = payload.get("type", "unknown")
    data_obj = payload.get("data", {}).get("object", {})
    tenant_slug = data_obj.get("metadata", {}).get("tenant")
    customer_id = data_obj.get("customer")
    subscription_id = data_obj.get("subscription") or data_obj.get("id")
    tenant = Tenant.query.filter_by(slug=tenant_slug).first() if tenant_slug else None
    if tenant:
        subscription = Subscription.query.filter_by(tenant_id=tenant.id).first()
        if not subscription:
            subscription = Subscription(tenant_id=tenant.id)
            db.session.add(subscription)

        if customer_id:
            subscription.provider_customer_id = customer_id
        if subscription_id:
            subscription.provider_subscription_id = subscription_id

        if event_type in {"checkout.session.completed", "invoice.paid"}:
            subscription.status = "active"
        elif event_type in {"customer.subscription.updated"}:
            stripe_status = data_obj.get("status")
            if stripe_status:
                subscription.status = stripe_status
            cpe = data_obj.get("current_period_end")
            if cpe:
                try:
                    subscription.current_period_end = datetime.utcfromtimestamp(int(cpe))
                except (ValueError, TypeError):
                    pass
        elif event_type in {"customer.subscription.deleted", "invoice.payment_failed"}:
            subscription.status = "past_due"

        log_audit_event(
            tenant.id,
            "billing.webhook_received",
            {"event_type": event_type, "customer_id": customer_id},
            actor_user_id=None,
        )
        db.session.commit()
    return {"received": True, "event_type": event_type}, 202


@bp.get("/portal")
@login_required
@permission_required("billing.manage")
def billing_portal():
    tenant = current_user.tenant
    subscription = Subscription.query.filter_by(tenant_id=tenant.id).first()
    plan_definition = get_plan_definition(tenant.plan)
    return render_template(
        "billing/portal.html",
        tenant=tenant,
        subscription=subscription,
        plan_definition=plan_definition,
    )


@bp.get("/checkout/success")
def checkout_success():
    flash("Checkout success received. Subscription state will sync via webhook.", "success")
    return redirect(url_for("auth.login"))


@bp.post("/portal/session")
@login_required
@permission_required("billing.manage")
def portal_session():
    tenant = current_user.tenant
    subscription = Subscription.query.filter_by(tenant_id=tenant.id).first()
    if not subscription or not subscription.provider_customer_id:
        flash("No Stripe customer found for this workspace.", "warning")
        return redirect(url_for("billing.billing_portal"))

    stripe_key = current_app.config.get("STRIPE_SECRET_KEY", "")
    if not stripe_key:
        flash("Stripe key missing; cannot open live billing portal.", "warning")
        return redirect(url_for("billing.billing_portal"))

    return_url = current_app.config.get("STRIPE_BILLING_RETURN_URL") or url_for(
        "billing.billing_portal",
        _external=True,
    )
    try:
        session = create_billing_portal_session(
            api_key=stripe_key,
            customer_id=subscription.provider_customer_id,
            return_url=return_url,
        )
        url = session.get("url")
        if url:
            log_audit_event(
                tenant.id,
                "billing.portal_session_created",
                {"customer_id": subscription.provider_customer_id},
                actor_user_id=current_user.id,
            )
            db.session.commit()
            return redirect(url)
    except (HTTPError, URLError, TimeoutError) as exc:
        flash(f"Billing portal creation failed: {exc}", "danger")
        return redirect(url_for("billing.billing_portal"))

    flash("Billing portal unavailable.", "danger")
    return redirect(url_for("billing.billing_portal"))
