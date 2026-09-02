from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app.extensions import db
from app.models.notification import Notification
from app.models.user import User
from app.models.player import PlayerProfile, PlayerStatistic, Achievement, PlayerAchievement
from app.models.team import Team, TeamMember
from app.models.match import MatchResult, Match
from app.models.tournament import Tournament, TournamentRegistration
from app.services.stats_service import get_global_player_leaderboard
from app.utils.security import save_uploaded_image
from app.utils.audit import log_action

player_bp = Blueprint("player", __name__, template_folder="../templates")


@player_bp.route("/my-matches")
@login_required
def my_matches():
    user_team_ids = [tm.team_id for tm in TeamMember.query.filter_by(user_id=current_user.id).all()]
    captain_team_ids = [t.id for t in Team.query.filter_by(captain_id=current_user.id).all()]
    all_team_ids = list(set(user_team_ids + captain_team_ids))

    query_filter = [TournamentRegistration.registered_by_id == current_user.id]
    if all_team_ids:
        query_filter.append(TournamentRegistration.team_id.in_(all_team_ids))

    registrations = (
        TournamentRegistration.query.filter(db.or_(*query_filter))
        .order_by(TournamentRegistration.created_at.desc())
        .all()
    )

    booked_matches = []
    total_tokens_spent = 0.0
    active_count = 0

    for reg in registrations:
        tournament = reg.tournament
        first_match = Match.query.filter_by(tournament_id=tournament.id).order_by(Match.scheduled_time.asc()).first()
        fee = float(tournament.entry_fee or 0)
        total_tokens_spent += fee
        if reg.status == "confirmed" and tournament.status in ["registration_open", "ongoing"]:
            active_count += 1

        booked_matches.append({
            "registration": reg,
            "tournament": tournament,
            "team": reg.team,
            "match": first_match,
            "slot_number": reg.slot_number or "Auto",
            "registration_code": reg.registration_code,
            "in_game_name": reg.in_game_name or current_user.username,
            "status": reg.status,
            "entry_fee": fee,
            "created_at": reg.created_at
        })

    return render_template(
        "main/my_matches.html",
        booked_matches=booked_matches,
        total_tokens_spent=total_tokens_spent,
        active_count=active_count
    )


@player_bp.route("/profile", methods=["GET", "POST"])
@login_required
def my_profile():
    profile = current_user.profile
    if not profile:
        profile = PlayerProfile(user_id=current_user.id)
        db.session.add(profile)
        db.session.commit()

    stats = PlayerStatistic.query.filter_by(user_id=current_user.id).first()
    if not stats:
        stats = PlayerStatistic(user_id=current_user.id)
        db.session.add(stats)
        db.session.commit()

    if request.method == "POST":
        ff_uid = request.form.get("ff_uid", "").strip()
        ff_ign = request.form.get("ff_ign", "").strip()
        bio = request.form.get("bio", "").strip()
        country = request.form.get("country", "").strip()

        if ff_uid:
            existing = PlayerProfile.query.filter(
                PlayerProfile.ff_uid == ff_uid,
                PlayerProfile.user_id != current_user.id
            ).first()
            if existing:
                flash("That Free Fire UID is already registered by another player.", "danger")
                return redirect(url_for("player.my_profile"))

        profile.ff_uid = ff_uid or None
        profile.ff_ign = ff_ign or None
        profile.bio = bio or None
        profile.country = country or None

        avatar_file = request.files.get("avatar")
        if avatar_file and avatar_file.filename:
            try:
                avatar_path = save_uploaded_image(avatar_file, "avatars")
                if avatar_path:
                    current_user.avatar_url = avatar_path
            except ValueError as e:
                flash(str(e), "danger")
                return redirect(url_for("player.my_profile"))

        db.session.commit()
        log_action("Profile updated", "PlayerProfile", profile.id)
        flash("Your player profile has been updated successfully!", "success")
        return redirect(url_for("player.my_profile"))

    user_achievements = (
        PlayerAchievement.query.filter_by(user_id=current_user.id)
        .order_by(PlayerAchievement.earned_at.desc())
        .all()
    )
    unlocked_ids = {pa.achievement_id for pa in user_achievements}
    all_achievements = Achievement.query.all()

    recent_results = (
        MatchResult.query.join(MatchResult.team)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .filter(TeamMember.user_id == current_user.id, MatchResult.status == "verified")
        .order_by(MatchResult.created_at.desc())
        .limit(10)
        .all()
    )

    return render_template(
        "main/profile.html",
        profile=profile,
        stats=stats,
        user_achievements=user_achievements,
        unlocked_ids=unlocked_ids,
        all_achievements=all_achievements,
        recent_results=recent_results,
    )


@player_bp.route("/players/<username>")
def public_profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    profile = user.profile
    stats = PlayerStatistic.query.filter_by(user_id=user.id).first()

    user_achievements = (
        PlayerAchievement.query.filter_by(user_id=user.id)
        .order_by(PlayerAchievement.earned_at.desc())
        .all()
    )
    unlocked_ids = {pa.achievement_id for pa in user_achievements}
    all_achievements = Achievement.query.all()

    recent_results = (
        MatchResult.query.join(MatchResult.team)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .filter(TeamMember.user_id == user.id, MatchResult.status == "verified")
        .order_by(MatchResult.created_at.desc())
        .limit(10)
        .all()
    )

    return render_template(
        "main/public_profile.html",
        user=user,
        profile=profile,
        stats=stats,
        user_achievements=user_achievements,
        unlocked_ids=unlocked_ids,
        all_achievements=all_achievements,
        recent_results=recent_results,
    )


@player_bp.route("/leaderboards")
def global_leaderboards():
    players = get_global_player_leaderboard(limit=100)
    teams = (
        Team.query.filter_by(is_active=True)
        .order_by(Team.created_at.desc())
        .limit(50)
        .all()
    )
    return render_template("main/leaderboard_global.html", players=players, teams=teams)


@player_bp.route("/achievements")
def achievements_gallery():
    all_achievements = Achievement.query.all()
    unlocked_ids = set()
    if current_user.is_authenticated:
        user_achs = PlayerAchievement.query.filter_by(user_id=current_user.id).all()
        unlocked_ids = {ua.achievement_id for ua in user_achs}
    return render_template("main/achievements.html", achievements=all_achievements, unlocked_ids=unlocked_ids)


# ─────────────────────────────────────────────
# Notification Center
# ─────────────────────────────────────────────

@player_bp.route("/notifications")
@login_required
def notifications():
    filter_by = request.args.get("filter", "").strip()
    page = request.args.get("page", 1, type=int)

    query = Notification.query.filter_by(user_id=current_user.id)
    if filter_by == "unread":
        query = query.filter_by(is_read=False)
    elif filter_by == "read":
        query = query.filter_by(is_read=True)

    paginated = query.order_by(Notification.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()

    return render_template(
        "main/notifications.html",
        notifications=paginated,
        unread_count=unread_count,
        filter=filter_by,
    )


@player_bp.route("/notifications/<int:notif_id>/read", methods=["POST"])
@login_required
def mark_notification_read(notif_id):
    notif = Notification.query.get_or_404(notif_id)
    if notif.user_id != current_user.id:
        from flask import abort
        abort(403)
    notif.is_read = True
    db.session.commit()
    return redirect(request.referrer or url_for("player.notifications"))
