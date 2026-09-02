from app.extensions import db
from app.models.mixins import TimestampMixin

class Wallet(db.Model, TimestampMixin):
    __tablename__ = "wallets"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)

    available_balance = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    winning_balance = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    bonus_balance = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)

    total_added = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    total_withdrawn = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)

    transactions = db.relationship("WalletTransaction", backref="wallet", lazy="dynamic", cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    @property
    def total_balance(self):
        return float(self.available_balance or 0) + float(self.winning_balance or 0) + float(self.bonus_balance or 0)

    def __repr__(self):
        return f"<Wallet User={self.user_id} Total={self.total_balance}>"


class WalletTransaction(db.Model, TimestampMixin):
    __tablename__ = "wallet_transactions"

    id = db.Column(db.Integer, primary_key=True)
    wallet_id = db.Column(db.Integer, db.ForeignKey("wallets.id"), nullable=False)

    # Transaction Type: Deposit, Tournament Entry, Prize, Refund, Withdrawal
    transaction_type = db.Column(db.String(30), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    balance_after = db.Column(db.Numeric(10, 2), default=0.00, nullable=True)

    # Status: PENDING, SUCCESS, FAILED, REFUNDED
    status = db.Column(db.String(20), default="SUCCESS", nullable=False)

    description = db.Column(db.String(255), nullable=True)
    reference_id = db.Column(db.String(100), nullable=True)
    proof_path = db.Column(db.String(255), nullable=True)
    payment_method = db.Column(db.String(50), nullable=True)
    rejection_reason = db.Column(db.String(255), nullable=True)

    def __init__(self, **kwargs):
        if "balance_after" not in kwargs or kwargs["balance_after"] is None:
            kwargs["balance_after"] = 0.00
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __repr__(self):
        return f"<WalletTransaction {self.transaction_type} {self.amount} status={self.status}>"
