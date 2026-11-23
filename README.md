# Mentora Labs

Full-stack site: Flask backend + templated frontend, with an order form backed by
a real API and a database. It uses PostgreSQL when `DATABASE_URL` is set and
SQLite for local development otherwise.

## What's included

- `app.py` — Flask app: serves the public pages, exposes `POST /api/orders`, and an
  admin view at `/admin/orders` (password protected) to see submissions.
- `templates/base.html` — shared layout: left sidebar navigation (collapsible on
  desktop, rail on tablet, drawer on mobile), mobile top bar and footer.
- `templates/index.html`, `about.html`, `services.html` (the IT Services page at `/services`: hero, service overview, six services, process, audiences, CTA), `projects.html`,
  `learning.html`, `contact.html`, `reviews.html`, `faq.html`, `404.html` — the public pages.
- `business_enquiry.py` — business (IT services) enquiries: validation, cleaning, table setup and storage. `templates/business_enquiry.html` (the form at `/services/enquiry`) and `business_enquiry_submitted.html` (the confirmation page); `static/js/enquiry.js` adds inline checks and the "Sending…" state (the form also works without JavaScript).
- `project_service.py` — project data access (reads, create/update/delete, validation); `project_schema.py` — table creation and one-time migration; `project_seed_data.py` — the original nine projects.
- `faq_content.py` — the eight public FAQ categories and 110 reviewed Q&A entries.
- `static/js/faq.js` — FAQ search, category filtering and accordion controls.
- `tests/` — unit and integration tests (`python -m unittest discover tests`).
- `templates/partials/` — reusable pieces: icon sprite, project-card macro,
  footer, enquiry dialog, process steps, call-to-action band.
- `templates/admin_*.html` — the authenticated admin portal, dashboard, project editor, and order/enquiry views.
- `static/css/style.css` — the design system. All colors, spacing, radii,
  shadows, type scale and layout sizes are CSS variables in section 1.
- `static/js/main.js` — sidebar/drawer behaviour, enquiry dialog (a button can pre-fill the message with `data-order-message`). `static/js/projects.js` — Projects page filter, search and details dialog.
- `static/img/` — brand images (`logo.png`, `banner.jpg`) plus small
  `logo-96.png` and `favicon.png` derived from the logo.
- `requirements.txt` — Python dependencies.
- `render.yaml` — optional Render Blueprint.

## Running locally

```bash
pip install -r requirements.txt
python app.py
```

Visit `http://localhost:5000`.

## Deploying on Render

1. Push this folder to a GitHub repository and create a Render Web Service (or use the included Blueprint).
2. Build command: `pip install -r requirements.txt`.
3. Start command: `gunicorn app:app`.
4. Configure the environment variables listed under **Production environment variables** below.
5. Use PostgreSQL (`DATABASE_URL`) for production persistence. Render's ephemeral filesystem is not a durable database or upload store.
6. Deploy and verify `/`, `/projects`, `/services/enquiry`, `/admin`, and a test form submission.

The Blueprint in `render.yaml` generates `SECRET_KEY` and prompts for `ADMIN_USER`, `ADMIN_PASSWORD`, and `DATABASE_URL`. If configuring a service manually, set them in Render's Environment page. Do not put secrets in source control or share them in chat.

For persistent project thumbnails, configure a persistent disk on a Render plan that supports it and mount it at the application's `static/uploads` directory, or move uploads to durable object storage and configure the application accordingly. The current upload implementation writes to the local `static/uploads/projects` directory; files on an ephemeral instance can disappear during redeploys or instance replacement. Back up uploaded files separately.

For production, use PostgreSQL rather than the default SQLite file on Render. SQLite remains supported for local development and single-instance environments with durable storage. Keep regular database backups.

## Business enquiries (IT Services)

The IT Services page links to a business enquiry form at `/services/enquiry` (`POST` to the same URL).
Enquiries are stored in their own `business_enquiries` table, never in `orders`, which stays the student
project/course enquiry table (`POST /api/orders`).

- **Table** (created automatically on start-up with `CREATE TABLE IF NOT EXISTS`; nothing existing is touched):
  `id`, `name`, `email`, `phone`, `business_name`, `service`, `project_description`, `budget`,
  `status` (default `New`; one of `New`, `Contacted`, `In Progress`, `Completed`, `Closed`), `admin_notes`
  (reserved for the admin portal), `source` (which CTA the visitor came from), `submission_token`,
  `fingerprint`, `client_hash`, `created_at`, `updated_at` (ISO-8601 UTC text, like the other tables).
- `service` and `budget` hold stable codes; use `SERVICE_LABELS` / `BUDGET_LABELS` in `business_enquiry.py` to display them.
- **Protection:** server-side validation and length limits, CSRF token (signed session cookie), hidden honeypot
  field, rate limits (5 stored enquiries per visitor per hour, counted in the database so it holds across
  workers, plus a short-term per-process limit on attempts), and duplicate prevention (a per-form token and a
  24-hour check for an identical enquiry). The visitor's IP is never stored, only a keyed hash of it.
- **CTA preselection:** `/services/enquiry?service=<code>` or `?cta=<button key>`; both are checked against a whitelist on the server.
- Business enquiries can be reviewed at `/admin/enquiries`; the authenticated admin can update the existing status and internal notes.

