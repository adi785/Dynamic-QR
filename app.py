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
    has_request_context,
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
    from PIL import Image, ImageDraw, ImageFont
    HAS_QRCODE = True
    HAS_PIL = True
except ImportError:
    HAS_QRCODE = False
    HAS_PIL = False

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


def get_base_url():
    """Finds the effective public base URL, dynamically preferring request.host_url when available."""
    if os.environ.get("BASE_URL"):
        return os.environ.get("BASE_URL").rstrip("/")
    if os.environ.get("RENDER_EXTERNAL_URL"):
        return os.environ.get("RENDER_EXTERNAL_URL").rstrip("/")
    try:
        if has_request_context() and request.host_url:
            return request.host_url.rstrip("/")
    except Exception:
        pass
    return app.config.get("BASE_URL", "http://127.0.0.1:5000").rstrip("/")

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
        "config_base_url": get_base_url(),
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
    target_url = f"{get_base_url()}/t/{tshirt.slug}"

    if not HAS_QRCODE:
        return "qrcode library missing. Please install qrcode[pil]", 500

    size_param = request.args.get("size", default=600, type=int)
    box_size = max(4, min(40, size_param // 30))
    dark_mode = request.args.get("dark", "0") == "1" or request.args.get("invert", "0") == "1"

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # 30% fabric damage recovery
        box_size=box_size,
        border=4,
    )
    qr.add_data(target_url)
    qr.make(fit=True)

    # Standard high-contrast black on white or inverted white on black for dark apparel
    fill_col = "white" if dark_mode else "black"
    back_col = "black" if dark_mode else "white"
    img = qr.make_image(fill_color=fill_col, back_color=back_col)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG", dpi=(300, 300))
    buffer.seek(0)

    download = request.args.get("download", "0") == "1"
    suffix = "-dark" if dark_mode else ""
    return send_file(
        buffer,
        mimetype="image/png",
        as_attachment=download,
        download_name=f"{tshirt.slug}-qr{suffix}-300dpi.png",
    )


@app.route("/t/<slug>/qr.svg")
def qr_svg(slug):
    tshirt = TShirt.query.filter_by(slug=slug).first_or_404()
    target_url = f"{get_base_url()}/t/{tshirt.slug}"

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


@app.route("/t/<slug>/badge.png")
def badge_png(slug):
    tshirt = TShirt.query.filter_by(slug=slug).first_or_404()
    target_url = f"{get_base_url()}/t/{tshirt.slug}"

    if not HAS_QRCODE or not HAS_PIL:
        return "qrcode or Pillow library missing", 500

    # High-resolution scannable QR Code
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=2,
    )
    qr.add_data(target_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qr_size = 350
    qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.LANCZOS)

    # Canvas dimensions: 1100 x 440 (2.5 : 1 horizontal rectangular aspect ratio)
    width, height = 1100, 440
    badge = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(badge)
    accent_col = tshirt.accent_color or "#2563eb"

    # Cross-platform fonts
    font_brand = font_name = font_role = font_id = font_cta = None
    for p in [
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ]:
        if os.path.exists(p):
            try:
                font_brand = ImageFont.truetype(p, 24)
                font_name = ImageFont.truetype(p, 44)
                font_role = ImageFont.truetype(p, 28)
                font_id = ImageFont.truetype(p, 24)
                font_cta = ImageFont.truetype(p, 22)
                break
            except Exception:
                pass
    if not font_brand:
        font_brand = font_name = font_role = font_id = font_cta = ImageFont.load_default()

    # Outer rounded border
    draw.rounded_rectangle([12, 12, width - 12, height - 12], radius=24, outline="#0f172a", width=5)
    # Colored top accent strip
    draw.rounded_rectangle([12, 12, width - 12, 26], radius=6, fill=accent_col)

    # Paste QR Code on left
    badge.paste(qr_img, (45, 45))

    # Vertical divider line
    draw.line([(430, 48), (430, 392)], fill="#cbd5e1", width=3)

    # Member information on right
    draw.text((465, 55), "JU MAKERSPACE - OFFICIAL APPAREL", fill=accent_col, font=font_brand)
    draw.text((465, 105), tshirt.member_name, fill="#0f172a", font=font_name)
    draw.text((465, 180), f"Role: {tshirt.member_role}", fill="#475569", font=font_role)
    draw.text((465, 235), f"Member ID: {tshirt.id}", fill="#64748b", font=font_id)

    # Call to action
    draw.rounded_rectangle([465, 305, 1045, 380], radius=12, fill="#f1f5f9", outline="#cbd5e1", width=2)
    draw.text((490, 328), "Scan 2D Code to View Live Profile & Notices", fill="#1d4ed8", font=font_cta)

    buffer = io.BytesIO()
    badge.save(buffer, format="PNG", dpi=(300, 300))
    buffer.seek(0)

    download = request.args.get("download", "0") == "1"
    return send_file(
        buffer,
        mimetype="image/png",
        as_attachment=download,
        download_name=f"{tshirt.slug}-rectangular-badge-300dpi.png",
    )


