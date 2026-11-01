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
4. Mode Switching:
   - 'both': Shows Association Announcement on top + Member Profile & Message below.
   - 'admin_only': Admin message takes over full screen.
   - 'member_only': Hides admin broadcast and displays only the T-shirt owner's message.
5. Dual Code Generation: Both 2D QR Code (Level H) and 1D Barcode (Code 128) in PNG & SVG.
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
    request,
    send_file,
    session,
    url_for,
)

# Optional QR code library with high-res PIL and SVG factories
try:
    import qrcode
    import qrcode.image.svg
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False

# Optional Barcode library with PIL and SVG writers
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

# Import models & database
from models import (
    GlobalBroadcast,
    TShirt,
    db,
    generate_unique_slug,
    generate_unique_tshirt_id,
)

# -----------------------------------------------------------------------------
# Configuration & Database Initialization
# -----------------------------------------------------------------------------
app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", secrets.token_hex(32))


def get_database_url():
    """Finds and prepares the database URL, supporting PostgreSQL and SQLite."""
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
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

# Public base domain/URL (crucial for encoding absolute URLs in printable QR codes)
app.config["BASE_URL"] = (
    os.environ.get("BASE_URL")
    or os.environ.get("RENDER_EXTERNAL_URL")
    or "http://127.0.0.1:5000"
).rstrip("/")

# Admin dashboard password
app.config["ADMIN_PASSWORD"] = os.environ.get("ADMIN_PASSWORD", "admin123")

# Initialize database extension with app
db.init_app(app)


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


def render_markdown_or_safe_html(text):
    if HAS_MARKDOWN:
        return markdown.markdown(text, extensions=["extra", "nl2br", "sane_lists"], output_format="html5")
    from markupsafe import escape
    return str(escape(text)).replace("\n", "<br>\n")


@app.context_processor
def inject_globals():
    return {
        "config_base_url": app.config["BASE_URL"],
    }


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

    if broadcast and broadcast.is_currently_live():
        show_broadcast = True
        broadcast_mode = broadcast.mode

    member_msg_html = render_markdown_or_safe_html(tshirt.member_message)
    broadcast_msg_html = render_markdown_or_safe_html(broadcast.message) if broadcast else ""

    return render_template(
        "scan.html",
        tshirt=tshirt,
        broadcast=broadcast,
        show_broadcast=show_broadcast,
        broadcast_mode=broadcast_mode,
        member_msg_html=member_msg_html,
        broadcast_msg_html=broadcast_msg_html,
    )


# -----------------------------------------------------------------------------
# Print-Ready QR & Barcode Generation Endpoints
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

    return render_template("admin_login.html")


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
    is_postgres = "postgresql" in db_uri or "postgres" in db_uri
    if is_postgres:
        try:
            import urllib.parse
            parsed_host = urllib.parse.urlparse(db_uri).hostname or "cloud"
        except Exception:
            parsed_host = "cloud"
        db_backend = f"Neon PostgreSQL ({parsed_host})" if "neon" in db_uri else f"Cloud PostgreSQL ({parsed_host})"
    else:
        db_backend = "SQLite (Local / Ephemeral)"

    return render_template(
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
            broadcast.expires_at = datetime.strptime(expires_at_raw, "%Y-%m-%dT%H:%M")
        except ValueError:
            flash("Invalid date format for scheduled ending time.", "warning")
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
    return render_template("admin_edit_member.html", tshirt=None, default_slug=default_slug)


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

    return render_template("admin_edit_member.html", tshirt=tshirt)


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
    return render_template("print_card.html", tshirt=tshirt, target_url=target_url)


# -----------------------------------------------------------------------------
# Database Bootstrap
# -----------------------------------------------------------------------------
with app.app_context():
    try:
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
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"GlobalBroadcast bootstrap note: {e}", flush=True)

    try:
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
    except Exception as e:
        db.session.rollback()
        print(f"TShirt bootstrap note: {e}", flush=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
