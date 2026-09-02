from app.extensions import db
from app.models.mixins import TimestampMixin


class Room(db.Model, TimestampMixin):
    __tablename__ = "rooms"

    id = db.Column(db.Integer, primary_key=True)
    room_id_code = db.Column(db.String(30), nullable=False)   # actual FF room ID
    room_password = db.Column(db.String(30), nullable=False)

    release_time = db.Column(db.DateTime, nullable=False)
    # preparing / scheduled / released / completed
    status = db.Column(db.String(20), default="preparing", nullable=False)

    match = db.relationship("Match", backref="room", uselist=False)

    def masked(self, mask_char="•"):
        return {
            "room_id": mask_char * 8,
            "password": mask_char * 8,
        }

    def revealed(self):
        return {"room_id": self.room_id_code, "password": self.room_password}


class Match(db.Model, TimestampMixin):
    __tablename__ = "matches"

    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey("tournaments.id"), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id"), nullable=True)

    round_number = db.Column(db.Integer, default=1, nullable=False)
    match_number = db.Column(db.Integer, nullable=False)
    map_name = db.Column(db.String(50), nullable=True)

    scheduled_date = db.Column(db.Date, nullable=False)
    scheduled_time = db.Column(db.Time, nullable=False)

    # scheduled / room_pending / room_released / live / completed / cancelled
    status = db.Column(db.String(20), default="upcoming", nullable=False)

    match_teams = db.relationship(
        "MatchTeam", backref="match", lazy="dynamic", cascade="all, delete-orphan"
    )
    results = db.relationship(
        "MatchResult", backref="match", lazy="dynamic", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Match #{self.match_number} T{self.tournament_id}>"


class MatchTeam(db.Model):
    """Which teams are slotted into a given match."""
    __tablename__ = "match_teams"
    __table_args__ = (
        db.UniqueConstraint("match_id", "team_id", name="uq_match_team"),
    )

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey("matches.id"), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    slot_number = db.Column(db.Integer, nullable=True)

    team = db.relationship("Team")


class MatchResult(db.Model, TimestampMixin):
    __tablename__ = "match_results"
    __table_args__ = (
        db.UniqueConstraint("match_id", "team_id", name="uq_match_result_team"),
    )

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey("matches.id"), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)

    placement = db.Column(db.Integer, nullable=False)
    kills = db.Column(db.Integer, default=0, nullable=False)
    placement_points = db.Column(db.Integer, default=0, nullable=False)
    kill_points = db.Column(db.Integer, default=0, nullable=False)
    total_points = db.Column(db.Integer, default=0, nullable=False)

    is_mvp_team = db.Column(db.Boolean, default=False, nullable=False)
    mvp_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    # submitted / under_review / verified / rejected
    status = db.Column(db.String(20), default="pending", nullable=False)
    proof_url = db.Column(db.String(255), nullable=True)
    rejection_reason = db.Column(db.String(255), nullable=True)
    verified_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)

    team = db.relationship("Team")

    def compute_total(self):
        self.total_points = self.placement_points + self.kill_points
        return self.total_points
