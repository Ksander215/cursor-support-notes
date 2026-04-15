# Infra Guardrails Report

## Alembic Chain

- Revisions detected: 13
- Root revisions: 20260125_0001
- Head revisions: 12814dfc9c90
- Missing down_revision targets: none

- Status: chain structure looks consistent.

### Revision Map

- `12814dfc9c90` <- `20260325_0001_lead_scoring` (alembic\versions\12814dfc9c90_add_whitelabel_config.py)
- `20260125_0001` <- `None` (alembic\versions\20260125_0001_create_audits.py)
- `20260125_0002` <- `20260125_0001` (alembic\versions\20260125_0002_saas_scaffold.py)
- `20260129_0003` <- `20260125_0002` (alembic\versions\20260129_0003_notification_settings.py)
- `20260129_0004` <- `20260129_0003` (alembic\versions\20260129_0004_scan_progress.py)
- `20260129_0005` <- `20260129_0004` (alembic\versions\20260129_0005_default_pricing_plans.py)
- `20260201_0006` <- `20260129_0005` (alembic\versions\20260201_0006_audit_logs.py)
- `20260205_0007` <- `20260201_0006` (alembic\versions\20260205_0007_payments.py)
- `20260206_0008` <- `20260205_0007` (alembic\versions\20260206_0008_referral_system.py)
- `20260209_0009` <- `20260206_0008` (alembic\versions\20260209_0009_webhooks.py)
- `20260226_0010` <- `20260209_0009` (alembic\versions\20260226_0010_digital_orders.py)
- `20260307_0011` <- `20260226_0010` (alembic\versions\20260307_0011_leads.py)
- `20260325_0001_lead_scoring` <- `20260307_0011` (alembic\versions\20260325_0001_lead_scoring.py)

## API Port Usage

- Ports referenced in config/scripts: 22222, 3001, 5432, 5678, 6379, 8000, 8080
- `deploy/nginx/sec-scanner.conf.template`: 3001, 8000
- `scripts/*.sh`: 22222, 5432, 5678, 6379, 8000, 8080

### Port Drift Risk
- Multiple localhost API ports are present; verify intended canonical port.

## Recommended Next Checks

- Run `alembic heads` and ensure single head.
- Run `alembic history --verbose` and verify linear chain.
- Verify nginx `proxy_pass` API target matches deployed API container port.
- Re-run webhook smoke tests after deploy.
