from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db
from app.models.mixins import TimestampMixin


class Role(db.Model, TimestampMixin):
    """
    Roles: super_admin, tournament_manager, moderator, finance_manager, player
    Stored in DB (not hard-coded) so permissions stay configurable.
    """
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(255))

    users = db.relationship("User", backref="role", lazy="dynamic")

    # Well-known role slugs used throughout the app for RBAC checks
    SUPER_ADMIN = "super_admin"
    TOURNAMENT_MANAGER = "tournament_manager"
    MODERATOR = "moderator"
    FINANCE_MANAGER = "finance_manager"
    PLAYER = "player"

    ADMIN_ROLES = {SUPER_ADMIN, TOURNAMENT_MANAGER, MODERATOR, FINANCE_MANAGER}

    def __repr__(self):
        return f"<Role {self.name}>"


class User(db.Model, UserMixin, TimestampMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)

    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False)

    avatar_url = db.Column(db.String(255), default="default_avatar.png")
    is_active_account = db.Column(db.Boolean, default=True, nullable=False)
    is_email_verified = db.Column(db.Boolean, default=False, nullable=False)

    failed_login_attempts = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)
    last_login_at = db.Column(db.DateTime, nullable=True)
    last_login_ip = db.Column(db.String(45), nullable=True)

    password_reset_token = db.Column(db.String(255), nullable=True)
    password_reset_expires = db.Column(db.DateTime, nullable=True)

    # Virtual Coins & Winnings Balance
    coins_balance = db.Column(db.Integer, default=0, nullable=False)
    winnings_balance = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)

    # Relationships
    profile = db.relationship(
        "PlayerProfile", backref="user", uselist=False, cascade="all, delete-orphan"
    )
    team_memberships = db.relationship(
        "TeamMember", backref="user", lazy="dynamic", cascade="all, delete-orphan"
    )
    notifications = db.relationship(
        "Notification", backref="user", lazy="dynamic", cascade="all, delete-orphan"
    )
    wallet = db.relationship(
        "Wallet", backref="user", uselist=False, cascade="all, delete-orphan"
    )

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def get_wallet(self):
        from app.models.wallet import Wallet
        if not self.wallet:
            w = Wallet(user_id=self.id)
            db.session.add(w)
            db.session.commit()
            return w
        return self.wallet

    @property
    def wallet_balance(self) -> float:
        from app.models.wallet import Wallet
        w = Wallet.query.filter_by(user_id=self.id).first()
        return float(w.total_balance) if w else 0.0

    # ---------- Password helpers ----------
    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    # ---------- RBAC helpers ----------
    @property
    def role_name(self) -> str:
        return self.role.name if self.role else ""

    def has_role(self, *role_names) -> bool:
        return self.role_name in role_names

    def is_admin(self) -> bool:
        return self.role_name in Role.ADMIN_ROLES

    def is_super_admin(self) -> bool:
        return self.role_name == Role.SUPER_ADMIN

    # Flask-Login override: block disabled / locked accounts
    @property
    def is_active(self):
        return self.is_active_account

    def __repr__(self):
        return f"<User {self.username}>"
