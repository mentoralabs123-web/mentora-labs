# Task 6 — Final integration and QA report

## Scope reviewed

Reviewed the Task 5B application archive: Flask routes, admin authentication and CSRF guard, project and business-enquiry services/schema, public/admin templates, JavaScript, CSS, requirements, Render Blueprint, and deployment documentation. No wholesale redesign or schema reset was performed.

## Fixes made

- Corrected the business-enquiry admin editor to use the exact status vocabulary already defined by `business_enquiry.STATUSES` (`New`, `Contacted`, `In Progress`, `Completed`, `Closed`). Previously the editor offered `In progress` and omitted `Contacted`, so legitimate existing statuses could not be selected consistently.
- Updated the enquiry detail template to render the status options supplied by the service layer.
- Added an integration regression test covering all existing business-enquiry statuses.
- Replaced stale deployment instructions that referred to the retired Basic-Auth login and `.secret_key` fallback.
- Documented the actual production environment variables and Render persistence requirements.

## Database

No database schema changes or migrations were made for this QA task. The existing SQLite/PostgreSQL abstraction and additive `CREATE TABLE IF NOT EXISTS` initialization remain unchanged. The 23 project-service tests passed, including SQLite initialization, idempotent migration, deleted-project persistence, existing order/edit preservation, published visibility, and SQL-injection handling. PostgreSQL was not connected or integration-tested.

## Security source review

Retained Task 5A's Werkzeug password hashing, signed Flask sessions, session replacement after successful login, HTTP-only/SameSite cookies, HTTPS secure-cookie behavior, server-side admin guard, admin CSRF validation, login attempt throttle, and security headers. Reviewed parameterized query use, Jinja autoescaping, file extension/signature checks, generated upload names, upload size limits, and path containment. This was a source review, not a penetration test.

## Executed checks

| Check | Result |
|---|---|
| `python -m compileall -q .` | Passed |
| `python -m unittest tests.test_project_service -v` | Passed — 23/23 |
| Public route/template inventory | Passed — all seven expected public page templates/routes found |
| Template static-asset references | Passed — no missing referenced local assets found |
| Responsive breakpoint source inspection | Passed — responsive breakpoint rules present |
| ZIP archive integrity | Passed |
| Full `python -m unittest discover -s tests -v` | Blocked — 23 tests passed; five Flask-dependent test modules could not import because Flask/Werkzeug are absent |
| Flask route/auth/form/admin integration tests | Not executed |
| Browser rendering at 1440/1024/768/425/375 px | Not executed |
| Live PostgreSQL/Render deployment | Not executed |

Attempted to install `requirements.txt`; package installation could not reach the package index because network DNS was unavailable. No runtime test is represented as passed.

## Render configuration required

Set `SECRET_KEY` (at least 32 random characters), `ADMIN_USER`, `ADMIN_PASSWORD`, and `DATABASE_URL` in Render Environment. The included `render.yaml` generates `SECRET_KEY` and prompts for the other three. Use PostgreSQL for persistent database records. The current uploads directory is local filesystem storage; mount a Render persistent disk at the application's `static/uploads` directory (on a plan supporting disks) before accepting durable project image uploads. Back up the database and uploads.

Optional settings: `TRUSTED_PROXY_COUNT`, `SESSION_COOKIE_SECURE`, and the SMTP notification variables `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `NOTIFY_EMAIL`.

## Manual release checks still required

1. Install dependencies with `pip install -r requirements.txt`.
2. Run `python -m unittest discover -s tests -v` and resolve any runtime failures.
3. Run the app behind HTTPS and test login, logout, CSRF rejection, and unauthenticated write rejection.
4. Test all public forms and the admin project/enquiry workflows in a browser.
5. Check the public and admin layouts at 1440, 1024, 768, 425, and 375 CSS pixels.
6. Verify PostgreSQL startup, CRUD persistence after restart, and persistent image storage on the actual Render service.
7. Confirm backups and restore procedures before production use.
