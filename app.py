"""
Association T-Shirt QR System: Dual-Message Architecture
=========================================================
Features:
1. Member Personal Message: Each member has their own permanent T-shirt with their
   unique QR code, personal message, role, and contact details.
2. Global Admin Broadcast (Editable Anytime): A shared association announcement that
   updates across ALL members' T-shirts simultaneously.
3. Scheduled Ending Time: Admin can set an exact expiration date & time for the broadcast.
   When the timer expires, all T-shirts automatically revert back to showing only the
   member's personal message.
4. Mode Switching ("Jb mann krega admin ka tb woh khud ka msg daal skta h yaa fir owner ka"):
   - 'both': Shows Association Announcement on top + Member Profile & Message below.
   - 'admin_only': Admin message takes over full screen (for events/rallies/urgent notices).
   - 'member_only': Hides admin broadcast and displays only the T-shirt owner's message.
5. 24/7 Cloud Ready: Runs online with PostgreSQL or persistent SQLite, Gunicorn, and Level H QR codes.
"""

import io
import os
import re
import secrets
from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    render_template_string,
    request,
    send_file,
    session,
    url_for,
)
import jinja2
from flask_sqlalchemy import SQLAlchemy

# QR code library with high-res PIL and SVG image factories
try:
    import qrcode
    import qrcode.image.svg
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False

# Barcode library with PIL and SVG writers
try:
    import barcode
    from barcode.writer import ImageWriter, SVGWriter
    HAS_BARCODE = True
except ImportError:
    HAS_BARCODE = False

# Optional markdown rendering
try:
    import markdown
    HAS_MARKDOWN = True
except ImportError:
    HAS_MARKDOWN = False

# -----------------------------------------------------------------------------
# Configuration & Database Initialization
# -----------------------------------------------------------------------------
app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", secrets.token_hex(32))

def get_database_url():
    candidates = [
        "DATABASE_URL",
        "DATABASE_URI",
        "DB_URL",
        "POSTGRES_URL",
        "POSTGRESQL_URL",
        "NEON_URL",
        "NEON_DATABASE_URL",
        "SQLALCHEMY_DATABASE_URI",
    ]
    # Check exact match or trimmed/case-insensitive match in os.environ
    for key, val in os.environ.items():
        if key.strip().upper() in candidates and val and val.strip():
            url = val.strip().strip("'").strip('"')
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql+psycopg2://", 1)
            elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
                url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
            return url, key.strip()
    return "sqlite:///association_tshirts.db", "LOCAL_DEFAULT"

db_url, db_env_source = get_database_url()
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["DB_ENV_SOURCE"] = db_env_source
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Public base domain/URL (crucial for encoding absolute URLs in printable QR codes)
app.config["BASE_URL"] = (
    os.environ.get("BASE_URL")
    or os.environ.get("RENDER_EXTERNAL_URL")
    or "http://127.0.0.1:5000"
).rstrip("/")

# Admin dashboard password
app.config["ADMIN_PASSWORD"] = os.environ.get("ADMIN_PASSWORD", "admin123")

db = SQLAlchemy(app)

