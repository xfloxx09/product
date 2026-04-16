BEGIN;

DROP TABLE IF EXISTS connector_secrets CASCADE;
DROP TABLE IF EXISTS sync_job_errors CASCADE;
DROP TABLE IF EXISTS sync_jobs CASCADE;
DROP TABLE IF EXISTS data_source_alert_events CASCADE;
DROP TABLE IF EXISTS data_sources CASCADE;
DROP TABLE IF EXISTS csv_import_row_errors CASCADE;
DROP TABLE IF EXISTS csv_import_jobs CASCADE;
DROP TABLE IF EXISTS user_invitations CASCADE;
DROP TABLE IF EXISTS audit_events CASCADE;
DROP TABLE IF EXISTS csv_import_profiles CASCADE;
DROP TABLE IF EXISTS plan_definitions CASCADE;
DROP TABLE IF EXISTS subscriptions CASCADE;
DROP TABLE IF EXISTS scorecard_templates CASCADE;
DROP TABLE IF EXISTS coaching_action_items CASCADE;
DROP TABLE IF EXISTS coaching_sessions CASCADE;
DROP TABLE IF EXISTS coaching_cases CASCADE;
DROP TABLE IF EXISTS agent_coaching_cadences CASCADE;
DROP TABLE IF EXISTS agent_profiles CASCADE;
DROP TABLE IF EXISTS user_team_scopes CASCADE;
DROP TABLE IF EXISTS tenant_roles CASCADE;
DROP TABLE IF EXISTS teams CASCADE;
DROP TABLE IF EXISTS tenant_users CASCADE;
DROP TABLE IF EXISTS tenants CASCADE;

