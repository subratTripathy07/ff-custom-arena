from app.extensions import db
from app.models.mixins import TimestampMixin


class Tournament(db.Model, TimestampMixin):
    __tablename__ = "tournaments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(140), unique=True, nullable=False, index=True)
    banner_url = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    rules = db.Column(db.Text, nullable=True)

    # solo / duo / squad / clash_squad / league / knockout / championship
    tournament_type = db.Column(db.String(30), nullable=False)
    game_mode = db.Column(db.String(50), nullable=True)   # e.g. Battle Royale, Clash Squad
    map_name = db.Column(db.String(50), nullable=True)

    max_teams = db.Column(db.Integer, nullable=False, default=48)
    entry_fee = db.Column(db.Numeric(10, 2), default=0)
    prize_pool = db.Column(db.Numeric(10, 2), default=0)
    per_kill_prize = db.Column(db.Numeric(10, 2), default=5.0)

    registration_deadline = db.Column(db.DateTime, nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=True)

    # registration_open / closing_soon / live / completed / closed
    status = db.Column(db.String(20), default="registration_open", nullable=False)

    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    registrations = db.relationship(
        "TournamentRegistration", backref="tournament", lazy="dynamic",
        cascade="all, delete-orphan"
    )
    matches = db.relationship("Match", backref="tournament", lazy="dynamic")
    scoring_rules = db.relationship(
        "ScoringRule", backref="tournament", lazy="dynamic", cascade="all, delete-orphan"
    )

    @property
    def registered_team_count(self):
        return self.registrations.filter_by(status="confirmed").count()

    @property
    def slots_left(self):
        return max(self.max_teams - self.registered_team_count, 0)

    def __repr__(self):
        return f"<Tournament {self.name}>"


class TournamentRegistration(db.Model, TimestampMixin):
    __tablename__ = "tournament_registrations"
    __table_args__ = (
        db.UniqueConstraint("tournament_id", "team_id", name="uq_tournament_team"),
        db.UniqueConstraint("tournament_id", "slot_number", name="uq_tournament_slot_number"),
    )

    id = db.Column(db.Integer, primary_key=True)
    registration_code = db.Column(db.String(20), unique=True, nullable=False)  # FF-REG-28472

    tournament_id = db.Column(db.Integer, db.ForeignKey("tournaments.id"), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    registered_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    slot_number = db.Column(db.Integer, nullable=True)     # 1 to 48 match position
    in_game_name = db.Column(db.String(100), nullable=True)  # Free Fire IGN / UID

    # pending / confirmed / rejected / cancelled
    status = db.Column(db.String(20), default="pending", nullable=False)

    payment = db.relationship(
        "Payment", backref="registration", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Registration {self.registration_code}>"


class ScoringRule(db.Model):
    """Configurable placement-points table per tournament. Kill points stored separately."""
    __tablename__ = "scoring_rules"

    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey("tournaments.id"), nullable=False)

    placement = db.Column(db.Integer, nullable=False)   # 1st, 2nd, 3rd...
    points = db.Column(db.Integer, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("tournament_id", "placement", name="uq_tournament_placement"),
    )
