from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.extensions import db, csrf
from app.models.user import User
from app.models.team import Team
from app.models.tournament import Tournament, TournamentRegistration
from app.models.match import Match, MatchResult
from app.models.payment import Payment
from app.models.dispute import Dispute
from app.utils.security import generate_registration_code
from app.utils.audit import log_action

tournaments_bp = Blueprint("tournaments", __name__, template_folder="../templates/main")


@tournaments_bp.route("/")
def list_tournaments():
    search = request.args.get("search", "").strip()
    status = request.args.get("status", "").strip()
    mode = request.args.get("mode", "").strip()
    page = request.args.get("page", 1, type=int)

    query = Tournament.query

    if search:
        query = query.filter(Tournament.name.ilike(f"%{search}%"))
    if status:
        query = query.filter(Tournament.status == status)
    if mode:
        query = query.filter(Tournament.game_mode.ilike(f"%{mode}%"))

    tournaments = query.order_by(Tournament.start_time.desc()).paginate(page=page, per_page=12, error_out=False)

    return render_template(
        "main/tournaments.html",
        tournaments=tournaments,
        search=search,
        status=status,
        mode=mode,
        now=datetime.utcnow()
    )


@tournaments_bp.route("/<slug>")
def detail(slug):
    tournament = Tournament.query.filter_by(slug=slug).first_or_404()
    
    # Auto-update status if deadline has passed and still open
    if tournament.status == "registration_open" and tournament.registration_deadline <= datetime.utcnow():
        tournament.status = "closed"
        db.session.commit()

    teams = []
    my_registration = None
    my_payment = None

    if current_user.is_authenticated:
        teams = Team.query.filter_by(captain_id=current_user.id, is_active=True).order_by(Team.name).all()
        my_registration = TournamentRegistration.query.filter_by(
            tournament_id=tournament.id, registered_by_id=current_user.id
        ).first()
        if my_registration:
            my_payment = my_registration.payment

    # Matches for this tournament
    matches = tournament.matches.order_by(Match.round_number.asc(), Match.match_number.asc()).all()

    # Confirmed registered teams
    confirmed_registrations = tournament.registrations.filter_by(status="confirmed").all()

    # Leaderboard calculation
    results = (
        MatchResult.query.join(Match)
        .filter(Match.tournament_id == tournament.id, MatchResult.status == "verified")
        .all()
    )
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
            }
        )
        row["matches"] += 1
        row["wins"] += 1 if result.placement == 1 else 0
        row["kills"] += result.kills
        row["placement_points"] += result.placement_points
        row["kill_points"] += result.kill_points
        row["total_points"] += result.total_points

    leaderboard = sorted(board.values(), key=lambda r: (-r["total_points"], -r["kills"]))
    for rank, item in enumerate(leaderboard, 1):
        item["rank"] = rank

    # Disputes for this tournament (moderators or team captains)
    disputes = []
    if current_user.is_authenticated and current_user.is_admin():
        disputes = Dispute.query.join(Match).filter(Match.tournament_id == tournament.id).all()

    # Occupied slots calculation (1-48)
    occupied_slots = [r.slot_number for r in tournament.registrations.all() if r.slot_number]

    return render_template(
        "main/tournament_detail.html",
        tournament=tournament,
        teams=teams,
        my_registration=my_registration,
        my_payment=my_payment,
        matches=matches,
        confirmed_registrations=confirmed_registrations,
        leaderboard=leaderboard,
        disputes=disputes,
        occupied_slots=occupied_slots,
        now=datetime.utcnow(),
    )


