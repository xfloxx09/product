from flask import Flask, g, jsonify, request
from flask_login import current_user

from .config import Settings
from .extensions import db, login_manager, migrate
from .services.rbac import user_has_permission
from .services.tenant_context import resolve_tenant_from_request


def create_app(config_class=Settings):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    from .models import Tenant, TenantUser
    from .services.connector_alerts import maybe_send_health_alerts_for_tenant
    from .services.sync_sources import execute_due_sources_for_tenant, execute_health_checks_for_tenant

    @login_manager.user_loader
    def load_user(user_id):
        try:
            tenant_id, local_user_id = user_id.split(":", 1)
            return TenantUser.query.filter_by(
                tenant_id=int(tenant_id),
                id=int(local_user_id),
                is_active=True,
            ).first()
        except (ValueError, AttributeError):
            # Backward-compat if plain user ID is present in a stale session.
            try:
                return TenantUser.query.filter_by(id=int(user_id), is_active=True).first()
            except (ValueError, TypeError):
                return None

    from .modules.public import bp as public_bp
    from .modules.onboarding import bp as onboarding_bp
    from .modules.billing import bp as billing_bp
    from .modules.imports import bp as imports_bp
    from .modules.auth import bp as auth_bp
    from .modules.workspace import bp as workspace_bp
    from .modules.api import bp as api_bp
    from .modules.settings import bp as settings_bp
    from .modules.datasources import bp as datasources_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(onboarding_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(imports_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(workspace_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(datasources_bp)

    @app.before_request
    def resolve_tenant_context():
        # Tenant can be resolved by header, query parameter, or logged-in user.
        g.current_tenant = resolve_tenant_from_request(request)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    @app.context_processor
    def inject_permissions():
        def has_permission(permission_name):
            return user_has_permission(current_user, permission_name)

        return {"has_permission": has_permission}

    @app.cli.command("init-db")
    def init_db():
        db.create_all()
        print("Database initialized.")

    @app.cli.command("run-scheduled-syncs")
    def run_scheduled_syncs():
        tenants = Tenant.query.filter_by(is_active=True).all()
        total_due = 0
        total_executed = 0
        total_failed = 0
        total_throttled = 0
        for tenant in tenants:
            system_user = TenantUser.query.filter_by(tenant_id=tenant.id, is_active=True).first()
            if not system_user:
                continue
            result = execute_due_sources_for_tenant(
                tenant_id=tenant.id,
                actor_user_id=system_user.id,
                batch_size=app.config["DATASOURCE_SCHEDULE_BATCH_SIZE"],
                max_retries=app.config["DATASOURCE_MAX_RETRIES"],
            )
            total_due += result["due_count"]
            total_executed += result["executed"]
            total_failed += result["failed"]
            total_throttled += result["throttled"]
        db.session.commit()
        print(
            f"Scheduled sync run finished: due={total_due}, "
            f"executed={total_executed}, failed={total_failed}, throttled={total_throttled}"
        )

    @app.cli.command("run-connector-health-checks")
    def run_connector_health_checks():
        tenants = Tenant.query.filter_by(is_active=True).all()
        total_checked = 0
        total_unhealthy = 0
        total_degraded = 0
        total_alerts_sent = 0
        for tenant in tenants:
            result = execute_health_checks_for_tenant(
                tenant_id=tenant.id,
                batch_size=app.config["DATASOURCE_HEALTH_CHECK_BATCH_SIZE"],
                failure_threshold=app.config["DATASOURCE_HEALTH_FAILURE_THRESHOLD"],
            )
            alert_result = maybe_send_health_alerts_for_tenant(
                tenant=tenant,
                sources=result.get("sources_checked", []),
                cooldown_minutes=app.config["DATASOURCE_ALERT_COOLDOWN_MINUTES"],
                email_enabled=app.config["DATASOURCE_ALERT_EMAIL_ENABLED"],
                webhook_enabled=app.config["DATASOURCE_ALERT_WEBHOOK_ENABLED"],
                webhook_timeout_seconds=app.config["DATASOURCE_ALERT_WEBHOOK_TIMEOUT_SECONDS"],
                default_on_degraded=app.config["DATASOURCE_ALERT_DEFAULT_ON_DEGRADED"],
                default_on_unhealthy=app.config["DATASOURCE_ALERT_DEFAULT_ON_UNHEALTHY"],
            )
            total_checked += result["checked"]
            total_unhealthy += result["unhealthy"]
            total_degraded += result["degraded"]
            total_alerts_sent += alert_result["sent"]
        db.session.commit()
        print(
            "Connector health checks finished: "
            f"checked={total_checked}, degraded={total_degraded}, "
            f"unhealthy={total_unhealthy}, alerts_sent={total_alerts_sent}"
        )

    return app
