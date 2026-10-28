# Farmkart Foods — Online Peanut Purchasing (Working Pilot v0.1)

This repository contains a **new, independently written pilot**, based on the visible purchasing workflow in the provided FarmkartBilling.exe and screen recording. It is **not** the original software's source code, an exact executable copy, or a production deployment.

## For Himatnagar and Modasa Windows PCs

**Final planned use:** Open a single HTTPS website in Chrome or Edge on either Windows PC. Staff enter separate usernames/passwords. Both factories use **one PostgreSQL server** in the cloud. A factory's purchasing staff see only their assigned factory; the owner sees both.

**What works in this pilot:**

- Login with named users, signed-in sessions, roles (OWNER, PURCHASE, ACCOUNTS, VIEWER) and CSRF protection
- Shared farmer directory: farmer ID, name, village, mobile, cooperative
- Factory-specific sequential bill numbering, financial-year-aware (HMT / MDS)
- Multiple purchase lines/varieties, gross, kapat, net weights, exact Decimal rates per 20 kg
- Server-calculated purchase amount, weighbridge charges, other deductions and rounding
- Idempotent bill posting to reduce double-submit duplicate bills
- Bill register, browser-printed bilingual purchase receipts (sample format)
- Cash payments, cheque and bank payments with pending/cleared/bounced status
- Owner's combined dashboard, factory filtering, CSV/Excel-compatible export
- Audit trail for purchases and payment actions

**Not yet implemented:** Original software screen-for-screen fidelity, exact preprinted cheque/printer alignment, direct weighing-device integration, QC approval stages, cash ledger reconciliation, stock lots, ledger/Tally integration, automated notifications, document attachments, owner approval workflow, historical data migration, VAT/GST/state-compliant receipt validation, genuine Gujarati localization throughout, fine-grained user management UI, MFA, encryption key rotation, high availability and automated recovery tests. No real Farmkart data are included.

## Windows: run on ONE PC as a local trial

This local mode uses SQLite only to explore the application. **Do not use it concurrently from two factories or for financial production use**.

1. Install Python 3.11 or later (64-bit) on the trial Windows PC; choose **Add python.exe to PATH**.
2. Extract the ZIP to a folder, e.g. `C:\FarmkartPilot`.
3. Double click `01_Windows_Setup_Demo.bat`. It creates a private Python environment, installs dependencies, initializes the empty sample database and prompts you to create a user. Set role to `OWNER` for the first user; choose a password with 12+ characters.
4. Double click `02_Windows_Start_Demo.bat`.
5. In Chrome or Edge, visit `http://127.0.0.1:8000` on that same PC. Sign in with the user you created.

To add other sample users, activate the `.venv` and run `python -m farmkart_app.bootstrap user`, or rerun the setup file (it does not remove records). The local SQLite file is `farmkart_demo.db` in the extracted working directory.

**Important:** The demo uses actual local storage for its test bills. Never enter real farmer personal data or real purchasing transactions into an unapproved trial.

## Developer: run tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
node --check farmkart_app/static/app.js
```

## Cloud deployment model (implementation still required)

1. Provision an HTTPS hostname, e.g. a company-controlled subdomain, with TLS certificate, VPN/WAF/reverse proxy and locked-down administrative access.
2. Set up one dedicated PostgreSQL database (prefer managed PostgreSQL with encrypted disks, daily backups, point-in-time restoration, private networks and monitoring).
3. Deploy the FastAPI service from this repository with the provided Dockerfile. Supply `DATABASE_URL=postgresql+psycopg://...` from the cloud secret manager and `COOKIE_SECURE=1`; set `APP_ENV=production`.
4. Run `python -m farmkart_app.bootstrap init` once in the deployed app environment, then securely create named owner/purchasing/accounts users using `python -m farmkart_app.bootstrap user`.
5. Perform test transactions at both factories using non-production data. Confirm account isolation, weight/rate calculations, payment reconciliation, backups, SSL, printing and network failure handling.
6. Only after security review, statutory receipt approval and acceptance tests should the software handle live farmer purchases.

`compose.yaml` is supplied **for developer integration only**. It does not set up TLS, backups or a fully hardened deployment. Do not expose it directly to the public internet.

### Environment variables

- `DATABASE_URL`: SQLAlchemy URL. Defaults to `sqlite:///./farmkart_demo.db` **only for local development**.
- `COOKIE_SECURE`: must be `1` for HTTPS production.
- `APP_ENV`: set `production` to disable API docs endpoint.

### Production architecture

```
Himatnagar Windows PC ──HTTPS──┐
                               ├── HTTPS reverse proxy/WAF ─ FastAPI ─ PostgreSQL
Modasa Windows PC ──────HTTPS──┘                              │
                                                              └── Encrypted backups
Owner Windows PC ───────HTTPS─────────────────────────────────┘
```

### Data migration and validation

The original Windows EXE is **not** a backup of farmer and bill data. Before migration, back up each site's existing `%LOCALAPPDATA%\FarmkartBilling\instance\` directory, including all related SQLite databases. Develop a separate migration script with field mapping, verification of individual records, duplicate farmer resolution, opening balances and sign-off by the accounting team.

### Engineering limitations of this pilot

- Login throttling, MFA, robust session revocation, web server security headers, reverse-proxy origin checks, alerting, zero-downtime migrations and disaster recovery are not complete. They are mandatory production work.
- SQLite is not safe for simultaneous bill-number generation at two factories. Use PostgreSQL in central deployment and verify concurrent write behavior.
- A successful API POST means the app committed the bill; dropped network responses require staff to check the register before resubmitting. Retried requests reuse an idempotency key, but comprehensive outage handling is outstanding.
- `Base.metadata.create_all()` is for initial setup only; production database schema changes need Alembic migrations.
- Dashboard queries compute totals directly from rows and will require aggregation and pagination as volume grows.
- Printed receipt uses generic branding without the approved Farmkart logo. Replace it only with the user's exact approved asset and verify legal/statutory fields.

## File layout

```
farmkart_app/main.py      API routes and business rules
farmkart_app/models.py    database models
farmkart_app/security.py  logins and session controls
farmkart_app/bootstrap.py database and user initialization
farmkart_app/static/      Windows browser interface
requirements*.txt         dependencies
Dockerfile, compose.yaml  developer deployment examples
tests/test_app.py         functional backend tests
```
