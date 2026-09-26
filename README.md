# Mentora Labs

Full-stack site: Flask backend + templated frontend, with an order form backed by
a real API and a SQLite database — no more relying only on WhatsApp links.

## What's included

- `app.py` — Flask app: serves the site, exposes `POST /api/orders`, and an
  admin view at `/admin/orders` (password protected) to see submissions.
- `templates/index.html` — the site (Jinja2 template).
- `templates/admin.html` — simple table view of submitted orders.
- `static/css/style.css` — all styling.
- `static/img/logo.png`, `static/img/banner.jpg` — your brand images.
- `requirements.txt` — Python dependencies.
- `render.yaml` — optional Render Blueprint (lets Render auto-fill build/start
  commands if you use "New > Blueprint" instead of "New > Web Service").

## Running locally

```bash
pip install -r requirements.txt
python app.py
```

Visit `http://localhost:5000`.

## Deploying on Render

1. Push this folder to a GitHub repository.
2. On Render: **New > Web Service** (or **New > Blueprint** if you keep `render.yaml`).
3. Connect the repo.
4. If not using the Blueprint, set manually:
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `gunicorn app:app`
5. Add environment variables (Render dashboard → Environment):
   - `ADMIN_USER` — username for viewing orders (e.g. `sumi`)
   - `ADMIN_PASS` — a real password (don't leave the default)
   - Optional, only if you want email alerts on every new order:
     - `SMTP_HOST`, `SMTP_PORT` (usually `587`), `SMTP_USER`, `SMTP_PASS`,
       `NOTIFY_EMAIL` (where alerts get sent)
     - For Gmail: use an **App Password**, not your normal Gmail password.
6. Deploy. Render gives you a live `.onrender.com` URL.

## Important note on the database

This uses **SQLite**, a single file (`mentora.db`) written to disk. On Render's
**free plan, the filesystem is not persistent** — it resets on every deploy or
restart, which means stored orders can be lost. Two ways to handle this:

- **Fine for now**: rely on the optional email notifications (set the `SMTP_*`
  vars above) so you get every order by email the moment it's submitted, even
  if the database itself resets later.
- **For real persistence**: attach a Render **paid disk** to this service, or
  swap SQLite for Render's managed **Postgres** (a bigger change to `app.py`
  — ask if you want this done).

## Viewing submitted orders

Go to `https://<your-render-url>/admin/orders` and log in with the
`ADMIN_USER` / `ADMIN_PASS` you set.

## Customizing tracks, contact info, or pricing copy

- Tracks shown on the site: edit the `TRACKS` list near the top of `app.py`.
- Contact details/social links: edit the `CONTACT` dict in `app.py`.
- Everything else (copy, sections, layout): `templates/index.html` and
  `static/css/style.css`.
