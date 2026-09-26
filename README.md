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
6. Deploy. Render gives you a live `.onrender.com` URL.

Render's Free web services block outbound SMTP ports, so email alerts will not
work on the Free plan. The order form and admin page still run, but SQLite
storage is temporary on Render Free.

## Important note on free hosting

This uses **SQLite**, a single file (`mentora.db`) written to disk. Render Free
web services spin down after 15 minutes without traffic and have an ephemeral
filesystem, so orders can be lost on spin-down, restart, or deploy. Free Render
Postgres expires after 30 days, so it is not durable free storage either.

Use the Free plan for a demo or testing, not as the only record of real order
requests. Reliable order storage requires a persistent paid disk or a durable
external database.

## Viewing submitted orders

Go to `https://<your-render-url>/admin/orders` and log in with the
`ADMIN_USER` / `ADMIN_PASS` you set.

## Customizing tracks, contact info, or pricing copy

- Tracks shown on the site: edit the `TRACKS` list near the top of `app.py`.
- Contact details/social links: edit the `CONTACT` dict in `app.py`.
- Everything else (copy, sections, layout): `templates/index.html` and
  `static/css/style.css`.