## Viewing submitted orders

Sign in at `https://<your-render-url>/admin`. Student orders are available under **Orders** after authentication.

## Customizing tracks, contact info, or pricing copy

- Projects shown on the site live in the database (`projects`, `project_categories` and
  `project_category_links` tables). On first start-up the original nine projects are migrated from
  `project_seed_data.py` (once, tracked in `schema_migrations`; existing data is never touched and
  deleted projects are not brought back). After that, manage projects through the authenticated **Admin → Projects** interface. Each project has a `learning_group` (`ml`, `data` or
  `fullstack`) that decides its learning path.
- Project images: store a path relative to `static/` (e.g. `uploads/projects/nids-3fa9c1d2.png`)
  in the `image` / `gallery_images` columns. Missing files fall back to category artwork.
- Learning paths: the `GROUPS` list in `app.py`.
- Contact details/social links: edit the `CONTACT` dict in `app.py`.
- Page copy: the matching file in `templates/`.
- Colors, fonts, spacing: the variables at the top of `static/css/style.css`.


## Admin portal configuration (Task 5A)

Set these environment variables before deploying:

- `SECRET_KEY`: a cryptographically random secret of at least 32 characters (use a secret manager; do not commit it).
- `ADMIN_USER`: the administrator username or email.
- `ADMIN_PASSWORD`: the administrator password (the app hashes it with Werkzeug before comparison; it is never sent to the browser).
- `DATABASE_URL`: optional PostgreSQL connection string; omit to use the existing SQLite database.

`ADMIN_PASS` is accepted temporarily as a compatibility alias for `ADMIN_PASSWORD`; prefer `ADMIN_PASSWORD`.
In production (`RENDER=true` or `FLASK_ENV=production`), the app does not generate a fallback secret. Admin routes return a clear configuration error until the required values are set. Set `SESSION_COOKIE_SECURE=1` when deploying behind HTTPS outside Render. The admin login is at `/admin`; use `/admin/logout` via the portal's POST logout form.

For Render, the included Blueprint declares `ADMIN_USER`, `ADMIN_PASSWORD`, and `DATABASE_URL` as secret prompts and generates `SECRET_KEY`. When configuring manually, set all four values. Use a unique administrator password and a randomly generated `SECRET_KEY` of at least 32 characters. `TRUSTED_PROXY_COUNT` is optional (default `1` on Render, `0` elsewhere); `SESSION_COOKIE_SECURE` is optional and should be `1` when serving HTTPS behind a proxy outside Render. Optional email notifications use `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, and `NOTIFY_EMAIL`.

**Persistence warning:** Render's default filesystem is ephemeral. Use PostgreSQL for database persistence and a persistent disk mounted at `static/uploads` for project images. The current project upload handler stores images on the local filesystem; it does not yet integrate with object storage. Do not assume a free/ephemeral Render instance will retain SQLite data or uploaded images across replacement/redeploy.

## Admin management (Task 5B)

The authenticated admin workspace is available at `/admin` after setting the Task 5A
`SECRET_KEY`, `ADMIN_USER`, and `ADMIN_PASSWORD` environment variables. The existing
session authentication, password hash, session rotation, cookie flags, login throttle,
and admin CSRF token guard remain in place.

### Admin workspace

- `/admin/dashboard` shows live counts from `projects`, `orders`, and
  `business_enquiries`, plus recent incoming records.
- `/admin/projects` supports search, publication filtering, create, edit, delete,
  categories, comma-separated technologies, project URL, featured/publication flags,
  and display order. It uses `project_service.py` and the existing project tables.
- Project thumbnail uploads accept JPG/JPEG, PNG, WEBP, and GIF only, with a 5 MB
  per-file limit and a signature check against the selected extension. Upload names
  are generated server-side under `static/uploads/projects`; SVG and other active
  content formats are not accepted. Unreferenced managed thumbnails are removed
  after replacement or deletion.
- `/admin/orders` and `/admin/orders/<id>` are read-only views of the existing
  student `orders` table. No order records are rewritten or merged with enquiries.
- `/admin/enquiries` and `/admin/enquiries/<id>` show the separate business
  `business_enquiries` table. Existing status and admin-notes fields can be updated
  with server-side validation.

No new database tables or schema migrations were added for Task 5B. Existing project,
student-order, and business-enquiry records are retained. Project CRUD continues to
use the existing additive Task 3B schema and service layer. The dashboard and record
lists use parameterized queries and HTML autoescaping.

Run the full test suite in an environment with the dependencies from
`requirements.txt` installed:

```bash
python -m unittest discover -s tests -v
```

The admin integration tests are in `tests/test_admin_management.py` and the Task 5A
session/CSRF regression tests remain in `tests/test_admin_auth.py`.


## FAQ and contact details

- Public FAQ: `/faq`. Questions and answers are maintained in `faq_content.py`; the page builds FAQ structured data from the same visible content.
- Public contact phone numbers are configured in the `CONTACT` dictionary in `app.py`. The additional number `+91 88258 28406` is listed alongside the two existing numbers; its WhatsApp destination is `918825828406`.
