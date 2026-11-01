import secrets
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def generate_unique_tshirt_id():
    """Generates a unique 10-character ID (e.g. 'TS' + 8 hex digits = 10 chars)."""
    while True:
        candidate = f"TS{secrets.token_hex(4).upper()}"
        if not TShirt.query.get(candidate):
            return candidate


def generate_unique_slug(prefix="mem-", length=6):
    """Generates a unique URL slug for mobile QR scans."""
    while True:
        candidate = f"{prefix}{secrets.token_hex(length // 2)}"
        if not TShirt.query.filter_by(slug=candidate).first():
            return candidate


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
            if datetime.utcnow() > self.expires_at:
                return False
        return True


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

