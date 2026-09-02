from app.extensions import db
from app.models.mixins import TimestampMixin


class Payment(db.Model, TimestampMixin):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.String(100), unique=True, nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey("tournaments.id"), nullable=True)
    registration_id = db.Column(
        db.Integer, db.ForeignKey("tournament_registrations.id"), unique=True, nullable=True
    )

    amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(10), default="INR", nullable=False)
    gateway = db.Column(db.String(40), default="Razorpay", nullable=False)
    transaction_id = db.Column(db.String(100), nullable=True)  # Gateway Transaction ID / Payment ID
    payment_method = db.Column(db.String(50), nullable=True)
    proof_path = db.Column(db.String(255), nullable=True)
    payment_date = db.Column(db.DateTime, nullable=True)

    # Statuses: PENDING, SUCCESS, FAILED, CANCELLED, REFUNDED, verified, rejected
    status = db.Column(db.String(30), default="PENDING", nullable=False)

    verified_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.String(255), nullable=True)

    # Relationships
    user = db.relationship("User", foreign_keys=[user_id], backref="payments")
    tournament = db.relationship("Tournament", foreign_keys=[tournament_id], backref="payments")

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __repr__(self):
        return f"<Payment {self.order_id or self.transaction_id or self.id} status={self.status}>"
