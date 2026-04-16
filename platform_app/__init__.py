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
    from .services.data_governance import enforce_notes_retention
    from .services.job_orchestration import run_health_check_batch, run_scheduled_sync_batch

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
        totals = run_scheduled_sync_batch(app=app)
        print(
            f"Scheduled sync run finished: due={totals['due']}, "
            f"executed={totals['executed']}, failed={totals['failed']}, throttled={totals['throttled']}"
        )

    @app.cli.command("run-connector-health-checks")
    def run_connector_health_checks():
        totals = run_health_check_batch(app=app)
        print(
            "Connector health checks finished: "
            f"checked={totals['checked']}, degraded={totals['degraded']}, "
            f"unhealthy={totals['unhealthy']}, alerts_sent={totals['alerts_sent']}"
        )

    @app.cli.command("run-data-retention")
    def run_data_retention():
        tenants = Tenant.query.filter_by(is_active=True).all()
        total_cleared = 0
        for tenant in tenants:
            total_cleared += enforce_notes_retention(
                tenant_id=tenant.id,
                retention_days=app.config["DATA_RETENTION_DAYS"],
            )
        db.session.commit()
        print(f"Data retention run finished: cleared_notes={total_cleared}")

    return app
