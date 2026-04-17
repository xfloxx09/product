from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class TimestampMixin:
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class Tenant(TimestampMixin, db.Model):
    __tablename__ = "tenants"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    contact_email = db.Column(db.String(255), nullable=False)
    plan = db.Column(db.String(50), nullable=False, default="starter")
    industry = db.Column(db.String(50), nullable=False, default="telecom")
    locale = db.Column(db.String(10), nullable=False, default="de")
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    users = db.relationship("TenantUser", back_populates="tenant", cascade="all, delete-orphan")


class TenantUser(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "tenant_users"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "email", name="uq_tenant_user_email"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    full_name = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(50), nullable=False, default="owner")
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    tenant = db.relationship("Tenant", back_populates="users")

    def get_id(self):
        # Prevent cross-tenant collisions in login session IDs.
        return f"{self.tenant_id}:{self.id}"

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Team(TimestampMixin, db.Model):
    __tablename__ = "teams"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "name", name="uq_team_tenant_name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    manager_name = db.Column(db.String(150), nullable=True)


class Program(TimestampMixin, db.Model):
    __tablename__ = "programs"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "key", name="uq_program_tenant_key"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    key = db.Column(db.String(80), nullable=False, index=True)
    name = db.Column(db.String(140), nullable=False)
    channel = db.Column(db.String(30), nullable=False, default="inbound")
    industry = db.Column(db.String(50), nullable=False, default="telecom")
    client_name = db.Column(db.String(150), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class SkillProfile(TimestampMixin, db.Model):
    __tablename__ = "skill_profiles"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "key", name="uq_skill_profile_tenant_key"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    key = db.Column(db.String(80), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    direction = db.Column(db.String(30), nullable=False, default="inbound")
    language = db.Column(db.String(20), nullable=False, default="de")
    product_line = db.Column(db.String(80), nullable=True)


class PolicyPack(TimestampMixin, db.Model):
    __tablename__ = "policy_packs"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "name", name="uq_policy_pack_tenant_name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    cadence_days = db.Column(db.Integer, nullable=False, default=30)
    reminder_sla_hours = db.Column(db.Integer, nullable=False, default=48)
    escalation_hours = db.Column(db.Integer, nullable=False, default=72)
    notes_retention_days = db.Column(db.Integer, nullable=False, default=365)
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    config_json = db.Column(db.Text, nullable=False, default="{}")


class TenantRole(TimestampMixin, db.Model):
    __tablename__ = "tenant_roles"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "role_key", name="uq_tenant_role_key"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    role_key = db.Column(db.String(50), nullable=False, index=True)
    display_name = db.Column(db.String(100), nullable=False)
    permissions_json = db.Column(db.Text, nullable=False, default="[]")
    is_system = db.Column(db.Boolean, nullable=False, default=False)


class UserTeamScope(TimestampMixin, db.Model):
    __tablename__ = "user_team_scopes"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "user_id", "team_id", name="uq_user_team_scope"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("tenant_users.id"), nullable=False, index=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False, index=True)


class AgentProfile(TimestampMixin, db.Model):
    __tablename__ = "agent_profiles"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "employee_code", name="uq_agent_tenant_code"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=True, index=True)
    program_id = db.Column(db.Integer, db.ForeignKey("programs.id"), nullable=True, index=True)
    skill_profile_id = db.Column(db.Integer, db.ForeignKey("skill_profiles.id"), nullable=True, index=True)
    employee_code = db.Column(db.String(100), nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="active")

    team = db.relationship("Team")
    program = db.relationship("Program")
    skill_profile = db.relationship("SkillProfile")


