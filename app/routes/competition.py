from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db, socketio
from app.models.match import Match, MatchTeam, MatchResult, Room
from app.models.team import Team, TeamMember
from app.models.tournament import Tournament
from app.models.dispute import Dispute
from app.models.user import Role
from app.services.tournament_service import (
    calculate_result,
    notify_user,
    verify_result,
    check_and_release_room,
    auto_assign_teams_to_match,
)
from app.utils.audit import log_action
from app.utils.decorators import roles_required
from app.utils.uploads import save_proof

competition_bp = Blueprint("competition", __name__, template_folder="../templates")


@competition_bp.route("/matches")
@competition_bp.route("/competition/matches")
@login_required
def matches():
    status = request.args.get("status", "").strip()
    query = Match.query.order_by(Match.scheduled_date.asc(), Match.scheduled_time.asc())
    if status:
        query = query.filter_by(status=status)
    paginated_matches = query.paginate(
        page=request.args.get("page", 1, type=int), per_page=20, error_out=False
    )
    return render_template("competition/matches.html", matches=paginated_matches, status=status)


@competition_bp.route("/matches/<int:match_id>")
@login_required
def match_detail(match_id):
    match = Match.query.get_or_404(match_id)

    # Check if user is an admin or part of a slotted team
    user_team_ids = [
        tm.team_id for tm in TeamMember.query.filter_by(user_id=current_user.id).all()
    ]
    enrolled = current_user.is_admin() or any(
        slot.team_id in user_team_ids for slot in match.match_teams
    )

    if not enrolled and not current_user.is_admin():
        # Let public see match summary, but restrict room details
        pass

    # Check auto room release
    check_and_release_room(match)

    room_data = None
    if match.room and (enrolled or current_user.is_admin()):
        if match.room.release_time <= datetime.utcnow():
            room_data = match.room.revealed()
        else:
            room_data = match.room.masked()

    # Get results for this match
    results = match.results.order_by(MatchResult.placement.asc()).all()

    # Check if current user captain can submit result
    my_captained_team = None
    for slot in match.match_teams:
        if slot.team and slot.team.captain_id == current_user.id:
            my_captained_team = slot.team
            break

    existing_my_result = None
    if my_captained_team:
        existing_my_result = match.results.filter_by(team_id=my_captained_team.id).first()

    # Disputes for this match
    disputes = Dispute.query.filter_by(match_id=match.id).all()

    return render_template(
        "competition/match_detail.html",
        match=match,
        room_data=room_data,
        results=results,
        my_captained_team=my_captained_team,
        existing_my_result=existing_my_result,
        disputes=disputes,
        enrolled=enrolled,
        now=datetime.utcnow(),
    )


@competition_bp.route("/matches/<int:match_id>/submit-result", methods=["POST"])
@login_required
def submit_team_result(match_id):
    match = Match.query.get_or_404(match_id)
    team_id = request.form.get("team_id", type=int)
    team = Team.query.get_or_404(team_id)

    if team.captain_id != current_user.id and not current_user.is_admin():
        abort(403)

    try:
        placement = request.form.get("placement", type=int)
        kills = request.form.get("kills", type=int)
        if placement is None or kills is None:
            raise ValueError("Please provide both placement and kill count.")

        pp, kp, total = calculate_result(match, team.id, placement, kills)
        
        # Proof upload
        proof_file = request.files.get("proof")
        proof_url = None
        if proof_file and proof_file.filename:
            proof_url = save_proof(proof_file, "result_proofs")

        result = MatchResult.query.filter_by(match_id=match.id, team_id=team.id).first()
        if not result:
            result = MatchResult(match_id=match.id, team_id=team.id)

        result.placement = placement
        result.kills = kills
        result.placement_points = pp
        result.kill_points = kp
        result.total_points = total
        result.status = "under_review"
        if proof_url:
            result.proof_url = proof_url

        db.session.add(result)
        db.session.commit()

        log_action("Result submitted for review", "MatchResult", result.id)
        flash("Match scoreboard result submitted! An admin will review and verify.", "success")
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "danger")

    return redirect(url_for("competition.match_detail", match_id=match.id))


@competition_bp.route("/matches/<int:match_id>/dispute", methods=["POST"])
@login_required
def submit_dispute(match_id):
    match = Match.query.get_or_404(match_id)
    team_id = request.form.get("team_id", type=int)
    team = Team.query.get_or_404(team_id)

    if team.captain_id != current_user.id and not current_user.is_admin():
        abort(403)

    reason = request.form.get("reason", "").strip()
    description = request.form.get("description", "").strip()
    if not reason:
        flash("Please provide a reason for the dispute.", "danger")
        return redirect(url_for("competition.match_detail", match_id=match.id))

    proof_file = request.files.get("proof")
    proof_url = None
    if proof_file and proof_file.filename:
        proof_url = save_proof(proof_file, "dispute_proofs")

    dispute = Dispute(
        match_id=match.id,
        team_id=team.id,
        raised_by_id=current_user.id,
        reason=reason[:150],
        description=description or None,
        proof_url=proof_url,
        status="open",
    )
    db.session.add(dispute)
    db.session.commit()

    log_action("Dispute raised", "Dispute", dispute.id)
    flash("Dispute ticket raised. A tournament moderator will review the incident.", "warning")
    return redirect(url_for("competition.match_detail", match_id=match.id))


