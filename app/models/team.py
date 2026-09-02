from app.extensions import db
from app.models.mixins import TimestampMixin


class Team(db.Model, TimestampMixin):
    __tablename__ = "teams"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False, index=True)
    tag = db.Column(db.String(10), nullable=True)              # short clan tag e.g. [FFA]
    logo_url = db.Column(db.String(255), default="default_team_logo.png")
    description = db.Column(db.Text, nullable=True)

    captain_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    captain = db.relationship("User", foreign_keys=[captain_id])

    is_active = db.Column(db.Boolean, default=True, nullable=False)

    members = db.relationship(
        "TeamMember", backref="team", lazy="dynamic", cascade="all, delete-orphan"
    )
    registrations = db.relationship(
        "TournamentRegistration", backref="team", lazy="dynamic"
    )

    def roster_count(self):
        return self.members.filter_by(is_substitute=False).count()

    def __repr__(self):
        return f"<Team {self.name}>"


class TeamMember(db.Model, TimestampMixin):
    __tablename__ = "team_members"
    __table_args__ = (
        db.UniqueConstraint("user_id", "team_id", name="uq_user_team"),
    )

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    is_substitute = db.Column(db.Boolean, default=False, nullable=False)
    joined_at = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self):
        return f"<TeamMember team={self.team_id} user={self.user_id}>"
