from app.extensions import db
from app.models.mixins import TimestampMixin


class Prize(db.Model, TimestampMixin):
    __tablename__ = "prizes"

    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey("tournaments.id"), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)

    rank = db.Column(db.Integer, nullable=False)          # 1, 2, 3...
    amount = db.Column(db.Numeric(10, 2), nullable=False)

    # pending / processing / paid / rejected
    status = db.Column(db.String(20), default="pending", nullable=False)
    payment_date = db.Column(db.DateTime, nullable=True)
    reference_id = db.Column(db.String(100), nullable=True)

    tournament = db.relationship("Tournament")
    team = db.relationship("Team")
