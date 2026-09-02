from datetime import datetime
from app.extensions import db
from app.models.mixins import TimestampMixin


class CoinTopup(db.Model, TimestampMixin):
    """
    CoinTopup model for tracking automated virtual coin top-up orders.
    Statuses supported: PENDING, SUCCESS, FAILED
    """
    __tablename__ = "coin_topups"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    order_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    coins_to_add = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default="PENDING", nullable=False)  # 'PENDING', 'SUCCESS', 'FAILED'
    payment_id = db.Column(db.String(100), nullable=True)

    # Relationships
    user = db.relationship("User", backref=db.backref("coin_topups", lazy="dynamic", cascade="all, delete-orphan"))

    def __repr__(self):
        return f"<CoinTopup Order={self.order_id} User={self.user_id} Coins={self.coins_to_add} Status={self.status}>"