CREATE TABLE tenants (
    id SERIAL PRIMARY KEY,
    slug VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(150) NOT NULL,
    contact_email VARCHAR(255) NOT NULL,
    plan VARCHAR(50) NOT NULL DEFAULT 'starter',
    industry VARCHAR(50) NOT NULL DEFAULT 'telecom',
    locale VARCHAR(10) NOT NULL DEFAULT 'de',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_tenants_slug ON tenants (slug);

CREATE TABLE tenant_users (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'owner',
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_tenant_user_email UNIQUE (tenant_id, email)
);
CREATE INDEX ix_tenant_users_tenant_id ON tenant_users (tenant_id);
CREATE INDEX ix_tenant_users_email ON tenant_users (email);

CREATE TABLE teams (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(120) NOT NULL,
    manager_name VARCHAR(150),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_team_tenant_name UNIQUE (tenant_id, name)
);
CREATE INDEX ix_teams_tenant_id ON teams (tenant_id);

CREATE TABLE tenant_roles (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    role_key VARCHAR(50) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    permissions_json TEXT NOT NULL DEFAULT '[]',
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_tenant_role_key UNIQUE (tenant_id, role_key)
);
CREATE INDEX ix_tenant_roles_tenant_id ON tenant_roles (tenant_id);
CREATE INDEX ix_tenant_roles_role_key ON tenant_roles (role_key);

CREATE TABLE user_team_scopes (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES tenant_users(id) ON DELETE CASCADE,
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_user_team_scope UNIQUE (tenant_id, user_id, team_id)
);
CREATE INDEX ix_user_team_scopes_tenant_id ON user_team_scopes (tenant_id);
CREATE INDEX ix_user_team_scopes_user_id ON user_team_scopes (user_id);
CREATE INDEX ix_user_team_scopes_team_id ON user_team_scopes (team_id);

CREATE TABLE agent_profiles (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    team_id INTEGER REFERENCES teams(id) ON DELETE SET NULL,
    employee_code VARCHAR(100) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_agent_tenant_code UNIQUE (tenant_id, employee_code)
);
CREATE INDEX ix_agent_profiles_tenant_id ON agent_profiles (tenant_id);
CREATE INDEX ix_agent_profiles_team_id ON agent_profiles (team_id);

CREATE TABLE coaching_cases (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    team_id INTEGER REFERENCES teams(id) ON DELETE SET NULL,
    agent_id INTEGER NOT NULL REFERENCES agent_profiles(id) ON DELETE CASCADE,
    requested_by_user_id INTEGER REFERENCES tenant_users(id) ON DELETE SET NULL,
    assigned_to_user_id INTEGER REFERENCES tenant_users(id) ON DELETE SET NULL,
    title VARCHAR(160) NOT NULL,
    summary TEXT,
    source_type VARCHAR(40) NOT NULL DEFAULT 'ad_hoc',
    priority VARCHAR(20) NOT NULL DEFAULT 'normal',
    status VARCHAR(30) NOT NULL DEFAULT 'open',
    due_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_coaching_cases_tenant_id ON coaching_cases (tenant_id);
CREATE INDEX ix_coaching_cases_team_id ON coaching_cases (team_id);
CREATE INDEX ix_coaching_cases_agent_id ON coaching_cases (agent_id);
CREATE INDEX ix_coaching_cases_requested_by_user_id ON coaching_cases (requested_by_user_id);
CREATE INDEX ix_coaching_cases_assigned_to_user_id ON coaching_cases (assigned_to_user_id);

CREATE TABLE coaching_sessions (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    coaching_case_id INTEGER REFERENCES coaching_cases(id) ON DELETE SET NULL,
    agent_id INTEGER NOT NULL REFERENCES agent_profiles(id) ON DELETE CASCADE,
    coach_user_id INTEGER NOT NULL REFERENCES tenant_users(id) ON DELETE CASCADE,
    coaching_type VARCHAR(80) NOT NULL DEFAULT 'quality',
    channel VARCHAR(30) NOT NULL DEFAULT 'call',
    score DOUBLE PRECISION,
    occurred_at TIMESTAMP NOT NULL DEFAULT NOW(),
    notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_coaching_sessions_tenant_id ON coaching_sessions (tenant_id);
CREATE INDEX ix_coaching_sessions_coaching_case_id ON coaching_sessions (coaching_case_id);
CREATE INDEX ix_coaching_sessions_agent_id ON coaching_sessions (agent_id);
CREATE INDEX ix_coaching_sessions_coach_user_id ON coaching_sessions (coach_user_id);

CREATE TABLE coaching_action_items (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    coaching_session_id INTEGER NOT NULL REFERENCES coaching_sessions(id) ON DELETE CASCADE,
    owner_user_id INTEGER REFERENCES tenant_users(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    due_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_coaching_action_items_tenant_id ON coaching_action_items (tenant_id);
CREATE INDEX ix_coaching_action_items_coaching_session_id ON coaching_action_items (coaching_session_id);
CREATE INDEX ix_coaching_action_items_owner_user_id ON coaching_action_items (owner_user_id);

CREATE TABLE agent_coaching_cadences (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_id INTEGER NOT NULL REFERENCES agent_profiles(id) ON DELETE CASCADE,
    cadence_days INTEGER NOT NULL DEFAULT 30,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_agent_cadence_agent UNIQUE (tenant_id, agent_id)
);
CREATE INDEX ix_agent_coaching_cadences_tenant_id ON agent_coaching_cadences (tenant_id);
CREATE INDEX ix_agent_coaching_cadences_agent_id ON agent_coaching_cadences (agent_id);

CREATE TABLE scorecard_templates (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(120) NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    config_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_scorecard_tenant_name UNIQUE (tenant_id, name)
);
CREATE INDEX ix_scorecard_templates_tenant_id ON scorecard_templates (tenant_id);

CREATE TABLE subscriptions (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL UNIQUE REFERENCES tenants(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL DEFAULT 'stripe',
    provider_customer_id VARCHAR(120),
    provider_subscription_id VARCHAR(120),
    status VARCHAR(50) NOT NULL DEFAULT 'trialing',
    current_period_end TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_subscriptions_tenant_id ON subscriptions (tenant_id);

CREATE TABLE plan_definitions (
    id SERIAL PRIMARY KEY,
    plan_id VARCHAR(50) NOT NULL UNIQUE,
    config_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_plan_definitions_plan_id ON plan_definitions (plan_id);

CREATE TABLE csv_import_profiles (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(120) NOT NULL,
    mapping_json TEXT NOT NULL DEFAULT '{}',
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_csv_profile_tenant_name UNIQUE (tenant_id, name)
);
CREATE INDEX ix_csv_import_profiles_tenant_id ON csv_import_profiles (tenant_id);

CREATE TABLE audit_events (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    actor_user_id INTEGER REFERENCES tenant_users(id) ON DELETE SET NULL,
    event_type VARCHAR(120) NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_audit_events_tenant_id ON audit_events (tenant_id);
CREATE INDEX ix_audit_events_actor_user_id ON audit_events (actor_user_id);

CREATE TABLE user_invitations (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    invited_by_user_id INTEGER NOT NULL REFERENCES tenant_users(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'coach',
    token VARCHAR(255) NOT NULL UNIQUE,
    expires_at TIMESTAMP NOT NULL,
    accepted_at TIMESTAMP,
    revoked_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_invite_tenant_email_state UNIQUE (tenant_id, email, accepted_at)
);
CREATE INDEX ix_user_invitations_tenant_id ON user_invitations (tenant_id);
CREATE INDEX ix_user_invitations_invited_by_user_id ON user_invitations (invited_by_user_id);
CREATE INDEX ix_user_invitations_email ON user_invitations (email);
CREATE INDEX ix_user_invitations_token ON user_invitations (token);

CREATE TABLE csv_import_jobs (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    created_by_user_id INTEGER NOT NULL REFERENCES tenant_users(id) ON DELETE CASCADE,
    profile_id INTEGER REFERENCES csv_import_profiles(id) ON DELETE SET NULL,
    source_filename VARCHAR(255) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'uploaded',
    run_mode VARCHAR(20) NOT NULL DEFAULT 'apply',
    total_rows INTEGER NOT NULL DEFAULT 0,
    success_rows INTEGER NOT NULL DEFAULT 0,
    failed_rows INTEGER NOT NULL DEFAULT 0,
    mapping_snapshot_json TEXT NOT NULL DEFAULT '{}',
    transformation_json TEXT NOT NULL DEFAULT '{}',
    summary_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_csv_import_jobs_tenant_id ON csv_import_jobs (tenant_id);
CREATE INDEX ix_csv_import_jobs_created_by_user_id ON csv_import_jobs (created_by_user_id);
CREATE INDEX ix_csv_import_jobs_profile_id ON csv_import_jobs (profile_id);

CREATE TABLE csv_import_row_errors (
    id SERIAL PRIMARY KEY,
    import_job_id INTEGER NOT NULL REFERENCES csv_import_jobs(id) ON DELETE CASCADE,
    row_number INTEGER NOT NULL,
    row_payload_json TEXT NOT NULL DEFAULT '{}',
    error_message VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_csv_import_row_errors_import_job_id ON csv_import_row_errors (import_job_id);

CREATE TABLE data_sources (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(120) NOT NULL,
    source_type VARCHAR(30) NOT NULL DEFAULT 'csv_upload',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    schedule VARCHAR(40) NOT NULL DEFAULT 'manual',
    config_json TEXT NOT NULL DEFAULT '{}',
    last_synced_at TIMESTAMP,
    last_secret_rotated_at TIMESTAMP,
    last_connection_tested_at TIMESTAMP,
    last_connection_status VARCHAR(20),
    last_connection_error VARCHAR(255),
    connection_failure_count INTEGER NOT NULL DEFAULT 0,
    health_status VARCHAR(20) NOT NULL DEFAULT 'unknown',
    last_health_alerted_at TIMESTAMP,
    last_health_alert_status VARCHAR(20),
    last_error VARCHAR(255),
    failure_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_data_source_tenant_name UNIQUE (tenant_id, name)
);
CREATE INDEX ix_data_sources_tenant_id ON data_sources (tenant_id);

CREATE TABLE data_source_alert_events (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    data_source_id INTEGER NOT NULL REFERENCES data_sources(id) ON DELETE CASCADE,
    trigger_type VARCHAR(20) NOT NULL DEFAULT 'automatic',
    health_status VARCHAR(20) NOT NULL,
    error_message VARCHAR(255),
    delivery_attempted BOOLEAN NOT NULL DEFAULT FALSE,
    delivery_failed BOOLEAN NOT NULL DEFAULT FALSE,
    sent_email INTEGER NOT NULL DEFAULT 0,
    sent_webhook INTEGER NOT NULL DEFAULT 0,
    email_result_json TEXT NOT NULL DEFAULT '{}',
    webhook_result_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_data_source_alert_events_tenant_id ON data_source_alert_events (tenant_id);
CREATE INDEX ix_data_source_alert_events_data_source_id ON data_source_alert_events (data_source_id);

CREATE TABLE sync_jobs (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    data_source_id INTEGER NOT NULL REFERENCES data_sources(id) ON DELETE CASCADE,
    triggered_by_user_id INTEGER NOT NULL REFERENCES tenant_users(id) ON DELETE CASCADE,
    run_mode VARCHAR(20) NOT NULL DEFAULT 'dry_run',
    status VARCHAR(30) NOT NULL DEFAULT 'queued',
    attempt_count INTEGER NOT NULL DEFAULT 1,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    source_filename VARCHAR(255),
    total_rows INTEGER NOT NULL DEFAULT 0,
    success_rows INTEGER NOT NULL DEFAULT 0,
    failed_rows INTEGER NOT NULL DEFAULT 0,
    summary_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_sync_jobs_tenant_id ON sync_jobs (tenant_id);
CREATE INDEX ix_sync_jobs_data_source_id ON sync_jobs (data_source_id);
CREATE INDEX ix_sync_jobs_triggered_by_user_id ON sync_jobs (triggered_by_user_id);

CREATE TABLE sync_job_errors (
    id SERIAL PRIMARY KEY,
    sync_job_id INTEGER NOT NULL REFERENCES sync_jobs(id) ON DELETE CASCADE,
    row_number INTEGER NOT NULL,
    error_message VARCHAR(255) NOT NULL,
    row_payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_sync_job_errors_sync_job_id ON sync_job_errors (sync_job_id);

CREATE TABLE connector_secrets (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    data_source_id INTEGER NOT NULL REFERENCES data_sources(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    cipher_text TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_connector_secret_source_name UNIQUE (data_source_id, name)
);
CREATE INDEX ix_connector_secrets_tenant_id ON connector_secrets (tenant_id);
CREATE INDEX ix_connector_secrets_data_source_id ON connector_secrets (data_source_id);

INSERT INTO plan_definitions (id, plan_id, config_json, created_at, updated_at) VALUES
(1, 'starter', '{"id":"starter","name":"Starter","price":"99 EUR","limits":{"active_members":50},"features":{"source_csv_upload":true,"source_sftp":false,"source_api":false,"alert_analytics":true,"advanced_alert_workflows":false}}', NOW(), NOW()),
(2, 'growth', '{"id":"growth","name":"Growth","price":"299 EUR","limits":{"active_members":250},"features":{"source_csv_upload":true,"source_sftp":true,"source_api":true,"alert_analytics":true,"advanced_alert_workflows":true}}', NOW(), NOW()),
(3, 'enterprise', '{"id":"enterprise","name":"Enterprise","price":"Custom","limits":{"active_members":1000},"features":{"source_csv_upload":true,"source_sftp":true,"source_api":true,"alert_analytics":true,"advanced_alert_workflows":true}}', NOW(), NOW());

INSERT INTO tenants (id, slug, name, contact_email, plan, industry, locale, is_active, created_at, updated_at) VALUES
(1, 'demo-enterprise', 'Demo Enterprise Coaching OS', 'owner@demo-enterprise.local', 'growth', 'telecom', 'de', TRUE, NOW(), NOW());

INSERT INTO tenant_users (id, tenant_id, email, full_name, role, password_hash, is_active, created_at, updated_at) VALUES
(1, 1, 'owner@demo-enterprise.local', 'Demo Owner', 'owner', 'pbkdf2:sha256:600000$coachingos$35b6c495e867ea4aa81e5f5d17eb0291df0df9980b2264c5035701075f46da39', TRUE, NOW(), NOW()),
(2, 1, 'admin@demo-enterprise.local', 'Demo Admin', 'admin', 'pbkdf2:sha256:600000$coachingos$35b6c495e867ea4aa81e5f5d17eb0291df0df9980b2264c5035701075f46da39', TRUE, NOW(), NOW()),
(3, 1, 'manager@demo-enterprise.local', 'Demo Manager', 'manager', 'pbkdf2:sha256:600000$coachingos$35b6c495e867ea4aa81e5f5d17eb0291df0df9980b2264c5035701075f46da39', TRUE, NOW(), NOW()),
(4, 1, 'coach@demo-enterprise.local', 'Demo Coach', 'coach', 'pbkdf2:sha256:600000$coachingos$35b6c495e867ea4aa81e5f5d17eb0291df0df9980b2264c5035701075f46da39', TRUE, NOW(), NOW()),
(5, 1, 'viewer@demo-enterprise.local', 'Demo Viewer', 'viewer', 'pbkdf2:sha256:600000$coachingos$35b6c495e867ea4aa81e5f5d17eb0291df0df9980b2264c5035701075f46da39', TRUE, NOW(), NOW()),
(6, 1, 'qalead@demo-enterprise.local', 'QA Lead', 'qa_lead', 'pbkdf2:sha256:600000$coachingos$35b6c495e867ea4aa81e5f5d17eb0291df0df9980b2264c5035701075f46da39', TRUE, NOW(), NOW());

INSERT INTO tenant_roles (id, tenant_id, role_key, display_name, permissions_json, is_system, created_at, updated_at) VALUES
(1, 1, 'qa_lead', 'QA Lead', '["workspace.view","workspace.manage_sessions","workspace.manage_agents"]', FALSE, NOW(), NOW());

INSERT INTO teams (id, tenant_id, name, manager_name, created_at, updated_at) VALUES
(1, 1, 'Retention', 'Demo Manager', NOW(), NOW()),
(2, 1, 'Sales', 'Demo Admin', NOW(), NOW()),
(3, 1, 'Support', 'QA Lead', NOW(), NOW());

INSERT INTO user_team_scopes (id, tenant_id, user_id, team_id, created_at, updated_at) VALUES
(1, 1, 3, 1, NOW(), NOW()),
(2, 1, 3, 3, NOW(), NOW()),
(3, 1, 6, 3, NOW(), NOW());

INSERT INTO agent_profiles (id, tenant_id, team_id, employee_code, full_name, status, created_at, updated_at) VALUES
(1, 1, 1, 'RET-001', 'Anna Becker', 'active', NOW(), NOW()),
(2, 1, 1, 'RET-002', 'Jonas Wolf', 'active', NOW(), NOW()),
(3, 1, 2, 'SAL-001', 'Mia Fischer', 'active', NOW(), NOW()),
(4, 1, 2, 'SAL-002', 'Luca Braun', 'inactive', NOW(), NOW()),
(5, 1, 3, 'SUP-001', 'Sofia Keller', 'active', NOW(), NOW()),
(6, 1, 3, 'SUP-002', 'Noah Wagner', 'active', NOW(), NOW());

INSERT INTO agent_coaching_cadences (id, tenant_id, agent_id, cadence_days, created_at, updated_at) VALUES
(1, 1, 1, 14, NOW(), NOW()),
(2, 1, 2, 21, NOW(), NOW()),
(3, 1, 3, 30, NOW(), NOW()),
(4, 1, 4, 30, NOW(), NOW()),
(5, 1, 5, 14, NOW(), NOW()),
(6, 1, 6, 14, NOW(), NOW());

INSERT INTO coaching_cases (id, tenant_id, team_id, agent_id, requested_by_user_id, assigned_to_user_id, title, summary, source_type, priority, status, due_at, completed_at, created_at, updated_at) VALUES
(1, 1, 1, 1, 3, 4, 'Retention quality recovery', 'Quality trend declined across the last three reviews. Coach should focus on empathy and save intent framing.', 'quality_risk', 'high', 'planned', NOW() + INTERVAL '3 days', NULL, NOW() - INTERVAL '2 days', NOW()),
(2, 1, 1, 2, 3, 4, 'Monthly retention cadence', 'Recurring coaching cycle for retention member.', 'cadence', 'normal', 'open', NOW() + INTERVAL '7 days', NULL, NOW() - INTERVAL '1 day', NOW()),
(3, 1, 2, 3, 2, 4, 'New sales objection handling follow-up', 'Follow-up from last coaching session. Validate discovery depth and commercial closing.', 'follow_up', 'high', 'follow_up', NOW() + INTERVAL '5 days', NULL, NOW() - INTERVAL '5 days', NOW()),
(4, 1, 3, 5, 6, 6, 'Support QA escalation', 'Escalated from QA audit after repeated process misses.', 'manager_assigned', 'critical', 'in_progress', NOW() + INTERVAL '1 day', NULL, NOW() - INTERVAL '3 days', NOW()),
(5, 1, 3, 6, 3, 4, 'Support case review complete', 'Completed coaching cycle with documented follow-through.', 'ad_hoc', 'normal', 'completed', NOW() - INTERVAL '5 days', NOW() - INTERVAL '2 days', NOW() - INTERVAL '8 days', NOW() - INTERVAL '2 days');

INSERT INTO coaching_sessions (id, tenant_id, coaching_case_id, agent_id, coach_user_id, coaching_type, channel, score, occurred_at, notes, created_at, updated_at) VALUES
(1, 1, 5, 6, 4, 'quality', 'call', 88.5, NOW() - INTERVAL '2 days', 'Strong progress against the prior support quality gap. Next step is consistency across escalation notes.', NOW() - INTERVAL '2 days', NOW() - INTERVAL '2 days'),
(2, 1, 3, 3, 4, 'quality', 'video', 72.0, NOW() - INTERVAL '9 days', 'Discovery was better, but objection handling still lacked commercial confidence.', NOW() - INTERVAL '9 days', NOW() - INTERVAL '9 days'),
(3, 1, NULL, 1, 4, 'quality', 'call', 61.5, NOW() - INTERVAL '15 days', 'Backfilled ad hoc session prior to full workflow rollout.', NOW() - INTERVAL '15 days', NOW() - INTERVAL '15 days'),
(4, 1, NULL, 5, 6, 'compliance', 'chat', 55.0, NOW() - INTERVAL '20 days', 'Critical miss on process adherence and documentation quality.', NOW() - INTERVAL '20 days', NOW() - INTERVAL '20 days');

INSERT INTO coaching_action_items (id, tenant_id, coaching_session_id, owner_user_id, title, status, due_at, completed_at, created_at, updated_at) VALUES
(1, 1, 1, 6, 'Use the updated escalation template on every tier-two case', 'open', NOW() + INTERVAL '3 days', NULL, NOW() - INTERVAL '2 days', NOW()),
(2, 1, 1, 4, 'Review three random follow-up cases for consistency', 'completed', NOW() - INTERVAL '1 day', NOW() - INTERVAL '12 hours', NOW() - INTERVAL '2 days', NOW() - INTERVAL '12 hours'),
(3, 1, 2, 3, 'Shadow the next objection-handling call and document missed opportunities', 'open', NOW() + INTERVAL '2 days', NULL, NOW() - INTERVAL '9 days', NOW()),
(4, 1, 4, 5, 'Complete process refresher and confirm checklist usage', 'open', NOW() - INTERVAL '4 days', NULL, NOW() - INTERVAL '20 days', NOW());

INSERT INTO scorecard_templates (id, tenant_id, name, is_default, config_json, created_at, updated_at) VALUES
(1, 1, 'Enterprise Quality Scorecard', TRUE, '{"sections":[{"key":"communication","label":"Communication","weight":35},{"key":"process","label":"Process","weight":35},{"key":"outcome","label":"Outcome","weight":30}]}', NOW(), NOW());

INSERT INTO subscriptions (id, tenant_id, provider, provider_customer_id, provider_subscription_id, status, current_period_end, created_at, updated_at) VALUES
(1, 1, 'stripe', 'cus_demo_enterprise', 'sub_demo_enterprise', 'trialing', NOW() + INTERVAL '21 days', NOW(), NOW());

INSERT INTO csv_import_profiles (id, tenant_id, name, mapping_json, is_default, created_at, updated_at) VALUES
(1, 1, 'Default Agent Import', '{"employee_code":"employee_code","full_name":"full_name","team_name":"team"}', TRUE, NOW(), NOW());

INSERT INTO csv_import_jobs (id, tenant_id, created_by_user_id, profile_id, source_filename, status, run_mode, total_rows, success_rows, failed_rows, mapping_snapshot_json, transformation_json, summary_json, created_at, updated_at) VALUES
(1, 1, 2, 1, 'agents_april.csv', 'completed', 'apply', 42, 40, 2, '{"employee_code":"employee_code","full_name":"full_name","team_name":"team"}', '{"trim_strings":true}', '{"created":2,"updated":38,"failed":2}', NOW() - INTERVAL '6 days', NOW() - INTERVAL '6 days');

INSERT INTO csv_import_row_errors (id, import_job_id, row_number, row_payload_json, error_message, created_at, updated_at) VALUES
(1, 1, 17, '{"employee_code":"SAL-991","full_name":"","team":"Sales"}', 'full_name is required', NOW() - INTERVAL '6 days', NOW() - INTERVAL '6 days'),
(2, 1, 24, '{"employee_code":"","full_name":"Imported User","team":"Support"}', 'employee_code is required', NOW() - INTERVAL '6 days', NOW() - INTERVAL '6 days');

INSERT INTO data_sources (id, tenant_id, name, source_type, is_active, schedule, config_json, last_synced_at, last_secret_rotated_at, last_connection_tested_at, last_connection_status, last_connection_error, connection_failure_count, health_status, last_health_alerted_at, last_health_alert_status, last_error, failure_count, created_at, updated_at) VALUES
(1, 1, 'Daily QA CSV Upload', 'csv_upload', TRUE, 'daily', '{"path":"uploads/qa_daily.csv"}', NOW() - INTERVAL '3 hours', NOW() - INTERVAL '20 days', NOW() - INTERVAL '1 day', 'ok', NULL, 0, 'healthy', NOW() - INTERVAL '10 days', 'healthy', NULL, 0, NOW(), NOW()),
(2, 1, 'Support SFTP Feed', 'sftp', TRUE, 'hourly', '{"host":"sftp.demo.local","port":22,"username":"support_feed"}', NOW() - INTERVAL '1 day', NOW() - INTERVAL '30 days', NOW() - INTERVAL '2 hours', 'failed', 'Authentication failed', 4, 'degraded', NOW() - INTERVAL '2 hours', 'degraded', 'Authentication failed', 4, NOW(), NOW()),
(3, 1, 'CRM Coaching API', 'api', TRUE, 'manual', '{"base_url":"https://api.demo.local/coaching","timeout_seconds":15}', NOW() - INTERVAL '5 days', NOW() - INTERVAL '14 days', NOW() - INTERVAL '5 days', 'failed', '503 upstream timeout', 7, 'unhealthy', NOW() - INTERVAL '1 day', 'unhealthy', '503 upstream timeout', 7, NOW(), NOW());

INSERT INTO connector_secrets (id, tenant_id, data_source_id, name, cipher_text, created_at, updated_at) VALUES
(1, 1, 2, 'password', 'demo-encrypted-sftp-password', NOW(), NOW()),
(2, 1, 3, 'api_token', 'demo-encrypted-api-token', NOW(), NOW());

INSERT INTO data_source_alert_events (id, tenant_id, data_source_id, trigger_type, health_status, error_message, delivery_attempted, delivery_failed, sent_email, sent_webhook, email_result_json, webhook_result_json, created_at, updated_at) VALUES
(1, 1, 2, 'automatic', 'degraded', 'Authentication failed', TRUE, FALSE, 1, 0, '{"status":"sent"}', '{}', NOW() - INTERVAL '2 hours', NOW() - INTERVAL '2 hours'),
(2, 1, 3, 'automatic', 'unhealthy', '503 upstream timeout', TRUE, TRUE, 1, 1, '{"status":"sent"}', '{"status":"failed","error":"timeout"}', NOW() - INTERVAL '1 day', NOW() - INTERVAL '1 day');

INSERT INTO sync_jobs (id, tenant_id, data_source_id, triggered_by_user_id, run_mode, status, attempt_count, started_at, finished_at, source_filename, total_rows, success_rows, failed_rows, summary_json, created_at, updated_at) VALUES
(1, 1, 1, 2, 'apply', 'completed', 1, NOW() - INTERVAL '3 hours 10 minutes', NOW() - INTERVAL '3 hours', 'qa_daily_2026_04_16.csv', 200, 198, 2, '{"created_sessions":14,"updated_agents":12}', NOW() - INTERVAL '3 hours 10 minutes', NOW() - INTERVAL '3 hours'),
(2, 1, 3, 2, 'dry_run', 'failed', 2, NOW() - INTERVAL '5 days 15 minutes', NOW() - INTERVAL '5 days', NULL, 0, 0, 0, '{"error":"503 upstream timeout"}', NOW() - INTERVAL '5 days 15 minutes', NOW() - INTERVAL '5 days');

INSERT INTO sync_job_errors (id, sync_job_id, row_number, error_message, row_payload_json, created_at, updated_at) VALUES
(1, 1, 43, 'Missing agent employee_code', '{"full_name":"Unknown User","team":"Retention"}', NOW() - INTERVAL '3 hours', NOW() - INTERVAL '3 hours'),
(2, 1, 107, 'Invalid score value', '{"employee_code":"SUP-002","score":"N/A"}', NOW() - INTERVAL '3 hours', NOW() - INTERVAL '3 hours');

INSERT INTO user_invitations (id, tenant_id, invited_by_user_id, email, full_name, role, token, expires_at, accepted_at, revoked_at, created_at, updated_at) VALUES
(1, 1, 1, 'newcoach@demo-enterprise.local', 'New Coach Invite', 'coach', 'demo-invite-token-001', NOW() + INTERVAL '5 days', NULL, NULL, NOW(), NOW());

INSERT INTO audit_events (id, tenant_id, actor_user_id, event_type, details_json, created_at, updated_at) VALUES
(1, 1, 1, 'auth.owner_registered', '{"email":"owner@demo-enterprise.local"}', NOW() - INTERVAL '10 days', NOW() - INTERVAL '10 days'),
(2, 1, 2, 'workspace.coaching_case_created', '{"case_id":1,"agent_id":1,"source_type":"quality_risk","priority":"high"}', NOW() - INTERVAL '2 days', NOW() - INTERVAL '2 days'),
(3, 1, 4, 'workspace.session_created', '{"session_id":1,"agent_id":6,"case_id":5,"coaching_type":"quality","channel":"call","score":88.5,"action_item_count":2}', NOW() - INTERVAL '2 days', NOW() - INTERVAL '2 days'),
(4, 1, 6, 'workspace.agent_cadence_updated', '{"agent_id":5,"employee_code":"SUP-001","cadence_days":14}', NOW() - INTERVAL '7 days', NOW() - INTERVAL '7 days');

SELECT setval('plan_definitions_id_seq', COALESCE((SELECT MAX(id) FROM plan_definitions), 1), TRUE);
SELECT setval('tenants_id_seq', COALESCE((SELECT MAX(id) FROM tenants), 1), TRUE);
SELECT setval('tenant_users_id_seq', COALESCE((SELECT MAX(id) FROM tenant_users), 1), TRUE);
SELECT setval('tenant_roles_id_seq', COALESCE((SELECT MAX(id) FROM tenant_roles), 1), TRUE);
SELECT setval('teams_id_seq', COALESCE((SELECT MAX(id) FROM teams), 1), TRUE);
SELECT setval('user_team_scopes_id_seq', COALESCE((SELECT MAX(id) FROM user_team_scopes), 1), TRUE);
SELECT setval('agent_profiles_id_seq', COALESCE((SELECT MAX(id) FROM agent_profiles), 1), TRUE);
SELECT setval('agent_coaching_cadences_id_seq', COALESCE((SELECT MAX(id) FROM agent_coaching_cadences), 1), TRUE);
SELECT setval('coaching_cases_id_seq', COALESCE((SELECT MAX(id) FROM coaching_cases), 1), TRUE);
SELECT setval('coaching_sessions_id_seq', COALESCE((SELECT MAX(id) FROM coaching_sessions), 1), TRUE);
SELECT setval('coaching_action_items_id_seq', COALESCE((SELECT MAX(id) FROM coaching_action_items), 1), TRUE);
SELECT setval('scorecard_templates_id_seq', COALESCE((SELECT MAX(id) FROM scorecard_templates), 1), TRUE);
SELECT setval('subscriptions_id_seq', COALESCE((SELECT MAX(id) FROM subscriptions), 1), TRUE);
SELECT setval('csv_import_profiles_id_seq', COALESCE((SELECT MAX(id) FROM csv_import_profiles), 1), TRUE);
SELECT setval('csv_import_jobs_id_seq', COALESCE((SELECT MAX(id) FROM csv_import_jobs), 1), TRUE);
SELECT setval('csv_import_row_errors_id_seq', COALESCE((SELECT MAX(id) FROM csv_import_row_errors), 1), TRUE);
SELECT setval('data_sources_id_seq', COALESCE((SELECT MAX(id) FROM data_sources), 1), TRUE);
SELECT setval('connector_secrets_id_seq', COALESCE((SELECT MAX(id) FROM connector_secrets), 1), TRUE);
SELECT setval('data_source_alert_events_id_seq', COALESCE((SELECT MAX(id) FROM data_source_alert_events), 1), TRUE);
SELECT setval('sync_jobs_id_seq', COALESCE((SELECT MAX(id) FROM sync_jobs), 1), TRUE);
SELECT setval('sync_job_errors_id_seq', COALESCE((SELECT MAX(id) FROM sync_job_errors), 1), TRUE);
SELECT setval('user_invitations_id_seq', COALESCE((SELECT MAX(id) FROM user_invitations), 1), TRUE);
SELECT setval('audit_events_id_seq', COALESCE((SELECT MAX(id) FROM audit_events), 1), TRUE);

COMMIT;
