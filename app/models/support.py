from app.extensions import db
from app.models.mixins import TimestampMixin


class SupportTicket(db.Model, TimestampMixin):
    __tablename__ = "support_tickets"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    category = db.Column(db.String(50), nullable=False)
    subject = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    attachment_url = db.Column(db.String(255), nullable=True)

    # open / in_progress / resolved / closed
    status = db.Column(db.String(20), default="open", nullable=False)

    user = db.relationship("User", backref="support_tickets")
    replies = db.relationship(
        "SupportMessage", backref="ticket", lazy="dynamic", cascade="all, delete-orphan"
    )


class SupportMessage(db.Model, TimestampMixin):
    __tablename__ = "support_messages"

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("support_tickets.id"), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    message = db.Column(db.Text, nullable=False)

    sender = db.relationship("User")
