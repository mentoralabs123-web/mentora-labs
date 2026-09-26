# Mentora Labs

Full-stack site: Flask backend + templated frontend, with an order form backed by
a real API and a database. It uses PostgreSQL when `DATABASE_URL` is set and
SQLite for local development otherwise.

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
work on the Free plan. Set `DATABASE_URL` to a Neon PostgreSQL connection string
to keep orders outside Render's temporary filesystem.

## Connect Neon PostgreSQL

1. Create a project in Neon and copy its PostgreSQL connection string. Use the
  pooled connection string and make sure it includes `sslmode=require`.
2. In Render, open the `mentora-labs` service and go to **Environment**.
3. Add `DATABASE_URL` with the connection string as its value. Treat it as a
  password: do not put it in GitHub, source files, or chat.
4. Save the change and redeploy. The app creates the `orders` table on startup.
5. Submit a test order, then view it at `/admin/orders` using your admin login.

The Render Blueprint declares `DATABASE_URL` as a secret prompt for initial
setup. For an already-created Render service, add it manually in **Environment**.
Without `DATABASE_URL`, the app falls back to SQLite, whose data is temporary on
Render Free. Neon free-tier limits and availability are subject to Neon's terms;
keep backups for important order records.

## Viewing submitted orders

Go to `https://<your-render-url>/admin/orders` and log in with the
`ADMIN_USER` / `ADMIN_PASS` you set.

## Customizing tracks, contact info, or pricing copy

- Tracks shown on the site: edit the `TRACKS` list near the top of `app.py`.
- Contact details/social links: edit the `CONTACT` dict in `app.py`.
- Everything else (copy, sections, layout): `templates/index.html` and
  `static/css/style.css`.
