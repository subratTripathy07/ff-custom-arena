"""Statistics aggregation and achievement checking service."""
from datetime import datetime
from app.extensions import db, socketio
from app.models.player import PlayerStatistic, Achievement, PlayerAchievement
from app.models.tournament import Tournament
from app.models.match import Match, MatchResult
from app.services.tournament_service import notify_user


def check_and_award_achievements(user_id, match_result=None):
    """
    Evaluates player stats and recent match result to award achievements.
    Achievements:
      - FIRST_BLOOD: 1st kill in a tournament match
      - HUNDRED_KILLS: Reach 100 career kills
      - TOURNAMENT_WINNER: Win a tournament match or tournament
      - FIVE_X_MVP: Earn MVP 5 times
      - TOP_RANKED: Reach #1 on the global leaderboard
      - TWENTY_KILL_GAME: Get 20 kills in a single match
    """
    stats = PlayerStatistic.query.filter_by(user_id=user_id).first()
    if not stats:
        return []

    unlocked = []

    def _award(code):
        ach = Achievement.query.filter_by(code=code).first()
        if ach and not PlayerAchievement.query.filter_by(user_id=user_id, achievement_id=ach.id).first():
            pa = PlayerAchievement(user_id=user_id, achievement_id=ach.id, earned_at=datetime.utcnow())
            db.session.add(pa)
            unlocked.append(ach)
            notify_user(
                user_id,
                f"Achievement Unlocked: {ach.icon} {ach.title} - {ach.description}",
                icon=ach.icon or "🏆"
            )

    # 1. FIRST_BLOOD
    if stats.total_kills >= 1:
        _award("FIRST_BLOOD")

    # 2. HUNDRED_KILLS
    if stats.total_kills >= 100:
        _award("HUNDRED_KILLS")

    # 3. TOURNAMENT_WINNER
    if stats.wins >= 1:
        _award("TOURNAMENT_WINNER")

    # 4. FIVE_X_MVP
    if stats.mvp_count >= 5:
        _award("FIVE_X_MVP")

    # 5. TWENTY_KILL_GAME
    if match_result and match_result.kills >= 20:
        _award("TWENTY_KILL_GAME")

    # 6. TOP_RANKED (Check if user is #1)
    top_stat = PlayerStatistic.query.order_by(PlayerStatistic.total_points.desc(), PlayerStatistic.total_kills.desc()).first()
    if top_stat and top_stat.user_id == user_id and top_stat.total_points > 0:
        _award("TOP_RANKED")

    if unlocked:
        db.session.commit()

    return unlocked


def get_global_player_leaderboard(limit=50):
    """Returns ranked list of player stats."""
    stats = (
        PlayerStatistic.query.join(PlayerStatistic.user)
        .order_by(PlayerStatistic.total_points.desc(), PlayerStatistic.wins.desc(), PlayerStatistic.total_kills.desc())
        .limit(limit)
        .all()
    )
    ranked = []
    for rank, s in enumerate(stats, 1):
        ranked.append({
            "rank": rank,
            "user": s.user,
            "matches_played": s.matches_played,
            "wins": s.wins,
            "total_kills": s.total_kills,
            "total_points": s.total_points,
            "mvp_count": s.mvp_count,
            "avg_placement": s.avg_placement,
        })
    return ranked
