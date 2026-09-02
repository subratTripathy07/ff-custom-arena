from app.extensions import db
from app.models.mixins import TimestampMixin


class UploadedProof(db.Model, TimestampMixin):
    __tablename__ = "uploaded_proofs"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey("matches.id"), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    file_path = db.Column(db.String(255), nullable=False)   # secure_filename generated path
    description = db.Column(db.String(255), nullable=True)

    # pending / approved / rejected
    status = db.Column(db.String(20), default="pending", nullable=False)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
