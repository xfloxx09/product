import hashlib
import hmac
import json
import time
from urllib import request as urlrequest

from flask import current_app


def send_plain_email(to_email, subject, body_text):
    sendgrid_api_key = current_app.config.get("SENDGRID_API_KEY", "")
    from_email = current_app.config.get("INVITE_FROM_EMAIL", "no-reply@coachingos.local")

    if not sendgrid_api_key:
        print(f"[MAILER:FALLBACK] to={to_email} subject={subject}")
        return {"provider": "console", "status": "queued"}

    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body_text}],
    }
    data = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(
        "https://api.sendgrid.com/v3/mail/send",
        data=data,
        headers={
            "Authorization": f"Bearer {sendgrid_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlrequest.urlopen(req, timeout=10) as resp:
        status_code = resp.getcode()
    return {"provider": "sendgrid", "status": status_code}


def send_invitation_email(to_email, full_name, invite_link, workspace_slug):
    subject = f"You are invited to {workspace_slug} on CoachingOS"
    body_text = (
        f"Hello {full_name},\n\n"
        f"You have been invited to join workspace '{workspace_slug}'.\n"
        f"Accept your invite here:\n{invite_link}\n\n"
        "If you did not expect this invitation, ignore this email."
    )
    return send_plain_email(to_email, subject, body_text)


def send_action_item_reminder_email(
    *,
    to_email,
    recipient_name,
    workspace_slug,
    session_agent_name,
    action_title,
    due_at=None,
):
    subject = f"[CoachingOS] Action item reminder - {workspace_slug}"
    body_text = (
        f"Hello {recipient_name or 'team member'},\n\n"
        f"This is a reminder for a coaching follow-up item.\n"
        f"Workspace: {workspace_slug}\n"
        f"Agent: {session_agent_name}\n"
        f"Action item: {action_title}\n"
        f"Due date: {due_at or '-'}\n\n"
        "Please review and complete the action item in CoachingOS."
    )
    return send_plain_email(to_email, subject, body_text)


def send_data_source_health_alert_email(*, to_email, workspace_slug, source_name, health_status, error_message):
    subject = f"[CoachingOS] Connector {health_status.upper()} - {workspace_slug}"
    body_text = (
        f"Workspace: {workspace_slug}\n"
        f"Data source: {source_name}\n"
        f"Health status: {health_status}\n"
        f"Last error: {error_message or '-'}\n\n"
        "Please review connector settings and run a connection test."
    )
    return send_plain_email(to_email, subject, body_text)


def send_data_source_health_alert_webhook(
    *,
    webhook_url,
    workspace_slug,
    source_name,
    health_status,
    error_message,
    payload_format="generic",
    auth_header="Authorization",
    auth_token="",
    signature_header="X-CoachingOS-Signature",
    signing_secret="",
    timeout_seconds=10,
):
    payload = build_data_source_health_alert_payload(
        payload_format=payload_format,
        workspace_slug=workspace_slug,
        source_name=source_name,
        health_status=health_status,
        error_message=error_message,
    )
    headers = {
        "Content-Type": "application/json",
    }
    if auth_token:
        if auth_header.lower() == "authorization" and not auth_token.lower().startswith("bearer "):
            headers[auth_header] = f"Bearer {auth_token}"
        else:
            headers[auth_header] = auth_token
    data = json.dumps(payload).encode("utf-8")
    if signing_secret:
        headers.update(
            build_data_source_signature_headers(
                payload_json=data.decode("utf-8"),
                signing_secret=signing_secret,
                signature_header=signature_header,
            )
        )
    req = urlrequest.Request(webhook_url, data=data, headers=headers, method="POST")
    with urlrequest.urlopen(req, timeout=timeout_seconds) as resp:
        status_code = resp.getcode()
    return {"provider": "webhook", "status": status_code}


def build_data_source_health_alert_payload(*, payload_format, workspace_slug, source_name, health_status, error_message):
    if payload_format == "slack":
        severity_emoji = ":red_circle:" if health_status == "unhealthy" else ":warning:"
        return {
            "text": f"{severity_emoji} Connector {health_status.upper()} - {workspace_slug}",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"{severity_emoji} *Connector {health_status.upper()}*\n"
                            f"*Workspace:* {workspace_slug}\n"
                            f"*Source:* {source_name}\n"
                            f"*Error:* {error_message or '-'}"
                        ),
                    },
                }
            ],
        }
    if payload_format == "teams":
        theme = "E81123" if health_status == "unhealthy" else "FFAA44"
        return {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": f"Connector {health_status.upper()} - {workspace_slug}",
            "themeColor": theme,
            "title": f"Connector {health_status.upper()}",
            "sections": [
                {
                    "facts": [
                        {"name": "Workspace", "value": workspace_slug},
                        {"name": "Source", "value": source_name},
                        {"name": "Health", "value": health_status},
                        {"name": "Error", "value": error_message or "-"},
                    ]
                }
            ],
        }
    # generic JSON payload
    return {
        "event": "datasource.health_alert",
        "workspace": workspace_slug,
        "source_name": source_name,
        "health_status": health_status,
        "error_message": error_message,
    }


def build_data_source_signature_headers(*, payload_json, signing_secret, signature_header, timestamp=None):
    ts = timestamp or str(int(time.time()))
    to_sign = f"{ts}.{payload_json}".encode("utf-8")
    signature = hmac.new(signing_secret.encode("utf-8"), to_sign, hashlib.sha256).hexdigest()
    return {
        "X-CoachingOS-Timestamp": ts,
        (signature_header or "X-CoachingOS-Signature"): f"sha256={signature}",
    }
