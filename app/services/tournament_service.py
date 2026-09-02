"""Business rules shared by web routes and the Android API."""
from datetime import datetime

from app.extensions import db, socketio
from app.models.match import Match, MatchTeam, MatchResult, Room
from app.models.notification import Notification
from app.models.player import PlayerStatistic
from app.models.tournament import Tournament, TournamentRegistration
from app.models.prize import Prize


def notify_user(user_id, message, link=None, icon="🔔"):
    notification = Notification(user_id=user_id, message=message, link=link, icon=icon)
    db.session.add(notification)
    db.session.flush()
    try:
        socketio.emit(
            "notification",
            {"id": notification.id, "message": message, "link": link, "icon": icon},
            room=f"user:{user_id}",
        )
    except Exception:
        pass
    return notification


def broadcast_tournament_notification(tournament_id, message, link=None, icon="📢"):
    """Notify all confirmed participants of a tournament."""
    registrations = TournamentRegistration.query.filter_by(tournament_id=tournament_id, status="confirmed").all()
    for reg in registrations:
        for member in reg.team.members:
            notify_user(member.user_id, message, link=link, icon=icon)


def calculate_result(match, team_id, placement, kills):
    """Calculate points from the tournament's configurable placement table."""
    if placement < 1 or kills < 0:
        raise ValueError("Placement must be positive and kills cannot be negative.")
    if not any(slot.team_id == team_id for slot in match.match_teams):
        raise ValueError("That team is not assigned to this match.")
    placement_rule = match.tournament.scoring_rules.filter_by(placement=placement).first()
    
    # Standard Free Fire esports default scoring if no custom rule exists:
    # 1st: 12, 2nd: 9, 3rd: 8, 4th: 7, 5th: 6, 6th: 5, 7th: 4, 8th: 3, 9th: 2, 10th: 1, others: 0
    default_placements = {1: 12, 2: 9, 3: 8, 4: 7, 5: 6, 6: 5, 7: 4, 8: 3, 9: 2, 10: 1}
    placement_points = placement_rule.points if placement_rule else default_placements.get(placement, 0)
    kill_points = kills
    return placement_points, kill_points, placement_points + kill_points


def verify_result(result, reviewer_id):
    """Verify once, update team-player aggregates, trigger achievements, and publish a live event."""
    from app.services.stats_service import check_and_award_achievements

    if result.status == "verified":
        raise ValueError("This result has already been verified.")
    result.status = "verified"
    result.verified_by_id = reviewer_id
    result.verified_at = datetime.utcnow()

    for member in result.team.members.filter_by(is_substitute=False):
        stats = PlayerStatistic.query.filter_by(user_id=member.user_id).first()
        if not stats:
            stats = PlayerStatistic(user_id=member.user_id)
            db.session.add(stats)
        stats.matches_played += 1
        stats.total_kills += result.kills
        stats.total_points += result.total_points
        stats.sum_placement += result.placement
        if result.placement == 1:
            stats.wins += 1
        if result.mvp_user_id == member.user_id:
            stats.mvp_count += 1
        
        notify_user(
            member.user_id,
            f"Result verified: {result.team.name} secured #{result.placement} with {result.kills} kills ({result.total_points} pts).",
            icon="🏆"
        )
        # Check achievements
        check_and_award_achievements(member.user_id, result)

    try:
        socketio.emit(
            "result_verified",
            {
                "match_id": result.match_id,
                "team_id": result.team_id,
                "points": result.total_points,
                "placement": result.placement,
                "kills": result.kills,
            },
            room=f"tournament:{result.match.tournament_id}",
        )
    except Exception:
        pass


def auto_assign_teams_to_match(match_id):
    """Automatically assigns all confirmed registered teams to the match slots."""
    match = Match.query.get(match_id)
    if not match:
        return 0
    
    confirmed_regs = (
        TournamentRegistration.query.filter_by(tournament_id=match.tournament_id, status="confirmed")
        .order_by(TournamentRegistration.created_at.asc())
        .all()
    )

    assigned = 0
    for idx, reg in enumerate(confirmed_regs, 1):
        if not MatchTeam.query.filter_by(match_id=match.id, team_id=reg.team_id).first():
            db.session.add(MatchTeam(match_id=match.id, team_id=reg.team_id, slot_number=idx))
            assigned += 1

    if assigned > 0:
        db.session.commit()
    return assigned


def check_and_release_room(match):
    """Checks if room release time has arrived and broadcasts to Socket.IO."""
    if not match.room:
        return False
    
    if match.room.release_time <= datetime.utcnow() and match.room.status != "released":
        match.room.status = "released"
        if match.status == "room_pending":
            match.status = "room_released"
        db.session.commit()
        try:
            socketio.emit(
                "room_released",
                {"match_id": match.id, "room_id": match.room.room_id_code, "password": match.room.room_password},
                room=f"tournament:{match.tournament_id}",
            )
            # Also notify assigned team captains
            for slot in match.match_teams:
                if slot.team and slot.team.captain_id:
                    notify_user(
                        slot.team.captain_id,
                        f"Room credentials released for Match #{match.match_number} in {match.tournament.name}!",
                        link=f"/matches/{match.id}",
                        icon="🔑"
                    )
        except Exception:
            pass
        return True
    return False