@app.route("/t/<slug>/tech-badge.png")
def tech_badge_png(slug):
    tshirt = TShirt.query.filter_by(slug=slug).first_or_404()
    target_url = f"{get_base_url()}/t/{tshirt.slug}"

    if not HAS_QRCODE or not HAS_PIL:
        return "qrcode or Pillow library missing", 500

    # 3.44 : 1 aspect ratio matching the barcode spot (600 x 175 px @ 300 DPI)
    width, height = 600, 175
    transparent = request.args.get("transparent", "0") == "1"
    bg_color = (0, 0, 0, 0) if transparent else (0, 0, 0, 255)
    badge = Image.new("RGBA", (width, height), color=bg_color)
    draw = ImageDraw.Draw(badge)

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=1,
    )
    qr.add_data(target_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="white", back_color="black").convert("RGBA")
    qr_img = qr_img.resize((155, 155), Image.Resampling.LANCZOS)
    badge.paste(qr_img, (10, 10))

    # Divider
    draw.line([(180, 15), (180, 160)], fill=(120, 120, 120, 255), width=2)

    # Cross-platform fonts
    font_title = font_sub = font_cta = None
    for p in [
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ]:
        if os.path.exists(p):
            try:
                font_title = ImageFont.truetype(p, 30)
                font_sub = ImageFont.truetype(p, 22)
                font_cta = ImageFont.truetype(p, 18)
                break
            except Exception:
                pass
    if not font_title:
        font_title = font_sub = font_cta = ImageFont.load_default()

    draw.text((195, 20), tshirt.id or tshirt.slug, fill=(255, 255, 255, 255), font=font_title)
    draw.text((195, 68), (tshirt.slug or "").replace("_", " ").upper(), fill=(180, 180, 180, 255), font=font_sub)
    accent = tshirt.accent_color or "#eb5f24"
    draw.rounded_rectangle([195, 115, 420, 155], radius=6, fill=accent)
    draw.text((215, 123), "SCAN PROFILE", fill=(255, 255, 255, 255), font=font_cta)

    buffer = io.BytesIO()
    badge.save(buffer, format="PNG", dpi=(300, 300))
    buffer.seek(0)

    download = request.args.get("download", "0") == "1"
    return send_file(
        buffer,
        mimetype="image/png",
        as_attachment=download,
        download_name=f"{tshirt.slug}-tech-barcode-badge-300dpi.png",
    )


@app.route("/t/<slug>/barcode.png")
def barcode_png(slug):
    tshirt = TShirt.query.filter_by(slug=slug).first_or_404()
    if not HAS_BARCODE:
        return "python-barcode library missing. Please install python-barcode", 500

    data_type = request.args.get("data", "url").lower()
    if data_type == "slug":
        data_to_encode = tshirt.slug
    elif data_type == "id":
        data_to_encode = tshirt.id or tshirt.slug
    else:
        # Default: Link to their member details page
        data_to_encode = f"{get_base_url()}/t/{tshirt.slug}"

    try:
        code_class = barcode.get_barcode_class("code128")
        bc = code_class(data_to_encode, writer=ImageWriter())
        buffer = io.BytesIO()
        # Render barcode bars without text overlapping
        bc.write(buffer, options={
            "module_width": 0.55,      # 0.55 mm
            "module_height": 28.0,     # 28.0 mm
            "quiet_zone": 8.5,         # 8.5 mm
            "write_text": False,
        })
        buffer.seek(0)
        im_bars = Image.open(buffer)
        bw, bh = im_bars.size

        # Find best TrueType font
        font_path = None
        for p in [
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        ]:
            if os.path.exists(p):
                font_path = p
                break

        draw_temp = ImageDraw.Draw(im_bars)
        target_tw = bw * 0.88
        best_font = None
        best_tw = 0
        best_th = 0
        best_bbox = (0, 0, 400, 30)

        if font_path:
            for fs in range(160, 20, -2):
                f = ImageFont.truetype(font_path, fs)
                bbox = draw_temp.textbbox((0, 0), data_to_encode, font=f)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                if tw <= target_tw:
                    best_font = f
                    best_tw = tw
                    best_th = th
                    best_bbox = bbox
                    break

        if not best_font:
            best_font = ImageFont.load_default()
            best_tw, best_th = 400, 30
            best_bbox = (0, 0, 400, 30)

        # Locate exact lowest black bar pixel to set a clean, lowered gap
        lowest_bar_y = bh
        for y in range(bh - 1, -1, -1):
            if any(im_bars.getpixel((x, y)) != (255, 255, 255) for x in range(bw)):
                lowest_bar_y = y
                break

        # Lowered, tight gap between barcode bars and text (default 18px)
        desired_gap = max(8, min(60, request.args.get("gap", 18, type=int)))
        ty = lowest_bar_y + desired_gap - best_bbox[1]
        bottom_pad = max(18, int(best_th * 0.2))
        total_h = ty + best_bbox[3] + bottom_pad

        canvas = Image.new("RGB", (bw, total_h), "white")
        canvas.paste(im_bars, (0, 0))

        draw = ImageDraw.Draw(canvas)
        tx = (bw - best_tw) // 2 - best_bbox[0]
        draw.text((tx, ty), data_to_encode, fill="black", font=best_font)

        out_buffer = io.BytesIO()
        canvas.save(out_buffer, format="PNG", dpi=(300, 300))
        out_buffer.seek(0)
    except Exception as e:
        return f"Failed to generate barcode: {str(e)}", 500

    download = request.args.get("download", "0") == "1"
    return send_file(
        out_buffer,
        mimetype="image/png",
        as_attachment=download,
        download_name=f"{tshirt.slug}-barcode.png",
    )


