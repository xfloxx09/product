from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db


REQUIRED_COLUMNS = {
    "agent_profiles": {
        "program_id": "INTEGER",
        "skill_profile_id": "INTEGER",
    },
    "coaching_cases": {
        "program_id": "INTEGER",
        "opened_at": "TIMESTAMP",
        "planned_at": "TIMESTAMP",
        "started_at": "TIMESTAMP",
        "closed_at": "TIMESTAMP",
    },
    "coaching_sessions": {
        "policy_pack_id": "INTEGER",
        "subject": "VARCHAR(255)",
        "coach_notes": "TEXT",
        "customer_journey_stage": "VARCHAR(50)",
    },
    "coaching_action_items": {
        "priority": "VARCHAR(20)",
        "escalated_at": "TIMESTAMP",
        "pii_tags_json": "TEXT",
    },
    "scorecard_templates": {
        "program_id": "INTEGER",
    },
    "data_sources": {
        "data_contract_id": "INTEGER",
        "pii_tags_json": "TEXT",
    },
    "connector_secrets": {
        "rotation_version": "INTEGER",
    },
}


def ensure_runtime_schema_compatibility():
    """
    Best-effort runtime compatibility for environments where alembic migrations
    are not applied during deploy. This keeps the app bootable and avoids hard
    failures on newly introduced columns/tables.
    """
    engine = db.engine
    inspector = inspect(engine)

    # Create missing tables from ORM metadata first.
    db.create_all()

    with engine.begin() as conn:
        for table_name, column_map in REQUIRED_COLUMNS.items():
            if table_name not in inspector.get_table_names():
                continue
            existing = {c["name"] for c in inspector.get_columns(table_name)}
            for column_name, column_type in column_map.items():
                if column_name in existing:
                    continue
                ddl = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                # Conservative defaults to avoid null issues on hot paths.
                if column_name == "priority":
                    ddl += " DEFAULT 'normal'"
                elif column_name == "pii_tags_json":
                    ddl += " DEFAULT '[]'"
                elif column_name == "rotation_version":
                    ddl += " DEFAULT 1"
                try:
                    conn.execute(text(ddl))
                except SQLAlchemyError:
                    # Ignore if column already appeared due to race/parallel boot.
                    pass

