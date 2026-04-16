import os


class Settings:
    """Production-focused baseline settings for the SaaS app."""

    SECRET_KEY = os.environ.get("SECRET_KEY")
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY must be set.")

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///platform_app.db")
    if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace("postgres://", "postgresql://", 1)

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"

    _is_prod = (
        os.environ.get("RAILWAY_ENVIRONMENT") is not None
        or os.environ.get("FLASK_ENV") == "production"
    )
    SESSION_COOKIE_SECURE = _is_prod
    REMEMBER_COOKIE_SECURE = _is_prod

    INVITE_TTL_HOURS = int(os.environ.get("INVITE_TTL_HOURS", "72"))
    APP_BASE_URL = os.environ.get("APP_BASE_URL", "").rstrip("/")

    STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    STRIPE_PRICE_STARTER = os.environ.get("STRIPE_PRICE_STARTER", "")
    STRIPE_PRICE_GROWTH = os.environ.get("STRIPE_PRICE_GROWTH", "")
    STRIPE_PRICE_ENTERPRISE = os.environ.get("STRIPE_PRICE_ENTERPRISE", "")
    STRIPE_CHECKOUT_SUCCESS_URL = os.environ.get("STRIPE_CHECKOUT_SUCCESS_URL", "")
    STRIPE_CHECKOUT_CANCEL_URL = os.environ.get("STRIPE_CHECKOUT_CANCEL_URL", "")
    STRIPE_BILLING_RETURN_URL = os.environ.get("STRIPE_BILLING_RETURN_URL", "")
    SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
    INVITE_FROM_EMAIL = os.environ.get("INVITE_FROM_EMAIL", "no-reply@coachingos.local")
    CONNECTOR_SECRETS_KEY = os.environ.get("CONNECTOR_SECRETS_KEY", "")

    DATASOURCE_MAX_RETRIES = int(os.environ.get("DATASOURCE_MAX_RETRIES", "3"))
    DATASOURCE_SCHEDULE_BATCH_SIZE = int(os.environ.get("DATASOURCE_SCHEDULE_BATCH_SIZE", "25"))
    DATASOURCE_HEALTH_FAILURE_THRESHOLD = int(os.environ.get("DATASOURCE_HEALTH_FAILURE_THRESHOLD", "3"))
    DATASOURCE_HEALTH_CHECK_BATCH_SIZE = int(os.environ.get("DATASOURCE_HEALTH_CHECK_BATCH_SIZE", "25"))
    DATASOURCE_ALERT_COOLDOWN_MINUTES = int(os.environ.get("DATASOURCE_ALERT_COOLDOWN_MINUTES", "180"))
    DATASOURCE_ALERT_EMAIL_ENABLED = os.environ.get("DATASOURCE_ALERT_EMAIL_ENABLED", "1").strip() not in {"0", "false", "False"}
    DATASOURCE_ALERT_WEBHOOK_ENABLED = os.environ.get("DATASOURCE_ALERT_WEBHOOK_ENABLED", "0").strip() not in {"0", "false", "False"}
    DATASOURCE_ALERT_WEBHOOK_TIMEOUT_SECONDS = int(os.environ.get("DATASOURCE_ALERT_WEBHOOK_TIMEOUT_SECONDS", "10"))
    DATASOURCE_ALERT_DEFAULT_ON_DEGRADED = os.environ.get("DATASOURCE_ALERT_DEFAULT_ON_DEGRADED", "0").strip() not in {"0", "false", "False"}
    DATASOURCE_ALERT_DEFAULT_ON_UNHEALTHY = os.environ.get("DATASOURCE_ALERT_DEFAULT_ON_UNHEALTHY", "1").strip() not in {"0", "false", "False"}