@app.route("/t/<slug>/barcode.svg")
def barcode_svg(slug):
    tshirt = TShirt.query.filter_by(slug=slug).first_or_404()
    if not HAS_BARCODE:
        return "python-barcode library missing. Please install python-barcode", 500

    data_type = request.args.get("data", "url").lower()
    if data_type == "slug":
        data_to_encode = tshirt.slug
    elif data_type == "id":
        data_to_encode = tshirt.id or tshirt.slug
    else:
        # Default: Link to their member details page
        data_to_encode = f"{get_base_url()}/t/{tshirt.slug}"

    try:
        code_class = barcode.get_barcode_class("code128")
        bc = code_class(data_to_encode, writer=SVGWriter())
        buffer = io.BytesIO()
        bc.write(buffer, options={
            "module_width": 0.55,      # 0.55 mm
            "module_height": 28.0,     # 28.0 mm
            "quiet_zone": 8.5,         # 8.5 mm
            "font_size": 11,           # Clean proportional size in SVG coordinates
            "text_distance": 5.0,
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

    return render_template(
        "admin_dashboard.html",
        broadcast=broadcast,
        is_broadcast_live=is_live,
        expiry_str=expiry_str,
        tshirts=tshirts,
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
        member_email = request.form.get("member_email", "").strip()
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
            member_email=member_email or None,
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
        tshirt.member_email = request.form.get("member_email", "").strip() or None
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
    target_url = f"{get_base_url()}/t/{tshirt.slug}"
    return render_template("print_card.html", tshirt=tshirt, target_url=target_url)


@app.route("/admin/sync-roster", methods=["GET", "POST"])
@login_required
def admin_sync_roster():
    try:
        from roster_data import seed_roster_into_db
        created, updated = seed_roster_into_db(db, TShirt, generate_unique_tshirt_id)
        flash(f"Successfully synced roster with database! ({created} created, {updated} updated — 165 members active)", "success")
    except Exception as e:
        flash(f"Sync error: {e}", "danger")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/download-all-qrs")
@login_required
def admin_download_all_qrs():
    import zipfile
    base_url = get_base_url()
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for t in TShirt.query.order_by(TShirt.member_name).all():
            target_url = f"{base_url}/t/{t.slug}"
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=10,
                border=2,
            )
            qr.add_data(target_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
            img_io = io.BytesIO()
            img.save(img_io, format="PNG")
            img_io.seek(0)
            z.writestr(f"{t.slug}_qr.png", img_io.getvalue())
    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name="all_member_qr_codes.zip",
    )


# -----------------------------------------------------------------------------
# Database Bootstrap
# -----------------------------------------------------------------------------
with app.app_context():
    try:
        db.create_all()
    except Exception as e:
        print(f"db.create_all note: {e}", flush=True)

    # Safe schema migration for newly added columns (works on PostgreSQL & SQLite)
    try:
        with db.engine.connect() as conn:
            url_str = str(db.engine.url).lower()
            if "postgresql" in url_str or "postgres" in url_str:
                conn.execute(db.text("ALTER TABLE tshirts ADD COLUMN IF NOT EXISTS member_email VARCHAR(120)"))
            else:
                try:
                    conn.execute(db.text("ALTER TABLE tshirts ADD COLUMN member_email VARCHAR(120)"))
                except Exception:
                    pass
            conn.commit()
    except Exception as e:
        print(f"Column migration note: {e}", flush=True)

    try:
        # Initialize default broadcast if not present
        if not GlobalBroadcast.query.first():
            broadcast = GlobalBroadcast(
                title="JU Makerspace",
                message="Welcome! Scan any of our official Makerspace T-shirts to stay updated with our latest events, initiatives and meetings.",
                mode="both",
                is_active=True,
            )
            db.session.add(broadcast)
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"GlobalBroadcast bootstrap note: {e}", flush=True)

    try:
        from roster_data import seed_roster_into_db
        # Automatically ensure all 165 members are populated in deployed database (Render/Postgres/SQLite)
        if TShirt.query.count() < 165:
            created, updated = seed_roster_into_db(db, TShirt, generate_unique_tshirt_id)
            print(f"Roster bootstrap complete: {created} created, {updated} updated.", flush=True)
    except Exception as e:
        db.session.rollback()
        print(f"Roster bootstrap note: {e}", flush=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