class CoachingSession(TimestampMixin, db.Model):
    __tablename__ = "coaching_sessions"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    coaching_case_id = db.Column(db.Integer, db.ForeignKey("coaching_cases.id"), nullable=True, index=True)
    agent_id = db.Column(db.Integer, db.ForeignKey("agent_profiles.id"), nullable=False, index=True)
    coach_user_id = db.Column(db.Integer, db.ForeignKey("tenant_users.id"), nullable=False, index=True)
    policy_pack_id = db.Column(db.Integer, db.ForeignKey("policy_packs.id"), nullable=True, index=True)
    coaching_type = db.Column(db.String(80), nullable=False, default="quality")
    session_format = db.Column(db.String(30), nullable=False, default="one_to_one")
    delivery_mode = db.Column(db.String(30), nullable=False, default="side_by_side")
    channel = db.Column(db.String(30), nullable=False, default="call")
    subject = db.Column(db.String(255), nullable=True)
    score = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(30), nullable=False, default="completed")
    planned_start_at = db.Column(db.DateTime, nullable=True)
    planned_end_at = db.Column(db.DateTime, nullable=True)
    assigned_by_user_id = db.Column(db.Integer, db.ForeignKey("tenant_users.id"), nullable=True, index=True)
    assignment_notes = db.Column(db.Text, nullable=True)
    occurred_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    coach_notes = db.Column(db.Text, nullable=True)
    customer_journey_stage = db.Column(db.String(50), nullable=True)

    agent = db.relationship("AgentProfile")
    coach = db.relationship("TenantUser")
    assigned_by = db.relationship("TenantUser", foreign_keys=[assigned_by_user_id])
    coaching_case = db.relationship("CoachingCase")
    policy_pack = db.relationship("PolicyPack")
    coach_participants = db.relationship(
        "CoachingSessionCoach",
        back_populates="coaching_session",
        cascade="all, delete-orphan",
    )


class CoachingSessionCoach(TimestampMixin, db.Model):
    __tablename__ = "coaching_session_coaches"
    __table_args__ = (
        db.UniqueConstraint("coaching_session_id", "coach_user_id", name="uq_session_coach"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    coaching_session_id = db.Column(db.Integer, db.ForeignKey("coaching_sessions.id"), nullable=False, index=True)
    coach_user_id = db.Column(db.Integer, db.ForeignKey("tenant_users.id"), nullable=False, index=True)
    role = db.Column(db.String(30), nullable=False, default="coach")

    coaching_session = db.relationship("CoachingSession", back_populates="coach_participants")
    coach = db.relationship("TenantUser")


class CoachingActionItem(TimestampMixin, db.Model):
    __tablename__ = "coaching_action_items"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    coaching_session_id = db.Column(db.Integer, db.ForeignKey("coaching_sessions.id"), nullable=False, index=True)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("tenant_users.id"), nullable=True, index=True)
    title = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="open")
    priority = db.Column(db.String(20), nullable=False, default="normal")
    due_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    escalated_at = db.Column(db.DateTime, nullable=True)
    pii_tags_json = db.Column(db.Text, nullable=False, default="[]")

    coaching_session = db.relationship("CoachingSession")
    owner = db.relationship("TenantUser")


class AgentCoachingCadence(TimestampMixin, db.Model):
    __tablename__ = "agent_coaching_cadences"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "agent_id", name="uq_agent_cadence_agent"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    agent_id = db.Column(db.Integer, db.ForeignKey("agent_profiles.id"), nullable=False, index=True)
    cadence_days = db.Column(db.Integer, nullable=False, default=30)

    agent = db.relationship("AgentProfile")


