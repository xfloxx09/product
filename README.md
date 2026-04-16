# CoachingOS Product Repository

This repository now runs a **new SaaS platform foundation** focused on enterprise coaching operations:

- Multi-tenant domain model (`Tenant`, `TenantUser`, `Team`, `AgentProfile`, `CoachingSession`, `ScorecardTemplate`, `Subscription`)
- Secure auth flow (workspace-aware login, owner registration, tenant-scoped sessions)
- Invitation flow with role assignment and token-based acceptance
- Tenant-customizable role catalog with permission-level RBAC management
- Invitation lifecycle controls (send/resend/revoke) with optional SendGrid delivery
- User governance controls (change role, activate/deactivate accounts) with owner safety guardrails
- Delegated team-level access scopes for managers/admins (restrict agents and sessions by assigned teams)
- Coaching action plans with per-session follow-up items and completion tracking
- Overdue action dashboard and manual reminder workflow for coaching follow-through
- Coaching cadence policies and SLA dashboard for overdue / never-coached visibility
- Quality trend intelligence with at-risk member detection and team trend ranking
- Guided onboarding (creates tenant + owner + industry defaults)
- Multi-plan catalog with feature unlocks and active-member capacity entitlements
- Industry presets (telecom, energy, generic) for scorecards and CSV mapping
- Workspace operations module for teams, agents, sessions, and KPI dashboard
- Active member lifecycle controls (activate/deactivate) with plan-capacity enforcement
- RBAC permission checks (`workspace.*`, `settings.manage`, `billing.manage`)
- Audit logging for onboarding, auth, settings, billing, and workspace mutations
- CSV import job pipeline with job history, row-level errors, and dry-run transforms
- Live-ready Stripe checkout/portal integration with mock fallback and webhook sync
- Multi-source ingestion baseline (`DataSource` + `SyncJob`) for CSV/SFTP/API connectors
- Sync reliability layer (due-run detection, attempt tracking, source health status)
- Encrypted connector secret storage for API/SFTP credentials
- Secret rotation workflow per data source (update/clear credentials with audit trail)
- Connector health checks with “Test Connection” action and status tracking
- Automated connector health governance (degraded/unhealthy thresholds + CLI checks)
- Connector alerting with cooldown/deduped notifications for degraded/unhealthy states
- Multi-channel connector alerts (email + webhook) with per-source policies
- Slack/Teams-ready webhook payload formats with optional HMAC signature headers
- Per-source "Send Test Alert" action for validating alert channels end-to-end
- Webhook Verification Helper page with signed payload/header samples and receiver snippets
- Per-source alert delivery history (automatic + test alerts) with channel failure details
- Tenant-level alert analytics dashboard (24h/7d/30d) with failure trends and top failing sources
- Alert Policy Simulator to preview send/suppress decisions before dispatch
- Plan Catalog Management panel (UI) for editing plan names, prices, capacity, and feature unlocks
- Role Management panel (UI) for tenant-customizable roles and permission mapping
- Tenant context middleware and `/health` operational endpoint
- API starter (`/api/v1`) for integration-readiness

## Quick start

1. Set environment variables:
   - `SECRET_KEY` (required)
   - `DATABASE_URL` (optional, defaults to local SQLite)
   - `CONNECTOR_SECRETS_KEY` (recommended in production; Fernet key)
   - `DATASOURCE_ALERT_EMAIL_ENABLED` / `DATASOURCE_ALERT_WEBHOOK_ENABLED`
   - `DATASOURCE_ALERT_COOLDOWN_MINUTES`
   - `DATASOURCE_ALERT_WEBHOOK_TIMEOUT_SECONDS`
2. Install deps:
   - `pip install -r requirements.txt`
3. Initialize DB:
   - `flask --app run.py init-db`
4. Run:
   - `python run.py`

## New structure

- `platform_app/config.py`: runtime config and security settings
- `platform_app/extensions.py`: shared Flask extension instances
- `platform_app/models.py`: tenant, user, operations, billing, and audit models
- `platform_app/modules/public`: marketing pages and pricing
- `platform_app/modules/onboarding`: workspace setup flow
- `platform_app/modules/billing`: checkout integration entrypoint
- `platform_app/modules/auth`: workspace authentication
- `platform_app/templates/auth/invite_user.html`: owner/admin invitation UI
- `platform_app/modules/workspace`: operational dashboard + CRUD starters
- `platform_app/modules/imports`: tenant CSV mapping view
- `platform_app/templates/imports/new_job.html`: CSV upload and processing
- `platform_app/templates/imports/job_detail.html`: import diagnostics
- `platform_app/modules/datasources`: enterprise ingestion sources + sync jobs
- `platform_app/modules/settings`: workspace and scorecard settings
- `platform_app/modules/api`: integration-ready JSON endpoints
- `platform_app/services/provisioning.py`: industry-based default provisioning
- `platform_app/services/tenant_context.py`: tenant and role guard helpers
- `platform_app/services/rbac.py`: role-permission matrix
- `platform_app/services/audit.py`: audit event writer
- `platform_app/services/mailer.py`: invite delivery abstraction
- `platform_app/services/imports.py`: CSV import processing engine
- `platform_app/services/stripe_client.py`: Stripe checkout and portal client
- `platform_app/services/plan_catalog.py`: plan definitions, usage snapshots, and limit checks
- `platform_app/services/sync_sources.py`: data source sync orchestrator
- `platform_app/services/connector_alerts.py`: health alert orchestration + dedupe
- `platform_app/services/mailer.py`: email + generic/slack/teams webhook alert delivery
- CLI command: `flask --app run.py run-scheduled-syncs` for scheduled sync batches
- CLI command: `flask --app run.py run-connector-health-checks` for proactive connector monitoring
- `platform_app/services/connector_secrets.py`: encrypted connector secret manager
- `platform_app/templates/datasources/settings.html`: connector config + secret rotation UI
- Optional runtime dependency for SFTP sources: `paramiko`

## Product roadmap (next implementation waves)

1. Replace mock billing checkout with live Stripe Checkout Sessions and customer portal links
2. Add invite email templates + localization (DE/EN) and deliverability monitoring
3. Build full CSV mapping UI editor with per-column transformations and dry-run mode
4. Integrate vault/KMS-backed secret providers and webhook/chat alert channels
5. Add enterprise controls (SSO/SAML, audit dashboards, retention policies)
6. Add benchmarking and AI-assisted coaching insights

Legacy monolith code remains in `app/` for reference during migration.
