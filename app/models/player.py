from app.extensions import db
from app.models.mixins import TimestampMixin


class PlayerProfile(db.Model, TimestampMixin):
    __tablename__ = "player_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)

    ff_uid = db.Column(db.String(30), unique=True, nullable=True, index=True)
    ff_ign = db.Column(db.String(50), nullable=True)  # in-game name
    bio = db.Column(db.String(255), nullable=True)
    country = db.Column(db.String(60), nullable=True)

    def __repr__(self):
        return f"<PlayerProfile uid={self.ff_uid}>"


class PlayerStatistic(db.Model, TimestampMixin):
    """Aggregated, denormalized stats kept in sync by services/stats_service.py"""
    __tablename__ = "player_statistics"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)

    matches_played = db.Column(db.Integer, default=0, nullable=False)
    wins = db.Column(db.Integer, default=0, nullable=False)
    total_kills = db.Column(db.Integer, default=0, nullable=False)
    total_points = db.Column(db.Integer, default=0, nullable=False)
    mvp_count = db.Column(db.Integer, default=0, nullable=False)
    sum_placement = db.Column(db.Integer, default=0, nullable=False)  # used to compute avg

    user = db.relationship("User", backref=db.backref("statistics", uselist=False))

    @property
    def avg_placement(self):
        if self.matches_played == 0:
            return 0
        return round(self.sum_placement / self.matches_played, 2)


class Achievement(db.Model):
    __tablename__ = "achievements"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)   # e.g. FIRST_BLOOD
    title = db.Column(db.String(100), nullable=False)              # "First Blood"
    icon = db.Column(db.String(10), default="🏆")
    description = db.Column(db.String(255))


class PlayerAchievement(db.Model):
    __tablename__ = "player_achievements"
    __table_args__ = (
        db.UniqueConstraint("user_id", "achievement_id", name="uq_user_achievement"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    achievement_id = db.Column(db.Integer, db.ForeignKey("achievements.id"), nullable=False)
    earned_at = db.Column(db.DateTime, server_default=db.func.now())

    achievement = db.relationship("Achievement")