class CoachingCase(TimestampMixin, db.Model):
    __tablename__ = "coaching_cases"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    program_id = db.Column(db.Integer, db.ForeignKey("programs.id"), nullable=True, index=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=True, index=True)
    agent_id = db.Column(db.Integer, db.ForeignKey("agent_profiles.id"), nullable=False, index=True)
    requested_by_user_id = db.Column(db.Integer, db.ForeignKey("tenant_users.id"), nullable=True, index=True)
    assigned_to_user_id = db.Column(db.Integer, db.ForeignKey("tenant_users.id"), nullable=True, index=True)
    title = db.Column(db.String(160), nullable=False)
    summary = db.Column(db.Text, nullable=True)
    source_type = db.Column(db.String(40), nullable=False, default="ad_hoc")
    coaching_format = db.Column(db.String(30), nullable=False, default="one_to_one")
    delivery_mode = db.Column(db.String(30), nullable=False, default="side_by_side")
    priority = db.Column(db.String(20), nullable=False, default="normal")
    status = db.Column(db.String(30), nullable=False, default="open")
    assigned_by_user_id = db.Column(db.Integer, db.ForeignKey("tenant_users.id"), nullable=True, index=True)
    assignment_notes = db.Column(db.Text, nullable=True)
    planned_for = db.Column(db.DateTime, nullable=True)
    due_at = db.Column(db.DateTime, nullable=True)
    opened_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    planned_at = db.Column(db.DateTime, nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    closed_at = db.Column(db.DateTime, nullable=True)

    program = db.relationship("Program")
    team = db.relationship("Team")
    agent = db.relationship("AgentProfile")
    requester = db.relationship("TenantUser", foreign_keys=[requested_by_user_id])
    assignee = db.relationship("TenantUser", foreign_keys=[assigned_to_user_id])
    assigned_by = db.relationship("TenantUser", foreign_keys=[assigned_by_user_id])


class ScorecardTemplate(TimestampMixin, db.Model):
    __tablename__ = "scorecard_templates"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "name", name="uq_scorecard_tenant_name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    program_id = db.Column(db.Integer, db.ForeignKey("programs.id"), nullable=True, index=True)
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    config_json = db.Column(db.Text, nullable=False, default="{}")

    program = db.relationship("Program")


class EvaluationTemplate(TimestampMixin, db.Model):
    __tablename__ = "evaluation_templates"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "name", name="uq_eval_template_tenant_name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    program_id = db.Column(db.Integer, db.ForeignKey("programs.id"), nullable=True, index=True)
    policy_pack_id = db.Column(db.Integer, db.ForeignKey("policy_packs.id"), nullable=True, index=True)
    name = db.Column(db.String(120), nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.String(30), nullable=False, default="draft")
    config_json = db.Column(db.Text, nullable=False, default="{}")

    program = db.relationship("Program")
    policy_pack = db.relationship("PolicyPack")


class EvaluationItem(TimestampMixin, db.Model):
    __tablename__ = "evaluation_items"
    __table_args__ = (
        db.UniqueConstraint("template_id", "key", name="uq_eval_item_template_key"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    template_id = db.Column(db.Integer, db.ForeignKey("evaluation_templates.id"), nullable=False, index=True)
    key = db.Column(db.String(80), nullable=False)
    label = db.Column(db.String(160), nullable=False)
    weight = db.Column(db.Float, nullable=False, default=1.0)
    is_required = db.Column(db.Boolean, nullable=False, default=True)
    pii_classification = db.Column(db.String(30), nullable=False, default="none")
    config_json = db.Column(db.Text, nullable=False, default="{}")

    template = db.relationship("EvaluationTemplate")


class CalibrationSession(TimestampMixin, db.Model):
    __tablename__ = "calibration_sessions"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    program_id = db.Column(db.Integer, db.ForeignKey("programs.id"), nullable=True, index=True)
    evaluation_template_id = db.Column(db.Integer, db.ForeignKey("evaluation_templates.id"), nullable=True, index=True)
    facilitator_user_id = db.Column(db.Integer, db.ForeignKey("tenant_users.id"), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False, default="scheduled")
    scheduled_for = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    summary_json = db.Column(db.Text, nullable=False, default="{}")

    program = db.relationship("Program")
    facilitator = db.relationship("TenantUser")
    evaluation_template = db.relationship("EvaluationTemplate")


class DataContract(TimestampMixin, db.Model):
    __tablename__ = "data_contracts"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "source_type", "version", name="uq_data_contract_source_version"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    source_type = db.Column(db.String(30), nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.String(20), nullable=False, default="active")
    schema_json = db.Column(db.Text, nullable=False, default="{}")
    mapping_rules_json = db.Column(db.Text, nullable=False, default="{}")


class Subscription(TimestampMixin, db.Model):
    __tablename__ = "subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True, unique=True)
    provider = db.Column(db.String(50), nullable=False, default="stripe")
    provider_customer_id = db.Column(db.String(120), nullable=True)
    provider_subscription_id = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(50), nullable=False, default="trialing")
    current_period_end = db.Column(db.DateTime, nullable=True)


class PlanDefinition(TimestampMixin, db.Model):
    __tablename__ = "plan_definitions"

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.String(50), nullable=False, unique=True, index=True)
    config_json = db.Column(db.Text, nullable=False, default="{}")


class CsvImportProfile(TimestampMixin, db.Model):
    __tablename__ = "csv_import_profiles"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "name", name="uq_csv_profile_tenant_name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    mapping_json = db.Column(db.Text, nullable=False, default="{}")
    is_default = db.Column(db.Boolean, nullable=False, default=False)

    tenant = db.relationship("Tenant")


class AuditEvent(TimestampMixin, db.Model):
    __tablename__ = "audit_events"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("tenant_users.id"), nullable=True, index=True)
    event_type = db.Column(db.String(120), nullable=False)
    details_json = db.Column(db.Text, nullable=False, default="{}")


