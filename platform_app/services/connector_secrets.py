import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app

from ..extensions import db
from ..models import ConnectorSecret


def _build_fernet():
    key = (current_app.config.get("CONNECTOR_SECRETS_KEY") or "").strip()
    if key:
        return Fernet(key.encode("utf-8"))

    # Fallback: derive deterministic key from SECRET_KEY for development.
    secret_key = current_app.config.get("SECRET_KEY", "")
    digest = hashlib.sha256((f"connector-secrets::{secret_key}").encode("utf-8")).digest()
    derived = base64.urlsafe_b64encode(digest)
    return Fernet(derived)


def _encrypt(value):
    f = _build_fernet()
    return f.encrypt((value or "").encode("utf-8")).decode("utf-8")


def _decrypt(value):
    f = _build_fernet()
    return f.decrypt((value or "").encode("utf-8")).decode("utf-8")


def upsert_source_secrets(*, tenant_id, data_source_id, secrets_dict):
    for name, raw_value in (secrets_dict or {}).items():
        value = (raw_value or "").strip()
        if not value:
            continue
        row = ConnectorSecret.query.filter_by(
            tenant_id=tenant_id,
            data_source_id=data_source_id,
            name=name,
        ).first()
        cipher = _encrypt(value)
        if row:
            row.cipher_text = cipher
        else:
            db.session.add(
                ConnectorSecret(
                    tenant_id=tenant_id,
                    data_source_id=data_source_id,
                    name=name,
                    cipher_text=cipher,
                )
            )


def clear_source_secret(*, tenant_id, data_source_id, name):
    row = ConnectorSecret.query.filter_by(
        tenant_id=tenant_id,
        data_source_id=data_source_id,
        name=name,
    ).first()
    if row:
        db.session.delete(row)


def get_source_secret(*, tenant_id, data_source_id, name, default=""):
    row = ConnectorSecret.query.filter_by(
        tenant_id=tenant_id,
        data_source_id=data_source_id,
        name=name,
    ).first()
    if not row:
        return default
    try:
        return _decrypt(row.cipher_text)
    except (InvalidToken, ValueError):
        return default


def has_source_secret(*, tenant_id, data_source_id, name):
    row = ConnectorSecret.query.filter_by(
        tenant_id=tenant_id,
        data_source_id=data_source_id,
        name=name,
    ).first()
    return row is not None
