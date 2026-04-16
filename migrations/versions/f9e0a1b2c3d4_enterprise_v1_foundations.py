"""Enterprise v1 domain foundations

Revision ID: f9e0a1b2c3d4
Revises: e1f2a3b4c5d6
Create Date: 2026-04-16
"""

from alembic import op
import sqlalchemy as sa


revision = "f9e0a1b2c3d4"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def _table_names(bind):
    return set(sa.inspect(bind).get_table_names())


def _column_names(bind, table_name):
    return {col["name"] for col in sa.inspect(bind).get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    tables = _table_names(bind)

    if "programs" not in tables:
        op.create_table(
            "programs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("key", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=140), nullable=False),
            sa.Column("channel", sa.String(length=30), nullable=False, server_default="inbound"),
            sa.Column("industry", sa.String(length=50), nullable=False, server_default="telecom"),
            sa.Column("client_name", sa.String(length=150), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "key", name="uq_program_tenant_key"),
        )
        op.create_index("ix_programs_key", "programs", ["key"], unique=False)

    if "skill_profiles" not in tables:
        op.create_table(
            "skill_profiles",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("key", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("direction", sa.String(length=30), nullable=False, server_default="inbound"),
            sa.Column("language", sa.String(length=20), nullable=False, server_default="de"),
            sa.Column("product_line", sa.String(length=80), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "key", name="uq_skill_profile_tenant_key"),
        )
        op.create_index("ix_skill_profiles_key", "skill_profiles", ["key"], unique=False)

    if "policy_packs" not in tables:
        op.create_table(
            "policy_packs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("cadence_days", sa.Integer(), nullable=False, server_default="30"),
            sa.Column("reminder_sla_hours", sa.Integer(), nullable=False, server_default="48"),
            sa.Column("escalation_hours", sa.Integer(), nullable=False, server_default="72"),
            sa.Column("notes_retention_days", sa.Integer(), nullable=False, server_default="365"),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "name", name="uq_policy_pack_tenant_name"),
        )

    if "evaluation_templates" not in tables:
        op.create_table(
            "evaluation_templates",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("program_id", sa.Integer(), nullable=True),
            sa.Column("policy_pack_id", sa.Integer(), nullable=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
            sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["program_id"], ["programs.id"]),
            sa.ForeignKeyConstraint(["policy_pack_id"], ["policy_packs.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "name", name="uq_eval_template_tenant_name"),
        )

    if "evaluation_items" not in tables:
        op.create_table(
            "evaluation_items",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("template_id", sa.Integer(), nullable=False),
            sa.Column("key", sa.String(length=80), nullable=False),
            sa.Column("label", sa.String(length=160), nullable=False),
            sa.Column("weight", sa.Float(), nullable=False, server_default="1"),
            sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("pii_classification", sa.String(length=30), nullable=False, server_default="none"),
            sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["template_id"], ["evaluation_templates.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("template_id", "key", name="uq_eval_item_template_key"),
        )

    if "calibration_sessions" not in tables:
        op.create_table(
            "calibration_sessions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("program_id", sa.Integer(), nullable=True),
            sa.Column("evaluation_template_id", sa.Integer(), nullable=True),
            sa.Column("facilitator_user_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="scheduled"),
            sa.Column("scheduled_for", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("summary_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["program_id"], ["programs.id"]),
            sa.ForeignKeyConstraint(["evaluation_template_id"], ["evaluation_templates.id"]),
            sa.ForeignKeyConstraint(["facilitator_user_id"], ["tenant_users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if "data_contracts" not in tables:
        op.create_table(
            "data_contracts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("source_type", sa.String(length=30), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("schema_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("mapping_rules_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "source_type", "version", name="uq_data_contract_source_version"),
        )

    if "domain_events" not in tables:
        op.create_table(
            "domain_events",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("aggregate_type", sa.String(length=50), nullable=False),
            sa.Column("aggregate_id", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.String(length=120), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_domain_events_tenant_type_created",
            "domain_events",
            ["tenant_id", "event_type", "created_at"],
            unique=False,
        )

    for table_name, columns in {
        "agent_profiles": [
            ("program_id", sa.Integer(), "programs.id"),
            ("skill_profile_id", sa.Integer(), "skill_profiles.id"),
        ],
        "coaching_cases": [
            ("program_id", sa.Integer(), "programs.id"),
            ("opened_at", sa.DateTime(), None),
            ("planned_at", sa.DateTime(), None),
            ("started_at", sa.DateTime(), None),
            ("closed_at", sa.DateTime(), None),
        ],
        "coaching_sessions": [
            ("policy_pack_id", sa.Integer(), "policy_packs.id"),
            ("subject", sa.String(length=255), None),
            ("coach_notes", sa.Text(), None),
            ("customer_journey_stage", sa.String(length=50), None),
        ],
        "coaching_action_items": [
            ("priority", sa.String(length=20), None),
            ("escalated_at", sa.DateTime(), None),
            ("pii_tags_json", sa.Text(), None),
        ],
        "scorecard_templates": [
            ("program_id", sa.Integer(), "programs.id"),
        ],
        "data_sources": [
            ("data_contract_id", sa.Integer(), "data_contracts.id"),
            ("pii_tags_json", sa.Text(), None),
        ],
        "connector_secrets": [
            ("rotation_version", sa.Integer(), None),
        ],
    }.items():
        if table_name not in _table_names(bind):
            continue
        existing_columns = _column_names(bind, table_name)
        with op.batch_alter_table(table_name) as batch_op:
            for col_name, col_type, fk_target in columns:
                if col_name in existing_columns:
                    continue
                nullable = col_name not in {"opened_at", "priority", "pii_tags_json", "rotation_version"}
                server_default = None
                if col_name == "opened_at":
                    server_default = sa.text("CURRENT_TIMESTAMP")
                elif col_name == "priority":
                    server_default = "normal"
                elif col_name == "pii_tags_json":
                    server_default = "[]"
                elif col_name == "rotation_version":
                    server_default = "1"
                batch_op.add_column(sa.Column(col_name, col_type, nullable=nullable, server_default=server_default))
                if fk_target:
                    target_table, target_col = fk_target.split(".")
                    batch_op.create_foreign_key(None, target_table, [col_name], [target_col])


def downgrade():
    bind = op.get_bind()
    tables = _table_names(bind)
    for table_name, col_names in {
        "connector_secrets": ["rotation_version"],
        "data_sources": ["pii_tags_json", "data_contract_id"],
        "scorecard_templates": ["program_id"],
        "coaching_action_items": ["pii_tags_json", "escalated_at", "priority"],
        "coaching_sessions": ["customer_journey_stage", "coach_notes", "subject", "policy_pack_id"],
        "coaching_cases": ["closed_at", "started_at", "planned_at", "opened_at", "program_id"],
        "agent_profiles": ["skill_profile_id", "program_id"],
    }.items():
        if table_name not in tables:
            continue
        existing_columns = _column_names(bind, table_name)
        with op.batch_alter_table(table_name) as batch_op:
            for col_name in col_names:
                if col_name in existing_columns:
                    batch_op.drop_column(col_name)

    for table_name in [
        "domain_events",
        "data_contracts",
        "calibration_sessions",
        "evaluation_items",
        "evaluation_templates",
        "policy_packs",
        "skill_profiles",
        "programs",
    ]:
        if table_name in _table_names(bind):
            op.drop_table(table_name)