@tournaments_bp.route("/<slug>/join", methods=["POST"])
@csrf.exempt
@login_required
def join(slug):
    tournament = Tournament.query.filter_by(slug=slug).first_or_404()
    
    is_json_req = request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if request.is_json:
        data = request.get_json() or {}
        team_id = data.get("team_id")
        slot_number = data.get("slot_number")
        in_game_name = str(data.get("in_game_name", "")).strip()
    else:
        team_id = request.form.get("team_id", type=int)
        slot_number = request.form.get("slot_number", type=int)
        in_game_name = request.form.get("in_game_name", "").strip()

    # Fallback to user's first team if team_id not passed
    if not team_id:
        user_team = Team.query.filter_by(captain_id=current_user.id, is_active=True).first()
        if user_team:
            team_id = user_team.id

    team = Team.query.filter_by(id=team_id, captain_id=current_user.id, is_active=True).first()

    if not team:
        msg = "Choose one of your active teams where you are the Captain to register."
        if is_json_req:
            return jsonify({"success": False, "message": msg}), 400
        flash(msg, "danger")
        return redirect(url_for("tournaments.detail", slug=slug))

    if tournament.status != "registration_open" or tournament.registration_deadline <= datetime.utcnow():
        msg = "Registration for this tournament is closed."
        if is_json_req:
            return jsonify({"success": False, "message": msg}), 400
        flash(msg, "danger")
        return redirect(url_for("tournaments.detail", slug=slug))

    if tournament.slots_left <= 0:
        msg = "This tournament is already full."
        if is_json_req:
            return jsonify({"success": False, "message": msg}), 400
        flash(msg, "danger")
        return redirect(url_for("tournaments.detail", slug=slug))

    if TournamentRegistration.query.filter_by(tournament_id=tournament.id, team_id=team.id).first():
        msg = "This team is already registered for this tournament."
        if is_json_req:
            return jsonify({"success": False, "message": msg}), 400
        flash(msg, "warning")
        return redirect(url_for("tournaments.detail", slug=slug))

    # Minimum roster validation
    if team.members.count() < 1:
        msg = "Your team must have at least 1 player to register."
        if is_json_req:
            return jsonify({"success": False, "message": msg}), 400
        flash(msg, "danger")
        return redirect(url_for("tournaments.detail", slug=slug))

    fee = int(tournament.entry_fee or 0)
    
    # 1. Row Locking (FOR UPDATE) & Concurrency Validation
    try:
        user_row = User.query.filter_by(id=current_user.id).with_for_update().first()
        user_coins = user_row.coins_balance or 0

        # Check if slot is already booked with row lock
        if slot_number:
            slot_taken = TournamentRegistration.query.filter_by(
                tournament_id=tournament.id, slot_number=slot_number
            ).with_for_update().first()
            if slot_taken:
                msg = f"Slot #{slot_number} is already booked by another player. Please select a different slot."
                if is_json_req:
                    return jsonify({"success": False, "message": msg}), 409
                flash(msg, "danger")
                return redirect(url_for("tournaments.detail", slug=slug))

        if fee > 0:
            if user_coins < fee:
                msg = f"Insufficient Coins! Required: {fee} Coins, but your available balance is {user_coins} Coins. Please Top-Up."
                if is_json_req:
                    return jsonify({
                        "success": False,
                        "error_code": "INSUFFICIENT_COINS",
                        "message": msg,
                        "required_coins": fee,
                        "available_coins": user_coins
                    }), 400
                flash(msg, "danger")
                return redirect(url_for("tournaments.detail", slug=slug))

            # Deduct Virtual Coins from user's coins_balance
            user_row.coins_balance = user_coins - fee

            # Record Wallet Transaction for transparency
            wallet = current_user.get_wallet()
            from app.models.wallet import WalletTransaction
            tx = WalletTransaction(
                wallet_id=wallet.id,
                transaction_type="tournament_entry",
                amount=-fee,
                balance_after=user_row.coins_balance,
                status="SUCCESS",
                description=f"Coins entry fee deduction for {tournament.name} (Slot #{slot_number or 'Auto'})",
                reference_id=f"T-{tournament.id}-S-{slot_number or 0}"
            )
            db.session.add(tx)

        registration = TournamentRegistration(
            registration_code=generate_registration_code(),
            tournament_id=tournament.id,
            team_id=team.id,
            registered_by_id=current_user.id,
            slot_number=slot_number,
            in_game_name=in_game_name or current_user.username,
            status="confirmed",
        )
        db.session.add(registration)
        db.session.commit()

    except Exception as e:
        db.session.rollback()
        msg = "Race condition detected! Slot was reserved micro-seconds earlier by another player." if "uq_tournament_slot" in str(e) else str(e)
        if is_json_req:
            return jsonify({"success": False, "message": msg}), 409
        flash(msg, "danger")
        return redirect(url_for("tournaments.detail", slug=slug))

    log_action(f"Tournament slot #{slot_number} booked by User #{current_user.id} for {tournament.name}", "TournamentRegistration", registration.id)
    success_msg = f"🎉 MATCH BOOKED SUCCESSFULLY! {fee} Coins deducted. Position #{slot_number or 'Auto'} confirmed! Remaining Balance: {current_user.coins_balance} Coins."

    if is_json_req:
        return jsonify({
            "success": True,
            "message": success_msg,
            "deducted_coins": fee,
            "remaining_coins": current_user.coins_balance,
            "registration_code": registration.registration_code,
            "slot_number": slot_number
        })

    flash(success_msg, "success")
    return redirect(url_for("tournaments.detail", slug=slug))