class UserInvitation(TimestampMixin, db.Model):
    __tablename__ = "user_invitations"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "email", "accepted_at", name="uq_invite_tenant_email_state"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    invited_by_user_id = db.Column(db.Integer, db.ForeignKey("tenant_users.id"), nullable=False, index=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    full_name = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(50), nullable=False, default="coach")
    token = db.Column(db.String(255), nullable=False, unique=True, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    accepted_at = db.Column(db.DateTime, nullable=True)
    revoked_at = db.Column(db.DateTime, nullable=True)


class CsvImportJob(TimestampMixin, db.Model):
    __tablename__ = "csv_import_jobs"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("tenant_users.id"), nullable=False, index=True)
    profile_id = db.Column(db.Integer, db.ForeignKey("csv_import_profiles.id"), nullable=True, index=True)
    source_filename = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="uploaded")
    run_mode = db.Column(db.String(20), nullable=False, default="apply")
    total_rows = db.Column(db.Integer, nullable=False, default=0)
    success_rows = db.Column(db.Integer, nullable=False, default=0)
    failed_rows = db.Column(db.Integer, nullable=False, default=0)
    mapping_snapshot_json = db.Column(db.Text, nullable=False, default="{}")
    transformation_json = db.Column(db.Text, nullable=False, default="{}")
    summary_json = db.Column(db.Text, nullable=False, default="{}")

    creator = db.relationship("TenantUser")
    profile = db.relationship("CsvImportProfile")


class CsvImportRowError(TimestampMixin, db.Model):
    __tablename__ = "csv_import_row_errors"

    id = db.Column(db.Integer, primary_key=True)
    import_job_id = db.Column(db.Integer, db.ForeignKey("csv_import_jobs.id"), nullable=False, index=True)
    row_number = db.Column(db.Integer, nullable=False)
    row_payload_json = db.Column(db.Text, nullable=False, default="{}")
    error_message = db.Column(db.String(255), nullable=False)


