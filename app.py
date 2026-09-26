import os
import sqlite3
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, render_template, request, jsonify, g, Response
import psycopg
from psycopg.rows import dict_row

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "mentora.db")
DATABASE_URL = os.environ.get("DATABASE_URL")

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "changeme")

SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL")  # where new-order alerts get sent


# ---------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------

def get_db():
    if "db" not in g:
        if DATABASE_URL:
            g.db = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        else:
            g.db = sqlite3.connect(DB_PATH)
            g.db.row_factory = sqlite3.Row
    return g.db


def execute_query(db, query, params=()):
    if DATABASE_URL:
        query = query.replace("?", "%s")
    return db.execute(query, params)


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    if DATABASE_URL:
        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        id_column = "BIGSERIAL PRIMARY KEY"
    else:
        conn = sqlite3.connect(DB_PATH)
        id_column = "INTEGER PRIMARY KEY AUTOINCREMENT"
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS orders (
            id {id_column},
            name TEXT NOT NULL,
            contact TEXT NOT NULL,
            track TEXT NOT NULL,
            message TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------
# Optional email notification (only fires if SMTP env vars are set)
# ---------------------------------------------------------------------

def notify_new_order(order):
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS and NOTIFY_EMAIL):
        return  # email notifications not configured — order is still saved in the DB
    try:
        body = (
            f"New order on Mentora Labs\n\n"
            f"Name: {order['name']}\n"
            f"Contact: {order['contact']}\n"
            f"Track: {order['track']}\n"
            f"Message: {order['message'] or '(none)'}\n"
            f"Received: {order['created_at']}\n"
        )
        msg = MIMEText(body)
        msg["Subject"] = f"New Mentora Labs order — {order['track']}"
        msg["From"] = SMTP_USER
        msg["To"] = NOTIFY_EMAIL

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, [NOTIFY_EMAIL], msg.as_string())
    except Exception as e:
        # never let a notification failure break the order submission
        app.logger.warning(f"Email notification failed: {e}")


# ---------------------------------------------------------------------
# Basic auth for the admin view
# ---------------------------------------------------------------------

def check_auth(username, password):
    return username == ADMIN_USER and password == ADMIN_PASS


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return Response(
                "Login required", 401,
                {"WWW-Authenticate": 'Basic realm="Mentora Labs Admin"'},
            )
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------
# Routes — site
# ---------------------------------------------------------------------

TRACKS = [
    {
        "key": "nids",
        "tag": "Security · ML",
        "title": "NIDS — Network Intrusion Detection",
        "desc": "A GAN-based system that flags malicious traffic on 5G networks.",
        "chips": ["Python", "TensorFlow", "GANs"],
    },
    {
        "key": "skin",
        "tag": "Healthcare · CV",
        "title": "Skin Disease Classification",
        "desc": "An image classifier that identifies common skin conditions from photos.",
        "chips": ["Python", "CNN", "Flask"],
    },
    {
        "key": "expense",
        "tag": "Full stack",
        "title": "Expense Tracker",
        "desc": "A budgeting app with spend categories, monthly summaries, and charts.",
        "chips": ["Flask", "HTML/CSS", "SQL"],
    },
]

CONTACT = {
    "phones": ["+91 74491 52395", "+91 76048 94278"],
    "whatsapp_number": "917449152395",
    "email": "mentoralabs123@gmail.com",
    "instagram": "https://www.instagram.com/mentora_labs.builds?stkn=MWk1bXdvdHVtcngwOQ==",
    "facebook": "https://www.facebook.com/share/1HTCs92zzT/",
    "whatsapp_channel": "https://whatsapp.com/channel/0029VbDPRqj4tRrzaQ6QRk1h",
    "telegram": "https://t.me/mentoralabs",
    "linkedin": "https://www.linkedin.com/in/mentora-labs-9b292943a",
    "google_review": "https://share.google/nfG1TgIeV6ZU2LZHu",
}


@app.route("/")
def index():
    return render_template("index.html", tracks=TRACKS, contact=CONTACT)


@app.route("/api/orders", methods=["POST"])
def create_order():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    contact = (data.get("contact") or "").strip()
    track = (data.get("track") or "").strip()
    message = (data.get("message") or "").strip()

    if not name or not contact or not track:
        return jsonify({"error": "name, contact, and track are required"}), 400

    created_at = datetime.now(timezone.utc).isoformat()

    db = get_db()
    execute_query(
        db,
        "INSERT INTO orders (name, contact, track, message, created_at) VALUES (?, ?, ?, ?, ?)",
        (name, contact, track, message, created_at),
    )
    db.commit()

    notify_new_order({
        "name": name, "contact": contact, "track": track,
        "message": message, "created_at": created_at,
    })

    return jsonify({"status": "ok"}), 201


# ---------------------------------------------------------------------
# Admin — view submitted orders (protected)
# ---------------------------------------------------------------------

@app.route("/admin/orders")
@requires_auth
def admin_orders():
    db = get_db()
    rows = execute_query(db, "SELECT * FROM orders ORDER BY id DESC").fetchall()
    return render_template("admin.html", orders=rows)


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
else:
    # also run under gunicorn (Render's production server)
    init_db()
