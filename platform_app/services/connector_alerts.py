import json
from datetime import datetime, timedelta

from ..extensions import db
from ..models import DataSourceAlertEvent
from .connector_secrets import get_source_secret
from ..services.mailer import send_data_source_health_alert_email
from ..services.mailer import send_data_source_health_alert_webhook


def evaluate_alert_dispatch_for_source(
    *,
    source,
    health_status,
    cooldown_minutes,
    default_on_degraded=False,
    default_on_unhealthy=True,
    now=None,
):
    now = now or datetime.utcnow()
    cfg = json.loads(source.config_json or "{}")
    alert_policy = cfg.get("alert_policy") or {}
    on_degraded = bool(alert_policy.get("on_degraded", default_on_degraded))
    on_unhealthy = bool(alert_policy.get("on_unhealthy", default_on_unhealthy))
    channel_email = bool(alert_policy.get("channel_email", True))
    channel_webhook = bool(alert_policy.get("channel_webhook", False))
    per_source_cooldown = int(alert_policy.get("cooldown_minutes", cooldown_minutes) or cooldown_minutes)
    per_source_cooldown = max(1, per_source_cooldown)

    if health_status == "degraded" and not on_degraded:
        return {
            "will_send": False,
            "reason": "policy_disabled_degraded",
            "channel_email": channel_email,
            "channel_webhook": channel_webhook,
            "cooldown_minutes": per_source_cooldown,
            "minutes_until_next_send": None,
        }
    if health_status == "unhealthy" and not on_unhealthy:
        return {
            "will_send": False,
            "reason": "policy_disabled_unhealthy",
            "channel_email": channel_email,
            "channel_webhook": channel_webhook,
            "cooldown_minutes": per_source_cooldown,
            "minutes_until_next_send": None,
        }

    if source.last_health_alerted_at is None:
        return {
            "will_send": True,
            "reason": "never_alerted_before",
            "channel_email": channel_email,
            "channel_webhook": channel_webhook,
            "cooldown_minutes": per_source_cooldown,
            "minutes_until_next_send": 0,
        }

    if source.last_health_alert_status != health_status:
        return {
            "will_send": True,
            "reason": "status_changed",
            "channel_email": channel_email,
            "channel_webhook": channel_webhook,
            "cooldown_minutes": per_source_cooldown,
            "minutes_until_next_send": 0,
        }

    next_allowed_at = source.last_health_alerted_at + timedelta(minutes=per_source_cooldown)
    if now >= next_allowed_at:
        return {
            "will_send": True,
            "reason": "cooldown_elapsed",
            "channel_email": channel_email,
            "channel_webhook": channel_webhook,
            "cooldown_minutes": per_source_cooldown,
            "minutes_until_next_send": 0,
        }

    remaining = next_allowed_at - now
    remaining_minutes = int(max(1, remaining.total_seconds() // 60))
    return {
        "will_send": False,
        "reason": "cooldown_active",
        "channel_email": channel_email,
        "channel_webhook": channel_webhook,
        "cooldown_minutes": per_source_cooldown,
        "minutes_until_next_send": remaining_minutes,
    }


def _record_alert_event(*, tenant_id, source_id, trigger_type, health_status, error_message, dispatch):
    event = DataSourceAlertEvent(
        tenant_id=tenant_id,
        data_source_id=source_id,
        trigger_type=trigger_type,
        health_status=health_status,
        error_message=(error_message or "")[:255] or None,
        delivery_attempted=dispatch["delivery_attempted"],
        delivery_failed=dispatch["delivery_failed"],
        sent_email=dispatch["sent_email"],
        sent_webhook=dispatch["sent_webhook"],
        email_result_json=json.dumps(dispatch["email_result"]),
        webhook_result_json=json.dumps(dispatch["webhook_result"]),
    )
    db.session.add(event)


def _send_alert_channels(
    *,
    tenant,
    source,
    health_status,
    error_message,
    email_enabled,
    webhook_enabled,
    webhook_timeout_seconds,
    channel_email,
    channel_webhook,
):
    sent_email = 0
    sent_webhook = 0
    delivery_attempted = False
    delivery_failed = False
    email_result = {"configured": bool(email_enabled and channel_email), "attempted": False, "ok": False}
    webhook_result = {"configured": bool(webhook_enabled and channel_webhook), "attempted": False, "ok": False}

    cfg = json.loads(source.config_json or "{}")

    if email_enabled and channel_email:
        delivery_attempted = True
        email_result["attempted"] = True
        try:
            result = send_data_source_health_alert_email(
                to_email=tenant.contact_email,
                workspace_slug=tenant.slug,
                source_name=source.name,
                health_status=health_status,
                error_message=error_message,
            )
            sent_email += 1
            email_result.update({"ok": True, "provider": result.get("provider"), "status": result.get("status")})
        except Exception as exc:
            delivery_failed = True
            email_result["error"] = str(exc)

    if webhook_enabled and channel_webhook:
        webhook_url = (cfg.get("alert_webhook_url") or "").strip()
        if webhook_url:
            delivery_attempted = True
            webhook_result["attempted"] = True
            auth_header = (cfg.get("alert_webhook_auth_header") or "Authorization").strip()
            auth_token = get_source_secret(
                tenant_id=tenant.id,
                data_source_id=source.id,
                name="alert_webhook_token",
                default="",
            )
            payload_format = (cfg.get("alert_webhook_format") or "generic").strip().lower()
            signature_header = (cfg.get("alert_webhook_signature_header") or "X-CoachingOS-Signature").strip()
            signing_secret = get_source_secret(
                tenant_id=tenant.id,
                data_source_id=source.id,
                name="alert_webhook_signing_secret",
                default="",
            )
            try:
                result = send_data_source_health_alert_webhook(
                    webhook_url=webhook_url,
                    workspace_slug=tenant.slug,
                    source_name=source.name,
                    health_status=health_status,
                    error_message=error_message,
                    payload_format=payload_format,
                    auth_header=auth_header,
                    auth_token=auth_token,
                    signature_header=signature_header,
                    signing_secret=signing_secret,
                    timeout_seconds=webhook_timeout_seconds,
                )
                sent_webhook += 1
                webhook_result.update(
                    {"ok": True, "provider": result.get("provider"), "status": result.get("status")}
                )
            except Exception as exc:
                delivery_failed = True
                webhook_result["error"] = str(exc)
        else:
            webhook_result["reason"] = "missing_webhook_url"

    return {
        "delivery_attempted": delivery_attempted,
        "delivery_failed": delivery_failed,
        "sent_email": sent_email,
        "sent_webhook": sent_webhook,
        "email_result": email_result,
        "webhook_result": webhook_result,
    }


def maybe_send_health_alerts_for_tenant(
    *,
    tenant,
    sources,
    cooldown_minutes,
    email_enabled,
    webhook_enabled,
    webhook_timeout_seconds,
    default_on_degraded=False,
    default_on_unhealthy=True,
):
    """
    Send health alerts for degraded/unhealthy sources with cooldown + dedupe.
    Returns dict counters.
    """
    now = datetime.utcnow()
    sent = 0
    skipped = 0
    failed = 0
    sent_email = 0
    sent_webhook = 0
    for source in sources:
        if source.health_status not in {"degraded", "unhealthy"}:
            continue

        evaluation = evaluate_alert_dispatch_for_source(
            source=source,
            health_status=source.health_status,
            cooldown_minutes=cooldown_minutes,
            default_on_degraded=default_on_degraded,
            default_on_unhealthy=default_on_unhealthy,
            now=now,
        )
        if not evaluation["will_send"]:
            skipped += 1
            continue

        dispatch = _send_alert_channels(
            tenant=tenant,
            source=source,
            health_status=source.health_status,
            error_message=source.last_connection_error,
            email_enabled=email_enabled,
            webhook_enabled=webhook_enabled,
            webhook_timeout_seconds=webhook_timeout_seconds,
            channel_email=evaluation["channel_email"],
            channel_webhook=evaluation["channel_webhook"],
        )
        _record_alert_event(
            tenant_id=tenant.id,
            source_id=source.id,
            trigger_type="automatic",
            health_status=source.health_status,
            error_message=source.last_connection_error,
            dispatch=dispatch,
        )
        sent_email += dispatch["sent_email"]
        sent_webhook += dispatch["sent_webhook"]
        delivery_attempted = dispatch["delivery_attempted"]
        delivery_failed = dispatch["delivery_failed"]

        if not delivery_attempted:
            # no outbound channels configured, but still track state transition timestamp
            source.last_health_alerted_at = now
            source.last_health_alert_status = source.health_status
            sent += 1
            continue

        if not delivery_failed:
            source.last_health_alerted_at = now
            source.last_health_alert_status = source.health_status
            sent += 1
        else:
            failed += 1

    return {
        "sent": sent,
        "sent_email": sent_email,
        "sent_webhook": sent_webhook,
        "skipped": skipped,
        "failed": failed,
    }


def send_test_alert_for_source(
    *,
    tenant,
    source,
    health_status="unhealthy",
    error_message="Manual test alert",
    email_enabled=True,
    webhook_enabled=True,
    webhook_timeout_seconds=10,
):
    cfg = json.loads(source.config_json or "{}")
    policy = cfg.get("alert_policy") or {}
    channel_email = bool(policy.get("channel_email", True))
    channel_webhook = bool(policy.get("channel_webhook", False))
    dispatch = _send_alert_channels(
        tenant=tenant,
        source=source,
        health_status=health_status,
        error_message=error_message,
        email_enabled=email_enabled,
        webhook_enabled=webhook_enabled,
        webhook_timeout_seconds=webhook_timeout_seconds,
        channel_email=channel_email,
        channel_webhook=channel_webhook,
    )
    _record_alert_event(
        tenant_id=tenant.id,
        source_id=source.id,
        trigger_type="manual_test",
        health_status=health_status,
        error_message=error_message,
        dispatch=dispatch,
    )
    return {
        "sent_email": dispatch["sent_email"],
        "sent_webhook": dispatch["sent_webhook"],
        "delivery_attempted": dispatch["delivery_attempted"],
        "delivery_failed": dispatch["delivery_failed"],
        "email_result": dispatch["email_result"],
        "webhook_result": dispatch["webhook_result"],
    }
