from app.extensions import db
from app.models.mixins import TimestampMixin


class Dispute(db.Model, TimestampMixin):
    __tablename__ = "disputes"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey("matches.id"), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    raised_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    reason = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    proof_url = db.Column(db.String(255), nullable=True)

    # open / under_review / accepted / rejected / resolved
    status = db.Column(db.String(20), default="open", nullable=False)
    handled_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    resolution_note = db.Column(db.Text, nullable=True)

    match = db.relationship("Match")
    team = db.relationship("Team")