# -----------------------------------------------------------------------------
# Database Models
# -----------------------------------------------------------------------------
class GlobalBroadcast(db.Model):
    """
    Association-wide broadcast message managed exclusively by the Admin.
    Applies across ALL members' T-shirts simultaneously.
    """
    __tablename__ = "global_broadcast"

    id = db.Column(db.Integer, primary_key=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    # mode options: 'both' (Banner + Member), 'admin_only' (Takeover), 'member_only'
    mode = db.Column(db.String(20), default="both", nullable=False)
    title = db.Column(db.String(150), default="Official Association Notice", nullable=False)
    message = db.Column(db.Text, default="Welcome to our Association! Stay connected for our upcoming community drives.", nullable=False)
    # Scheduled ending time (Expiration datetime)
    expires_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def is_currently_live(self):
        """Returns True if the broadcast is active and has not expired."""
        if not self.is_active:
            return False
        if self.expires_at:
            # Compare with UTC/server time
            if datetime.utcnow() > self.expires_at:
                return False
        return True


def generate_unique_tshirt_id():
    """Generates a unique 10-character ID (e.g. 'TS' + 8 hex digits = 10 chars)."""
    while True:
        candidate = f"TS{secrets.token_hex(4).upper()}"
        if not TShirt.query.get(candidate):
            return candidate


class TShirt(db.Model):
    """
    Individual T-shirt assigned to a specific association member.
    The QR code points permanently to /t/<slug>.
    """
    __tablename__ = "tshirts"

    id = db.Column(db.String(10), primary_key=True, default=generate_unique_tshirt_id)
    slug = db.Column(db.String(32), unique=True, nullable=False, index=True)
    member_name = db.Column(db.String(120), nullable=False)
    member_role = db.Column(db.String(100), default="Member", nullable=False)
    member_message = db.Column(db.Text, nullable=False, default="Proud member of this association. Scan my T-shirt anytime!")
    member_phone = db.Column(db.String(30), nullable=True)
    accent_color = db.Column(db.String(7), default="#2563eb", nullable=False)
    scan_count = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Please sign in to access the Association Admin Panel.", "warning")
            return redirect(url_for("admin_login", next=request.path))
        return f(*args, **kwargs)
    return decorated_function


def generate_unique_slug(prefix="mem-", length=6):
    while True:
        candidate = f"{prefix}{secrets.token_hex(length // 2)}"
        if not TShirt.query.filter_by(slug=candidate).first():
            return candidate


def render_markdown_or_safe_html(text):
    if HAS_MARKDOWN:
        return markdown.markdown(text, extensions=["extra", "nl2br", "sane_lists"], output_format="html5")
    from markupsafe import escape
    return str(escape(text)).replace("\n", "<br>\n")


# -----------------------------------------------------------------------------
# HTML Templates
# -----------------------------------------------------------------------------
BASE_LAYOUT = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
  <title>{% block title %}Association T-Shirt QR Manager{% endblock %}</title>
  <style>
    :root {
      --primary: #2563eb;
      --primary-hover: #1d4ed8;
      --bg: #f8fafc;
      --surface: #ffffff;
      --text: #0f172a;
      --text-muted: #64748b;
      --border: #e2e8f0;
      --radius: 14px;
      --shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05);
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.6;
    }
    .navbar {
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 0.9rem 1.5rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .navbar-brand {
      font-weight: 800;
      font-size: 1.15rem;
      color: var(--text);
      text-decoration: none;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 0.4rem;
      padding: 0.6rem 1.1rem;
      border-radius: 8px;
      font-size: 0.9rem;
      font-weight: 600;
      text-decoration: none;
      border: 1px solid transparent;
      cursor: pointer;
      transition: all 0.15s ease-in-out;
    }
    .btn-primary { background: var(--primary); color: white; }
    .btn-primary:hover { background: var(--primary-hover); }
    .btn-secondary { background: #f1f5f9; color: #334155; border-color: var(--border); }
    .btn-secondary:hover { background: #e2e8f0; }
    .btn-danger { background: #ef4444; color: white; }
    .btn-success { background: #10b981; color: white; }
    .btn-sm { padding: 0.35rem 0.75rem; font-size: 0.82rem; }
    .container { max-width: 1050px; margin: 1.75rem auto; padding: 0 1rem; }
    .alert { padding: 0.85rem 1.25rem; border-radius: 8px; margin-bottom: 1.25rem; font-size: 0.95rem; }
    .alert-success { background: #ecfdf5; color: #065f46; border: 1px solid #a7f3d0; }
    .alert-warning { background: #fffbeb; color: #92400e; border: 1px solid #fde68a; }
    .alert-danger { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
    .card {
      background: var(--surface);
      border-radius: var(--radius);
      border: 1px solid var(--border);
      box-shadow: var(--shadow);
      padding: 1.75rem;
      margin-bottom: 1.75rem;
    }
  </style>
</head>
<body>
  {% if session.get('is_admin') %}
  <header class="navbar">
    <a href="{{ url_for('admin_dashboard') }}" class="navbar-brand">
      <span>👕</span> Association QR Control
    </a>
    <div style="display:flex; gap:0.75rem; align-items:center;">
      <a href="{{ url_for('admin_new_tshirt') }}" class="btn btn-primary btn-sm">+ Add Member T-Shirt</a>
      <a href="{{ url_for('admin_logout') }}" class="btn btn-secondary btn-sm">Sign Out</a>
    </div>
  </header>
  {% endif %}

  <main class="container">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category, msg in messages %}
          <div class="alert alert-{{ category }}">{{ msg }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}
    {% block content %}{% endblock %}
  </main>
</body>
</html>
"""

SCAN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
  <title>{{ tshirt.member_name }} | Association Member</title>
  <style>
    :root {
      --accent: {{ tshirt.accent_color or '#2563eb' }};
      --bg: #090d16;
      --card-bg: rgba(23, 30, 48, 0.9);
      --card-border: rgba(255, 255, 255, 0.1);
      --text: #f8fafc;
      --text-muted: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
      background: radial-gradient(circle at 50% 0%, #1e293b 0%, var(--bg) 100%);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 1.25rem;
      -webkit-font-smoothing: antialiased;
    }
    .wrapper { width: 100%; max-width: 480px; margin: auto; }
    
    /* Admin Broadcast Alert Banner */
    .broadcast-banner {
      background: linear-gradient(135deg, rgba(234, 88, 12, 0.15) 0%, rgba(245, 158, 11, 0.25) 100%);
      border: 2px solid #f59e0b;
      border-radius: 20px;
      padding: 1.5rem;
      margin-bottom: 1.5rem;
      box-shadow: 0 15px 30px -10px rgba(245, 158, 11, 0.3);
      position: relative;
    }
    .broadcast-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      padding: 0.3rem 0.75rem;
      background: #f59e0b;
      color: #0f172a;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 0.75rem;
    }
    .broadcast-title {
      font-size: 1.25rem;
      font-weight: 800;
      color: #fbbf24;
      margin-bottom: 0.5rem;
      line-height: 1.3;
    }
    .broadcast-body {
      font-size: 0.98rem;
      color: #fef3c7;
      line-height: 1.6;
      word-break: break-word;
    }
    .broadcast-expiry {
      margin-top: 0.85rem;
      font-size: 0.78rem;
      color: #fde68a;
      display: flex;
      align-items: center;
      gap: 0.35rem;
      border-top: 1px dashed rgba(245, 158, 11, 0.4);
      padding-top: 0.65rem;
    }

    /* Member Card */
    .member-card {
      background: var(--card-bg);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid var(--card-border);
      border-radius: 24px;
      padding: 2.25rem 1.75rem;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.6);
      text-align: center;
    }
    .avatar-circle {
      width: 72px;
      height: 72px;
      border-radius: 50%;
      background: var(--accent);
      color: white;
      font-size: 1.85rem;
      font-weight: 800;
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0 auto 1rem;
      box-shadow: 0 0 20px var(--accent);
    }
    .member-name {
      font-size: 1.65rem;
      font-weight: 800;
      letter-spacing: -0.02em;
      margin-bottom: 0.25rem;
    }
    .member-role {
      font-size: 0.95rem;
      font-weight: 600;
      color: var(--accent);
      text-transform: uppercase;
      letter-spacing: 0.04em;
      margin-bottom: 1.5rem;
    }
    .message-box {
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 16px;
      padding: 1.35rem;
      font-size: 1.05rem;
      line-height: 1.65;
      text-align: left;
      margin-bottom: 1.5rem;
      color: #e2e8f0;
    }
    .meta-footer {
      border-top: 1px solid rgba(255, 255, 255, 0.08);
      padding-top: 1rem;
      display: flex;
      justify-content: space-between;
      font-size: 0.75rem;
      color: var(--text-muted);
    }
  </style>
</head>
<body>
  <div class="wrapper">

    {# SCENARIO 1: Admin Takeover Mode (Admin message only) #}
    {% if show_broadcast and broadcast_mode == 'admin_only' %}
      <div class="member-card" style="border: 2px solid #f59e0b; box-shadow: 0 0 40px rgba(245, 158, 11, 0.2);">
        <div class="broadcast-badge">📢 Official Association Announcement</div>
        <h1 style="font-size: 1.7rem; color: #fbbf24; margin-bottom: 1rem;">{{ broadcast.title }}</h1>
        
        <div class="message-box" style="background: rgba(120, 53, 15, 0.25); border-color: rgba(245, 158, 11, 0.3);">
          {{ broadcast_msg_html|safe }}
        </div>

        {% if broadcast.expires_at %}
          <div style="font-size: 0.8rem; color: #fde68a; margin-bottom: 1.5rem;">
            ⏳ Active until: <strong>{{ broadcast.expires_at.strftime('%d %b %Y, %I:%M %p') }} UTC</strong>
          </div>
        {% endif %}

        <div style="background: rgba(255,255,255,0.04); border-radius: 12px; padding: 0.85rem; font-size: 0.85rem; color: var(--text-muted);">
          👕 Scanned from <strong>{{ tshirt.member_name }}</strong>'s T-Shirt ({{ tshirt.member_role }})
        </div>
      </div>

    {# SCENARIO 2: Both Mode OR Member Only Mode #}
    {% else %}
      
      {# Show Broadcast Banner at Top if Active in 'both' mode #}
      {% if show_broadcast and broadcast_mode == 'both' %}
        <div class="broadcast-banner">
          <div class="broadcast-badge">📢 Association Notice</div>
          <div class="broadcast-title">{{ broadcast.title }}</div>
          <div class="broadcast-body">{{ broadcast_msg_html|safe }}</div>
          {% if broadcast.expires_at %}
            <div class="broadcast-expiry">
              <span>⏳</span>
              <span>Notice active until {{ broadcast.expires_at.strftime('%d %b %Y, %I:%M %p') }} UTC</span>
            </div>
          {% endif %}
        </div>
      {% endif %}

      {# Member Personal Card #}
      <div class="member-card">
        <div class="avatar-circle">
          {{ tshirt.member_name[0]|upper }}
        </div>
        <h1 class="member-name">{{ tshirt.member_name }}</h1>
        <div class="member-role">{{ tshirt.member_role }}</div>

        <div class="message-box">
          {{ member_msg_html|safe }}
        </div>

        {% if tshirt.member_phone %}
          <div style="margin-bottom: 1.25rem;">
            <a href="tel:{{ tshirt.member_phone }}" style="display:inline-block; padding:0.6rem 1.2rem; background:rgba(255,255,255,0.08); border:1px solid var(--card-border); color:white; text-decoration:none; border-radius:10px; font-size:0.9rem;">
              📞 Call: {{ tshirt.member_phone }}
            </a>
          </div>
        {% endif %}

        <div class="meta-footer">
          <span>● Verified Association Member</span>
          <span>Scan #{{ tshirt.scan_count }}</span>
        </div>
      </div>
    {% endif %}

    <p style="text-align:center; margin-top:1.5rem; font-size:0.75rem; color:#64748b;">
      Powered by Association 24/7 Dynamic T-Shirt QR
    </p>
  </div>
</body>
</html>
"""

ADMIN_DASHBOARD_TEMPLATE = """
{% extends "base" %}
{% block title %}Admin Dashboard | Association T-Shirts{% endblock %}
{% block content %}
<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 1.75rem; flex-wrap:wrap; gap:1rem;">
  <div>
    <div style="display:flex; align-items:center; gap:0.6rem; flex-wrap:wrap;">
      <h1 style="font-size: 1.85rem; font-weight:800; letter-spacing:-0.03em;">Association T-Shirt Control Center</h1>
      <span style="font-size:0.75rem; padding:0.25rem 0.65rem; border-radius:999px; background: {{ '#dcfce7' if is_postgres else '#fee2e2' }}; color: {{ '#166534' if is_postgres else '#991b1b' }}; font-weight:700; border: 1px solid {{ '#86efac' if is_postgres else '#fca5a5' }};">
        {{ '🟢 ' + db_backend if is_postgres else '⚠️ Local: SQLite (Not Cloud)' }}
      </span>
    </div>
    <p style="color:var(--text-muted); font-size:0.95rem;">
      Manage your live broadcast announcements and individual members' permanent QR T-shirts.
    </p>
  </div>
  <a href="{{ url_for('admin_new_tshirt') }}" class="btn btn-primary">+ Add New Member T-Shirt</a>
</div>

<!-- ========================================================================= -->
<!-- SECTION 1: GLOBAL BROADCAST CONTROLLER (THE EDITABLE ADMIN MESSAGE)       -->
<!-- ========================================================================= -->
<div class="card" style="border: 2px solid #f59e0b; background: #fffdf5;">
  <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:1rem; margin-bottom:1.25rem; border-bottom: 1px solid #fef3c7; padding-bottom: 1rem;">
    <div>
      <span style="background:#f59e0b; color:#0f172a; font-weight:800; font-size:0.75rem; padding:0.25rem 0.65rem; border-radius:999px; text-transform:uppercase;">
        Master Control
      </span>
      <h2 style="font-size: 1.35rem; font-weight:800; margin-top:0.35rem; color:#78350f;">
        Message Broadcast
      </h2>
      <p style="font-size:0.88rem; color:#92400e;">
        Can be seen on every tshirt
      </p>
    </div>

    <!-- Current Live Status Badge -->
    <div>
      {% if is_broadcast_live %}
        <span style="display:inline-flex; align-items:center; gap:0.4rem; background:#ecfdf5; color:#065f46; border:1px solid #a7f3d0; padding:0.4rem 0.85rem; border-radius:999px; font-weight:700; font-size:0.85rem;">
          <span style="width:8px; height:8px; border-radius:50%; background:#10b981;"></span>
          BROADCAST ACTIVE (Showing {{ broadcast.mode|upper }})
        </span>
      {% else %}
        <span style="display:inline-flex; align-items:center; gap:0.4rem; background:#f1f5f9; color:#64748b; border:1px solid #e2e8f0; padding:0.4rem 0.85rem; border-radius:999px; font-weight:700; font-size:0.85rem;">
          ⚪ BROADCAST INACTIVE (Showing Member Message Only)
        </span>
      {% endif %}
    </div>
  </div>

  <form action="{{ url_for('admin_update_broadcast') }}" method="POST">
    <div style="display:grid; grid-template-columns: 2fr 1fr; gap:1.25rem; margin-bottom: 1.25rem;">
      <!-- Title & Message -->
      <div>
        <label style="display:block; font-weight:700; margin-bottom:0.35rem; font-size:0.9rem;">Announcement Heading</label>
        <input type="text" name="title" required value="{{ broadcast.title }}" style="width:100%; padding:0.65rem; border-radius:8px; border:1px solid var(--border); font-size:0.95rem; margin-bottom:0.85rem;">

        <label style="display:block; font-weight:700; margin-bottom:0.35rem; font-size:0.9rem;">Broadcast Message Content</label>
        <textarea name="message" rows="4" required style="width:100%; padding:0.65rem; border-radius:8px; border:1px solid var(--border); font-size:0.95rem; font-family:inherit;">{{ broadcast.message }}</textarea>
      </div>

      <!-- Controls: Mode & Scheduled Ending Time -->
      <div style="background:#ffffff; border:1px solid #fed7aa; border-radius:12px; padding:1.25rem;">
        <label style="display:block; font-weight:700; margin-bottom:0.4rem; font-size:0.9rem;">Display Priority Mode</label>
        <select name="mode" style="width:100%; padding:0.55rem; border-radius:6px; border:1px solid var(--border); margin-bottom:1rem; font-size:0.9rem;">
          <option value="both" {{ 'selected' if broadcast.mode == 'both' else '' }}>Both (Admin Banner + Member Profile)</option>
          <option value="admin_only" {{ 'selected' if broadcast.mode == 'admin_only' else '' }}>Admin Only (Takeover full screen)</option>
          <option value="member_only" {{ 'selected' if broadcast.mode == 'member_only' else '' }}>Member Only (Hide Admin Message)</option>
        </select>

        <label style="display:block; font-weight:700; margin-bottom:0.4rem; font-size:0.9rem;">
          Scheduled Ending Time
        </label>
        <input type="datetime-local" name="expires_at" value="{{ expiry_str }}" style="width:100%; padding:0.55rem; border-radius:6px; border:1px solid var(--border); margin-bottom:0.5rem; font-size:0.88rem;">
        <small style="display:block; color:#78350f; font-size:0.78rem; line-height:1.4;">
          After this timer!! Every tshirt will back to their normal quote
        </small>

        <div style="margin-top:1rem; padding-top:0.75rem; border-top:1px solid #fde68a;">
          <label style="display:flex; align-items:center; gap:0.5rem; font-size:0.9rem; font-weight:700; cursor:pointer;">
            <input type="checkbox" name="is_active" value="1" {{ 'checked' if broadcast.is_active else '' }}>
            Enable Broadcast Now
          </label>
        </div>
      </div>
    </div>

    <div style="display:flex; justify-content:flex-end; gap:0.75rem;">
      <button type="submit" class="btn btn-primary" style="background:#d97706; border-color:#b45309; padding:0.7rem 1.75rem;">
        Save & Push Broadcast Live
      </button>
    </div>
  </form>
</div>

<!-- ========================================================================= -->
<!-- SECTION 2: MEMBER T-SHIRT FLEET (PERMANENT QR CODES)                     -->
<!-- ========================================================================= -->
<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
  <h2 style="font-size: 1.35rem; font-weight:800;">Member T-Shirts ({{ tshirts|length }})</h2>
  <div style="font-size:0.85rem; color:var(--text-muted);">
    Total Scans Recorded: <strong>{{ tshirts|sum(attribute='scan_count') }}</strong>
  </div>
</div>

{% if not tshirts %}
  <div class="card" style="text-align:center; padding: 3rem 1.5rem;">
    <div style="font-size: 3rem; margin-bottom: 0.75rem;"></div>
    <h3>No Member T-Shirts registered yet</h3>
    <p style="color:var(--text-muted); margin: 0.5rem 0 1.25rem;">
      Add each member's details to generate their permanent print-ready QR code.
    </p>
    <a href="{{ url_for('admin_new_tshirt') }}" class="btn btn-primary">+ Register First Member T-Shirt</a>
  </div>
{% else %}
  <div class="card" style="padding: 0; overflow:hidden;">
    <div style="overflow-x:auto;">
      <table style="width: 100%; border-collapse: collapse; text-align:left; font-size:0.95rem;">
        <thead>
          <tr style="background:#f1f5f9; border-bottom:1px solid var(--border); font-size:0.8rem; text-transform:uppercase; color:var(--text-muted);">
            <th style="padding:1rem 1.25rem;">Member Details</th>
            <th style="padding:1rem 1.25rem;">Personal Message</th>
            <th style="padding:1rem 1.25rem; text-align:center;">Scans</th>
            <th style="padding:1rem 1.25rem; text-align:center;">Print Codes (QR / Barcode)</th>
            <th style="padding:1rem 1.25rem; text-align:right;">Actions</th>
          </tr>
        </thead>
        <tbody>
          {% for shirt in tshirts %}
          <tr style="border-bottom:1px solid var(--border);">
            <td style="padding:1.15rem 1.25rem;">
              <div style="font-weight:700; color:var(--text); font-size:1.05rem;">
                {{ shirt.member_name }}
              </div>
              <div style="font-size:0.82rem; color:var(--primary); font-weight:600;">
                {{ shirt.member_role }}
              </div>
              <div style="font-size:0.75rem; color:var(--text-muted); font-family:monospace; margin-top:2px;">
                ID: <span style="color:#0f172a; font-weight:700;">{{ shirt.id }}</span> &bull; Slug: {{ shirt.slug }}
              </div>
            </td>
            <td style="padding:1.15rem 1.25rem; max-width:280px;">
              <div style="color:#334155; font-size:0.9rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                {{ shirt.member_message }}
              </div>
              {% if shirt.member_phone %}
                <div style="font-size:0.75rem; color:var(--text-muted); margin-top:2px;">
                   {{ shirt.member_phone }}
                </div>
              {% endif %}
            </td>
            <td style="padding:1.15rem 1.25rem; text-align:center;">
              <span style="display:inline-block; background:#e0f2fe; color:#0369a1; padding:0.2rem 0.65rem; border-radius:999px; font-weight:700; font-size:0.85rem;">
                {{ shirt.scan_count }}
              </span>
            </td>
            <td style="padding:1.15rem 1.25rem; text-align:center;">
              <div style="display:inline-flex; align-items:center; gap:0.5rem; justify-content:center;">
                <a href="{{ url_for('qr_png', slug=shirt.slug) }}" target="_blank" title="View 300 DPI QR Code">
                  <img src="{{ url_for('qr_png', slug=shirt.slug) }}" width="42" height="42" style="border:1px solid var(--border); border-radius:6px; vertical-align:middle;" alt="QR">
                </a>
                <a href="{{ url_for('barcode_png', slug=shirt.slug) }}" target="_blank" title="View Code 128 Barcode">
                  <img src="{{ url_for('barcode_png', slug=shirt.slug) }}" height="42" style="border:1px solid var(--border); border-radius:6px; vertical-align:middle; max-width:76px; object-fit:contain; background:#fff; padding:2px;" alt="Barcode">
                </a>
              </div>
            </td>
            <td style="padding:1.15rem 1.25rem; text-align:right;">
              <div style="display:inline-flex; gap:0.35rem;">
                <a href="{{ url_for('scan_tshirt', slug=shirt.slug) }}" target="_blank" class="btn btn-secondary btn-sm" title="Preview Mobile Scan">👁️ View</a>
                <a href="{{ url_for('admin_edit_tshirt', id=shirt.id) }}" class="btn btn-primary btn-sm" title="Edit Member Info">✏️ Edit</a>
                <a href="{{ url_for('admin_print_card', id=shirt.id) }}" target="_blank" class="btn btn-secondary btn-sm" title="Print Shop Sheet">🖨️ Print Sheet</a>
                <form action="{{ url_for('admin_delete_tshirt', id=shirt.id) }}" method="POST" style="display:inline;" onsubmit="return confirm('Are you sure you want to delete this member T-shirt?');">
                  <button type="submit" class="btn btn-danger btn-sm">🗑️</button>
                </form>
              </div>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
{% endif %}
{% endblock %}
"""

ADMIN_EDIT_MEMBER_TEMPLATE = """
{% extends "base" %}
{% block title %}{{ 'Edit Member' if tshirt else 'Add New Member' }} | Association QR{% endblock %}
{% block content %}
<div style="max-width: 650px; margin: auto;">
  <div style="margin-bottom: 1.5rem;">
    <a href="{{ url_for('admin_dashboard') }}" style="color:var(--text-muted); text-decoration:none; font-size:0.9rem;">&larr; Back to Control Center</a>
    <h1 style="font-size: 1.75rem; font-weight:800; margin-top:0.4rem;">
      {{ 'Edit Member T-Shirt Details' if tshirt else 'Register New Member T-Shirt' }}
    </h1>
    <p style="color:var(--text-muted); font-size:0.9rem;">
      The generated QR code is permanent. You can edit this member's details anytime.
    </p>
  </div>

  <div class="card">
    <form method="POST">
      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:1rem; margin-bottom: 1.25rem;">
        <div>
          <label style="display:block; font-weight:700; margin-bottom:0.35rem; font-size:0.9rem;">Member Name</label>
          <input type="text" name="member_name" required value="{{ tshirt.member_name if tshirt else '' }}" placeholder="e.g., Rajesh Sharma" style="width:100%; padding:0.7rem; border-radius:8px; border:1px solid var(--border); font-size:0.95rem;">
        </div>
        <div>
          <label style="display:block; font-weight:700; margin-bottom:0.35rem; font-size:0.9rem;">Role / Designation</label>
          <input type="text" name="member_role" value="{{ tshirt.member_role if tshirt else 'Core Member' }}" placeholder="e.g., Volunteer Coordinator" style="width:100%; padding:0.7rem; border-radius:8px; border:1px solid var(--border); font-size:0.95rem;">
        </div>
      </div>

      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:1rem; margin-bottom: 1.25rem;">
        <div>
          <label style="display:block; font-weight:700; margin-bottom:0.35rem; font-size:0.9rem;">
            Member ID (Max 10 chars)
            <span style="font-weight:400; color:var(--text-muted); font-size:0.8rem;">({{ 'Permanent' if tshirt else 'Auto if blank' }})</span>
          </label>
          <input type="text" name="custom_id" maxlength="10" {{ 'readonly' if tshirt else '' }} value="{{ tshirt.id if tshirt else '' }}" placeholder="e.g. TSH0000001" style="width:100%; padding:0.7rem; border-radius:8px; border:1px solid var(--border); font-size:0.95rem; font-family:monospace; text-transform:uppercase; background: {{ '#f8fafc' if tshirt else '#ffffff' }};">
        </div>
        <div>
          <label style="display:block; font-weight:700; margin-bottom:0.35rem; font-size:0.9rem;">
            Permanent QR Slug
            <span style="font-weight:400; color:var(--text-muted); font-size:0.8rem;">(URL path)</span>
          </label>
          <input type="text" name="slug" {{ 'readonly' if tshirt else '' }} value="{{ tshirt.slug if tshirt else default_slug }}" style="width:100%; padding:0.7rem; border-radius:8px; border:1px solid var(--border); font-size:0.95rem; font-family:monospace; background: {{ '#f8fafc' if tshirt else '#ffffff' }};">
        </div>
      </div>

      <div style="margin-bottom: 1.25rem;">
        <label style="display:block; font-weight:700; margin-bottom:0.35rem; font-size:0.9rem;">
          Member's Personal Message
        </label>
        <textarea name="member_message" rows="5" required placeholder="Write the member's bio, welcome message, or personal quote..." style="width:100%; padding:0.7rem; border-radius:8px; border:1px solid var(--border); font-size:0.95rem; font-family:inherit; line-height:1.5;">{{ tshirt.member_message if tshirt else 'Proud member of Jaipur Youth Association. Committed to social work and community welfare!' }}</textarea>
      </div>

      <div style="display:grid; grid-template-columns: 2fr 1fr; gap:1rem; margin-bottom: 1.5rem;">
        <div>
          <label style="display:block; font-weight:700; margin-bottom:0.35rem; font-size:0.9rem;">Contact Phone / WhatsApp (Optional)</label>
          <input type="text" name="member_phone" value="{{ tshirt.member_phone if tshirt else '' }}" placeholder="+91 98765 43210" style="width:100%; padding:0.7rem; border-radius:8px; border:1px solid var(--border); font-size:0.95rem;">
        </div>
        <div>
          <label style="display:block; font-weight:700; margin-bottom:0.35rem; font-size:0.9rem;">Profile Accent Color</label>
          <input type="color" name="accent_color" value="{{ tshirt.accent_color if tshirt else '#2563eb' }}" style="width:100%; height:45px; border-radius:8px; border:1px solid var(--border); cursor:pointer;">
        </div>
      </div>

      <div style="display:flex; justify-content:flex-end; gap:0.75rem;">
        <a href="{{ url_for('admin_dashboard') }}" class="btn btn-secondary">Cancel</a>
        <button type="submit" class="btn btn-primary">
          {{ 'Save Changes' if tshirt else 'Create T-Shirt & Generate QR' }}
        </button>
      </div>
    </form>
  </div>
</div>
{% endblock %}
"""

ADMIN_LOGIN_TEMPLATE = """
{% extends "base" %}
{% block title %}Admin Sign In | Association T-Shirts{% endblock %}
{% block content %}
<div style="max-width: 400px; margin: 3rem auto;">
  <div class="card" style="text-align:center;">
    <div style="font-size: 2.75rem; margin-bottom: 0.5rem;">👕🔐</div>
    <h1 style="font-size: 1.45rem; font-weight:800; margin-bottom: 0.35rem;">Association Admin Login</h1>
    <p style="color:var(--text-muted); font-size:0.88rem; margin-bottom: 1.5rem;">
      Enter the administrative password to push live broadcasts and manage member T-shirts.
    </p>

    <form method="POST">
      <div style="margin-bottom: 1.25rem; text-align:left;">
        <label style="display:block; font-weight:700; margin-bottom:0.35rem; font-size:0.88rem;">Admin Password</label>
        <input type="password" name="password" required autofocus placeholder="Enter password..." style="width:100%; padding:0.7rem; border-radius:8px; border:1px solid var(--border); font-size:0.95rem;">
      </div>
      <button type="submit" class="btn btn-primary" style="width:100%; padding:0.75rem;">Sign In</button>
    </form>
  </div>
</div>
{% endblock %}
"""

PRINT_CARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Apparel Print Sheet | {{ tshirt.member_name }}</title>
  <style>
    @page { size: A4 portrait; margin: 1.2cm; }
    * { box-sizing: border-box; margin:0; padding:0; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; color: #0f172a; padding: 2rem; background: #f8fafc; }
    .print-sheet {
      max-width: 720px; margin: 0 auto; background: #ffffff; border: 2px dashed #94a3b8; border-radius: 16px; padding: 2.25rem; text-align: center;
      box-shadow: 0 4px 12px rgba(0,0,0,0.03);
    }
    .header-badge {
      display: inline-block; background: #0f172a; color: white; padding: 0.35rem 1rem; border-radius: 999px;
      font-size: 0.82rem; font-weight: 700; text-transform: uppercase; margin-bottom: 0.85rem; letter-spacing: 0.5px;
    }
    .codes-container {
      display: flex; justify-content: center; align-items: center; gap: 1.5rem; margin: 1.25rem 0; flex-wrap: wrap;
    }
    .code-box {
      background: #ffffff; border: 2px solid #0f172a; border-radius: 12px; padding: 1.25rem; display: inline-flex; flex-direction: column; align-items: center; justify-content: center;
      transition: all 0.2s ease;
    }
    .code-box.hidden { display: none !important; }
    .code-title {
      font-size: 0.78rem; font-weight: 800; text-transform: uppercase; color: #475569; letter-spacing: 0.5px; margin-bottom: 0.75rem;
    }
    .qr-frame img { display: block; width: 220px; height: 220px; }
    .barcode-frame img { display: block; max-width: 300px; height: auto; max-height: 130px; }
    .btn { display: inline-block; padding: 0.55rem 1.1rem; background: #2563eb; color: white; text-decoration: none; border-radius: 8px; font-weight: 700; border: none; cursor: pointer; font-size: 0.85rem; }
    .btn-secondary { background: #475569; }
    .view-toggle-btn {
      background: #e2e8f0; color: #334155; border: 1px solid #cbd5e1; padding: 0.45rem 0.95rem; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 0.85rem;
    }
    .view-toggle-btn.active {
      background: #0f172a; color: #ffffff; border-color: #0f172a;
    }
    @media print {
      .no-print { display: none !important; }
      body { padding: 0; background: #ffffff; }
      .print-sheet { border: 2px dashed #64748b; box-shadow: none; padding: 1.2cm; max-width: 100%; }
    }
  </style>
</head>
<body>
  <div class="no-print" style="max-width:720px; margin:0 auto 1.5rem; text-align:center;">
    <div style="display:flex; justify-content:center; align-items:center; gap:0.5rem; margin-bottom:1rem; flex-wrap:wrap;">
      <span style="font-weight:700; font-size:0.9rem; color:#475569; margin-right:0.5rem;">Select Code to Print:</span>
      <button class="view-toggle-btn active" id="btn-both" onclick="setMode('both')">🔘 Both (QR + Barcode)</button>
      <button class="view-toggle-btn" id="btn-qr" onclick="setMode('qr')">📱 QR Code Only</button>
      <button class="view-toggle-btn" id="btn-barcode" onclick="setMode('barcode')">🏷️ Barcode Only</button>
    </div>

    <div style="display:flex; justify-content:center; gap:0.4rem; flex-wrap:wrap;">
      <button class="btn" onclick="window.print()">🖨️ Print Spec Sheet</button>
      <a href="{{ url_for('qr_png', slug=tshirt.slug, download=1) }}" class="btn" style="background:#0f172a;">⬇️ QR (PNG)</a>
      <a href="{{ url_for('qr_svg', slug=tshirt.slug, download=1) }}" class="btn" style="background:#059669;">⬇️ QR (Vector SVG)</a>
      <a href="{{ url_for('barcode_png', slug=tshirt.slug, download=1) }}" class="btn" style="background:#4338ca;">⬇️ Barcode (PNG)</a>
      <a href="{{ url_for('barcode_svg', slug=tshirt.slug, download=1) }}" class="btn" style="background:#7c3aed;">⬇️ Barcode (Vector SVG)</a>
    </div>
  </div>

  <div class="print-sheet">
    <div class="header-badge">Association Official Apparel Master</div>
    <h1 style="font-size:1.85rem; font-weight:800; color:#0f172a;">{{ tshirt.member_name }}</h1>
    <p style="color:#64748b; font-size:1rem; margin-top:0.25rem;">{{ tshirt.member_role }} &bull; Permanent Apparel Identification</p>

    <div class="codes-container" id="codes-wrap">
      <div class="code-box qr-frame" id="box-qr">
        <div class="code-title">2D Dynamic QR Code</div>
        <img src="{{ url_for('qr_png', slug=tshirt.slug, size=1000) }}" alt="QR Code">
      </div>

      <div class="code-box barcode-frame" id="box-barcode">
        <div class="code-title">1D Code 128 Barcode</div>
        <img src="{{ url_for('barcode_png', slug=tshirt.slug) }}" alt="Barcode">
      </div>
    </div>

    <div style="font-size:0.82rem; text-transform:uppercase; color:#64748b; font-weight:700;">Permanent Scan Target URL</div>
    <div style="font-family:monospace; font-size:1.05rem; font-weight:700; color:#2563eb; background:#f1f5f9; padding:0.5rem 1rem; border-radius:8px; display:inline-block; margin:0.5rem 0 1.25rem; word-break:break-all;">
      {{ target_url }}
    </div>

    <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.75rem; text-align:left; background:#f8fafc; padding:1rem; border-radius:8px; border:1px solid #e2e8f0; font-size:0.85rem;">
      <div><strong>Member ID:</strong> {{ tshirt.id }}</div>
      <div><strong>Member Slug:</strong> {{ tshirt.slug }}</div>
      <div><strong>QR Error Recovery:</strong> Level H (30% Fabric Damage Tolerance)</div>
      <div><strong>Barcode Standard:</strong> Code 128 (Universal 1D/2D scanner compliant)</div>
      <div><strong>Quiet Zone:</strong> Safety margin included on both codes</div>
    </div>
  </div>

  <script>
    function setMode(mode) {
      const qrBox = document.getElementById('box-qr');
      const bcBox = document.getElementById('box-barcode');
      const btnBoth = document.getElementById('btn-both');
      const btnQr = document.getElementById('btn-qr');
      const btnBc = document.getElementById('btn-barcode');

      [btnBoth, btnQr, btnBc].forEach(b => b.classList.remove('active'));

      if (mode === 'both') {
        qrBox.classList.remove('hidden');
        bcBox.classList.remove('hidden');
        btnBoth.classList.add('active');
      } else if (mode === 'qr') {
        qrBox.classList.remove('hidden');
        bcBox.classList.add('hidden');
        btnQr.classList.add('active');
      } else if (mode === 'barcode') {
        qrBox.classList.add('hidden');
        bcBox.classList.remove('hidden');
        btnBc.classList.add('active');
      }
    }
  </script>
</body>
</html>
"""

# -----------------------------------------------------------------------------
# Template Renderer Helper
# -----------------------------------------------------------------------------
TEMPLATES_MAP = {
    "base": BASE_LAYOUT,
    "base.html": BASE_LAYOUT,
    "scan.html": SCAN_TEMPLATE,
    "admin_dashboard.html": ADMIN_DASHBOARD_TEMPLATE,
    "admin_edit_member.html": ADMIN_EDIT_MEMBER_TEMPLATE,
    "admin_login.html": ADMIN_LOGIN_TEMPLATE,
    "print_card.html": PRINT_CARD_TEMPLATE,
}

app.jinja_loader = jinja2.ChoiceLoader([
    app.jinja_loader,
    jinja2.DictLoader(TEMPLATES_MAP),
])

def render_view(template_name, **context):
    context.setdefault("config_base_url", app.config["BASE_URL"])
    return render_template(template_name, **context)


# -----------------------------------------------------------------------------
# Public Scanning Route (Dual-Message & Scheduled Expiration Logic)
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    if session.get("is_admin"):
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("admin_login"))


@app.route("/t/<slug>")
def scan_tshirt(slug):
    """
    Public mobile scan page.
    Implements:
    1. Member personal message lookup
    2. Global admin broadcast lookup
    3. Automated expiration check (now > expires_at => revert to member message)
    4. Mode check: 'both', 'admin_only', or 'member_only'
    """
    tshirt = TShirt.query.filter_by(slug=slug).first_or_404()

    # Increment scan count
    tshirt.scan_count = (tshirt.scan_count or 0) + 1
    db.session.commit()

    broadcast = GlobalBroadcast.query.first()
    show_broadcast = False
    broadcast_mode = "both"

    if broadcast:
        broadcast_mode = broadcast.mode
        # Check if broadcast is live and within scheduled ending time
        if broadcast.is_currently_live() and broadcast_mode != "member_only":
            show_broadcast = True

    member_msg_html = render_markdown_or_safe_html(tshirt.member_message)
    broadcast_msg_html = render_markdown_or_safe_html(broadcast.message if broadcast else "")

    return render_view(
        "scan.html",
        tshirt=tshirt,
        broadcast=broadcast,
        show_broadcast=show_broadcast,
        broadcast_mode=broadcast_mode,
        member_msg_html=member_msg_html,
        broadcast_msg_html=broadcast_msg_html,
    )


# -----------------------------------------------------------------------------
# Print-Ready QR Code Generation Endpoints
# -----------------------------------------------------------------------------
@app.route("/t/<slug>/qr.png")
def qr_png(slug):
    tshirt = TShirt.query.filter_by(slug=slug).first_or_404()
    target_url = f"{app.config['BASE_URL']}/t/{tshirt.slug}"

    if not HAS_QRCODE:
        return "qrcode library missing. Please install qrcode[pil]", 500

    size_param = request.args.get("size", default=600, type=int)
    box_size = max(4, min(40, size_param // 30))

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # 30% fabric damage recovery
        box_size=box_size,
        border=4,
    )
    qr.add_data(target_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG", dpi=(300, 300))
    buffer.seek(0)

    download = request.args.get("download", "0") == "1"
    return send_file(
        buffer,
        mimetype="image/png",
        as_attachment=download,
        download_name=f"{tshirt.slug}-qr-300dpi.png",
    )


@app.route("/t/<slug>/qr.svg")
def qr_svg(slug):
    tshirt = TShirt.query.filter_by(slug=slug).first_or_404()
    target_url = f"{app.config['BASE_URL']}/t/{tshirt.slug}"

    if not HAS_QRCODE:
        return "qrcode library missing. Please install qrcode[pil]", 500

    factory = qrcode.image.svg.SvgPathImage
    img = qrcode.make(
        target_url,
        image_factory=factory,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        border=4,
    )
    buffer = io.BytesIO()
    img.save(buffer)
    buffer.seek(0)

    download = request.args.get("download", "0") == "1"
    resp = Response(buffer.getvalue(), mimetype="image/svg+xml")
    if download:
        resp.headers["Content-Disposition"] = f'attachment; filename="{tshirt.slug}-vector.svg"'
    return resp


@app.route("/t/<slug>/barcode.png")
def barcode_png(slug):
    tshirt = TShirt.query.filter_by(slug=slug).first_or_404()
    if not HAS_BARCODE:
        return "python-barcode library missing. Please install python-barcode", 500

    data_type = request.args.get("data", "url")
    if data_type == "slug":
        data_to_encode = tshirt.slug
    else:
        data_to_encode = f"{app.config['BASE_URL']}/t/{tshirt.slug}"

    try:
        code_class = barcode.get_barcode_class("code128")
        bc = code_class(data_to_encode, writer=ImageWriter())
        buffer = io.BytesIO()
        bc.write(buffer, options={
            "module_width": 0.25,
            "module_height": 14.0,
            "font_size": 10,
            "text_distance": 4.0,
            "quiet_zone": 3.0,
            "write_text": True,
        })
        buffer.seek(0)
    except Exception as e:
        return f"Failed to generate barcode: {str(e)}", 500

    download = request.args.get("download", "0") == "1"
    return send_file(
        buffer,
        mimetype="image/png",
        as_attachment=download,
        download_name=f"{tshirt.slug}-barcode.png",
    )


@app.route("/t/<slug>/barcode.svg")
def barcode_svg(slug):
    tshirt = TShirt.query.filter_by(slug=slug).first_or_404()
    if not HAS_BARCODE:
        return "python-barcode library missing. Please install python-barcode", 500

    data_type = request.args.get("data", "url")
    if data_type == "slug":
        data_to_encode = tshirt.slug
    else:
        data_to_encode = f"{app.config['BASE_URL']}/t/{tshirt.slug}"

    try:
        code_class = barcode.get_barcode_class("code128")
        bc = code_class(data_to_encode, writer=SVGWriter())
        buffer = io.BytesIO()
        bc.write(buffer, options={
            "module_width": 0.25,
            "module_height": 14.0,
            "font_size": 10,
            "text_distance": 4.0,
            "quiet_zone": 3.0,
            "write_text": True,
        })
        buffer.seek(0)
    except Exception as e:
        return f"Failed to generate barcode SVG: {str(e)}", 500

    download = request.args.get("download", "0") == "1"
    resp = Response(buffer.getvalue(), mimetype="image/svg+xml")
    if download:
        resp.headers["Content-Disposition"] = f'attachment; filename="{tshirt.slug}-barcode.svg"'
    return resp


# -----------------------------------------------------------------------------
# Admin Control Panel Routes
# -----------------------------------------------------------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("is_admin"):
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        password = request.form.get("password", "")
        if password == app.config["ADMIN_PASSWORD"]:
            session["is_admin"] = True
            flash("Welcome to the Association Admin Control Center.", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Invalid admin password. Please try again.", "danger")

    return render_view("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    flash("Signed out successfully.", "success")
    return redirect(url_for("admin_login"))


@app.route("/admin")
@login_required
def admin_dashboard():
    broadcast = GlobalBroadcast.query.first()
    tshirts = TShirt.query.order_by(TShirt.created_at.desc()).all()

    is_live = broadcast.is_currently_live() if broadcast else False
    expiry_str = broadcast.expires_at.strftime("%Y-%m-%dT%H:%M") if (broadcast and broadcast.expires_at) else ""

    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    is_postgres = "postgresql" in db_uri
    if is_postgres:
        try:
            import urllib.parse
            parsed_host = urllib.parse.urlparse(db_uri).hostname or "cloud"
        except Exception:
            parsed_host = "cloud"
        db_backend = f"Neon PostgreSQL ({parsed_host})" if "neon" in db_uri else f"Cloud PostgreSQL ({parsed_host})"
    else:
        db_backend = "SQLite (Local / Ephemeral)"

    return render_view(
        "admin_dashboard.html",
        broadcast=broadcast,
        is_broadcast_live=is_live,
        expiry_str=expiry_str,
        tshirts=tshirts,
        is_postgres=is_postgres,
        db_backend=db_backend,
    )


@app.route("/admin/broadcast/update", methods=["POST"])
@login_required
def admin_update_broadcast():
    """Admin updates the global broadcast, display mode, and scheduled ending time."""
    broadcast = GlobalBroadcast.query.first()
    if not broadcast:
        broadcast = GlobalBroadcast()
        db.session.add(broadcast)

    broadcast.title = request.form.get("title", "Association Announcement").strip()
    broadcast.message = request.form.get("message", "").strip()
    broadcast.mode = request.form.get("mode", "both")
    broadcast.is_active = request.form.get("is_active") == "1"

    expires_at_raw = request.form.get("expires_at", "").strip()
    if expires_at_raw:
        try:
            # Parse datetime-local string (YYYY-MM-DDTHH:MM)
            broadcast.expires_at = datetime.fromisoformat(expires_at_raw)
        except ValueError:
            broadcast.expires_at = None
    else:
        broadcast.expires_at = None

    broadcast.updated_at = datetime.utcnow()
    db.session.commit()

    flash("Global Association Broadcast updated successfully! All T-shirts reflect this setting.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/tshirts/new", methods=["GET", "POST"])
@login_required
def admin_new_tshirt():
    if request.method == "POST":
        member_name = request.form.get("member_name", "").strip()
        member_role = request.form.get("member_role", "Member").strip()
        slug_raw = request.form.get("slug", "").strip()
        member_message = request.form.get("member_message", "").strip()
        member_phone = request.form.get("member_phone", "").strip()
        accent_color = request.form.get("accent_color", "#2563eb").strip()

        if not member_name:
            flash("Member name is required.", "danger")
            return redirect(request.url)

        slug = re.sub(r"[^a-zA-Z0-9-_]", "-", slug_raw).strip("-").lower() if slug_raw else generate_unique_slug()

        if TShirt.query.filter_by(slug=slug).first():
            flash(f"Slug '{slug}' is already taken. Please choose another.", "danger")
            return redirect(request.url)

        custom_id = request.form.get("custom_id", "").strip().upper()
        if custom_id:
            if len(custom_id) > 10:
                flash("Custom ID cannot exceed 10 characters.", "danger")
                return redirect(request.url)
            if TShirt.query.get(custom_id):
                flash(f"ID '{custom_id}' is already taken. Please choose another.", "danger")
                return redirect(request.url)
            tshirt_id = custom_id
        else:
            tshirt_id = generate_unique_tshirt_id()

        new_shirt = TShirt(
            id=tshirt_id,
            member_name=member_name,
            member_role=member_role,
            slug=slug,
            member_message=member_message or "Proud member of this association!",
            member_phone=member_phone or None,
            accent_color=accent_color or "#2563eb",
        )
        db.session.add(new_shirt)
        db.session.commit()

        flash(f"T-shirt registered for {member_name} (ID: {tshirt_id})! Permanent QR & Barcode are ready for printing.", "success")
        return redirect(url_for("admin_dashboard"))

    default_slug = generate_unique_slug()
    return render_view("admin_edit_member.html", tshirt=None, default_slug=default_slug)


@app.route("/admin/tshirts/<id>/edit", methods=["GET", "POST"])
@login_required
def admin_edit_tshirt(id):
    tshirt = TShirt.query.get_or_404(id)

    if request.method == "POST":
        tshirt.member_name = request.form.get("member_name", tshirt.member_name).strip()
        tshirt.member_role = request.form.get("member_role", tshirt.member_role).strip()
        tshirt.member_message = request.form.get("member_message", tshirt.member_message).strip()
        tshirt.member_phone = request.form.get("member_phone", "").strip() or None
        tshirt.accent_color = request.form.get("accent_color", tshirt.accent_color).strip()
        tshirt.updated_at = datetime.utcnow()

        db.session.commit()
        flash(f"Details for {tshirt.member_name} updated successfully!", "success")
        return redirect(url_for("admin_dashboard"))

    return render_view("admin_edit_member.html", tshirt=tshirt)


@app.route("/admin/tshirts/<id>/delete", methods=["POST"])
@login_required
def admin_delete_tshirt(id):
    tshirt = TShirt.query.get_or_404(id)
    name = tshirt.member_name
    db.session.delete(tshirt)
    db.session.commit()
    flash(f"Member T-Shirt for '{name}' removed.", "warning")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/tshirts/<id>/print-card")
@login_required
def admin_print_card(id):
    tshirt = TShirt.query.get_or_404(id)
    target_url = f"{app.config['BASE_URL']}/t/{tshirt.slug}"
    return render_view("print_card.html", tshirt=tshirt, target_url=target_url)


# -----------------------------------------------------------------------------
# Database Bootstrap
# -----------------------------------------------------------------------------
with app.app_context():
    db.create_all()
    # Initialize default broadcast if not present
    if not GlobalBroadcast.query.first():
        broadcast = GlobalBroadcast(
            title="Association Welcome & Community Drive",
            message="Welcome! Scan any of our official association T-shirts to stay updated with our latest social initiatives and meetings.",
            mode="both",
            is_active=True,
        )
        db.session.add(broadcast)

    # Initialize demo member T-shirt if empty
    if not TShirt.query.first():
        demo_member = TShirt(
            id="TSH0000001",
            member_name="Rajesh Sharma",
            member_role="Youth Coordinator",
            slug="rajesh-2026",
            member_message="Namaste! I lead youth engagement and volunteer activities for our association in Rajasthan. Connect with me anytime!",
            member_phone="+91 98765 43210",
            accent_color="#2563eb",
        )
        db.session.add(demo_member)
    db.session.commit()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)