class DataSource(TimestampMixin, db.Model):
    __tablename__ = "data_sources"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "name", name="uq_data_source_tenant_name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    source_type = db.Column(db.String(30), nullable=False, default="csv_upload")
    data_contract_id = db.Column(db.Integer, db.ForeignKey("data_contracts.id"), nullable=True, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    schedule = db.Column(db.String(40), nullable=False, default="manual")
    config_json = db.Column(db.Text, nullable=False, default="{}")
    last_synced_at = db.Column(db.DateTime, nullable=True)
    last_secret_rotated_at = db.Column(db.DateTime, nullable=True)
    last_connection_tested_at = db.Column(db.DateTime, nullable=True)
    last_connection_status = db.Column(db.String(20), nullable=True)
    last_connection_error = db.Column(db.String(255), nullable=True)
    connection_failure_count = db.Column(db.Integer, nullable=False, default=0)
    health_status = db.Column(db.String(20), nullable=False, default="unknown")
    last_health_alerted_at = db.Column(db.DateTime, nullable=True)
    last_health_alert_status = db.Column(db.String(20), nullable=True)
    last_error = db.Column(db.String(255), nullable=True)
    failure_count = db.Column(db.Integer, nullable=False, default=0)
    pii_tags_json = db.Column(db.Text, nullable=False, default="[]")

    data_contract = db.relationship("DataContract")


class DataSourceAlertEvent(TimestampMixin, db.Model):
    __tablename__ = "data_source_alert_events"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    data_source_id = db.Column(db.Integer, db.ForeignKey("data_sources.id"), nullable=False, index=True)
    trigger_type = db.Column(db.String(20), nullable=False, default="automatic")
    health_status = db.Column(db.String(20), nullable=False)
    error_message = db.Column(db.String(255), nullable=True)
    delivery_attempted = db.Column(db.Boolean, nullable=False, default=False)
    delivery_failed = db.Column(db.Boolean, nullable=False, default=False)
    sent_email = db.Column(db.Integer, nullable=False, default=0)
    sent_webhook = db.Column(db.Integer, nullable=False, default=0)
    email_result_json = db.Column(db.Text, nullable=False, default="{}")
    webhook_result_json = db.Column(db.Text, nullable=False, default="{}")

    data_source = db.relationship("DataSource")


class SyncJob(TimestampMixin, db.Model):
    __tablename__ = "sync_jobs"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    data_source_id = db.Column(db.Integer, db.ForeignKey("data_sources.id"), nullable=False, index=True)
    triggered_by_user_id = db.Column(db.Integer, db.ForeignKey("tenant_users.id"), nullable=False, index=True)
    run_mode = db.Column(db.String(20), nullable=False, default="dry_run")
    status = db.Column(db.String(30), nullable=False, default="queued")
    attempt_count = db.Column(db.Integer, nullable=False, default=1)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    source_filename = db.Column(db.String(255), nullable=True)
    total_rows = db.Column(db.Integer, nullable=False, default=0)
    success_rows = db.Column(db.Integer, nullable=False, default=0)
    failed_rows = db.Column(db.Integer, nullable=False, default=0)
    summary_json = db.Column(db.Text, nullable=False, default="{}")

    data_source = db.relationship("DataSource")


class SyncJobError(TimestampMixin, db.Model):
    __tablename__ = "sync_job_errors"

    id = db.Column(db.Integer, primary_key=True)
    sync_job_id = db.Column(db.Integer, db.ForeignKey("sync_jobs.id"), nullable=False, index=True)
    row_number = db.Column(db.Integer, nullable=False)
    error_message = db.Column(db.String(255), nullable=False)
    row_payload_json = db.Column(db.Text, nullable=False, default="{}")


class ConnectorSecret(TimestampMixin, db.Model):
    __tablename__ = "connector_secrets"
    __table_args__ = (
        db.UniqueConstraint("data_source_id", "name", name="uq_connector_secret_source_name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    data_source_id = db.Column(db.Integer, db.ForeignKey("data_sources.id"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    cipher_text = db.Column(db.Text, nullable=False)
    rotation_version = db.Column(db.Integer, nullable=False, default=1)


class DomainEvent(TimestampMixin, db.Model):
    __tablename__ = "domain_events"
    __table_args__ = (
        db.Index("ix_domain_events_tenant_type_created", "tenant_id", "event_type", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    aggregate_type = db.Column(db.String(50), nullable=False)
    aggregate_id = db.Column(db.Integer, nullable=False, index=True)
    event_type = db.Column(db.String(120), nullable=False)
    payload_json = db.Column(db.Text, nullable=False, default="{}")