@competition_bp.route("/leaderboards/<int:tournament_id>")
@competition_bp.route("/leaderboard/<int:tournament_id>")
@competition_bp.route("/tournaments/<int:tournament_id>/leaderboard")
def leaderboard(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    round_filter = request.args.get("round", type=int)

    query = MatchResult.query.join(Match).filter(
        Match.tournament_id == tournament.id, MatchResult.status == "verified"
    )
    if round_filter:
        query = query.filter(Match.round_number == round_filter)

    results = query.all()
    board = {}
    for result in results:
        row = board.setdefault(
            result.team_id,
            {
                "team": result.team,
                "matches": 0,
                "wins": 0,
                "kills": 0,
                "placement_points": 0,
                "kill_points": 0,
                "total_points": 0,
            },
        )
        row["matches"] += 1
        row["wins"] += 1 if result.placement == 1 else 0
        row["kills"] += result.kills
        row["placement_points"] += result.placement_points
        row["kill_points"] += result.kill_points
        row["total_points"] += result.total_points

    ranked = sorted(board.values(), key=lambda row: (-row["total_points"], -row["kills"]))
    for rank, row in enumerate(ranked, 1):
        row["rank"] = rank

    rounds = db.session.query(Match.round_number).filter(Match.tournament_id == tournament.id).distinct().all()
    available_rounds = [r[0] for r in rounds]

    return render_template(
        "competition/leaderboard.html",
        tournament=tournament,
        board=ranked,
        round_filter=round_filter,
        available_rounds=available_rounds,
    )


# ---------- Admin Operations ----------

@competition_bp.route("/admin/matches/create", methods=["POST"])
@roles_required(Role.SUPER_ADMIN, Role.TOURNAMENT_MANAGER)
def create_match():
    tournament = Tournament.query.get_or_404(request.form.get("tournament_id", type=int))
    try:
        date = datetime.strptime(request.form["scheduled_at"], "%Y-%m-%dT%H:%M")
        match = Match(
            tournament_id=tournament.id,
            round_number=request.form.get("round_number", 1, type=int),
            match_number=request.form["match_number"],
            map_name=request.form.get("map_name") or tournament.map_name,
            scheduled_date=date.date(),
            scheduled_time=date.time(),
            status="scheduled",
        )
        db.session.add(match)
        db.session.commit()
        
        # Auto-slot confirmed teams if checked
        if request.form.get("auto_slot") == "1":
            auto_assign_teams_to_match(match.id)

        log_action("Match created", "Match", match.id)
        try:
            socketio.emit("match_created", {"match_id": match.id}, room=f"tournament:{tournament.id}")
        except Exception:
            pass

        flash("Match scheduled successfully!", "success")
    except (KeyError, ValueError):
        db.session.rollback()
        flash("Enter a valid schedule and match number.", "danger")
    return redirect(url_for("admin.manage_tournament", tournament_id=tournament.id))


@competition_bp.route("/admin/matches/<int:match_id>/auto-slot", methods=["POST"])
@roles_required(Role.SUPER_ADMIN, Role.TOURNAMENT_MANAGER)
def auto_slot_teams(match_id):
    match = Match.query.get_or_404(match_id)
    count = auto_assign_teams_to_match(match.id)
    flash(f"Slotted {count} confirmed team(s) into Match #{match.match_number}.", "success")
    return redirect(url_for("admin.manage_tournament", tournament_id=match.tournament_id))


@competition_bp.route("/admin/matches/<int:match_id>/room", methods=["POST"])
@roles_required(Role.SUPER_ADMIN, Role.TOURNAMENT_MANAGER)
def set_room(match_id):
    match = Match.query.get_or_404(match_id)
    try:
        release_time = datetime.strptime(request.form["release_time"], "%Y-%m-%dT%H:%M")
        room = match.room or Room()
        room.room_id_code = request.form["room_id"].strip()
        room.room_password = request.form["room_password"].strip()
        room.release_time = release_time
        room.status = "scheduled"

        if not match.room:
            db.session.add(room)
            db.session.flush()
            match.room_id = room.id

        match.status = "room_pending"
        db.session.commit()
        log_action("Room scheduled", "Match", match.id)
        flash("Room credentials scheduled successfully.", "success")
    except (KeyError, ValueError):
        db.session.rollback()
        flash("Provide valid room credentials and release time.", "danger")
    return redirect(url_for("competition.match_detail", match_id=match.id))


@competition_bp.route("/admin/matches/<int:match_id>/status", methods=["POST"])
@roles_required(Role.SUPER_ADMIN, Role.TOURNAMENT_MANAGER)
def change_match_status(match_id):
    match = Match.query.get_or_404(match_id)
    status = request.form.get("status")
    if status not in {"scheduled", "room_pending", "room_released", "live", "completed", "cancelled"}:
        abort(400)
    match.status = status
    db.session.commit()
    log_action(f"Match marked {status}", "Match", match.id)
    try:
        socketio.emit(
            "match_status",
            {"match_id": match.id, "status": status},
            room=f"tournament:{match.tournament_id}",
        )
    except Exception:
        pass
    flash(f"Match status changed to '{status}'.", "info")
    return redirect(url_for("competition.match_detail", match_id=match.id))


@competition_bp.route("/admin/matches/<int:match_id>/delete", methods=["POST"])
@roles_required(Role.SUPER_ADMIN, Role.TOURNAMENT_MANAGER)
def delete_match(match_id):
    match = Match.query.get_or_404(match_id)
    tournament_id = match.tournament_id
    db.session.delete(match)
    db.session.commit()
    log_action("Match deleted", "Match", match_id)
    flash("Match deleted successfully.", "success")
    return redirect(url_for("admin.manage_tournament", tournament_id=tournament_id))
