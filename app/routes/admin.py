from datetime import datetime, timedelta
import io
import re

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user
from app.extensions import db, socketio
from app.models.audit import AuditLog
from app.models.dispute import Dispute
from app.models.match import Match, MatchResult, Room
from app.models.notification import Announcement, Notification
from app.models.payment import Payment
from app.models.player import Achievement, PlayerStatistic
from app.models.prize import Prize
from app.models.support import SupportMessage, SupportTicket
from app.models.team import Team
from app.models.tournament import ScoringRule, Tournament, TournamentRegistration
from app.models.user import Role, User
from app.services.report_service import (
    generate_disputes_csv,
    generate_disputes_pdf,
    generate_payments_csv,
    generate_payments_pdf,
    generate_prizes_csv,
    generate_prizes_pdf,
    generate_registrations_csv,
    generate_registrations_pdf,
    generate_results_csv,
    generate_results_pdf,
    generate_teams_csv,
    generate_teams_pdf,
    generate_tournaments_csv,
    generate_tournaments_pdf,
    generate_users_csv,
    generate_users_pdf,
)
from app.services.tournament_service import (
    auto_assign_teams_to_match,
    broadcast_tournament_notification,
    calculate_result,
    notify_user,
    verify_result,
)
from app.utils.audit import log_action
from app.utils.decorators import roles_required
from app.utils.security import save_uploaded_image

admin_bp = Blueprint("admin", __name__, template_folder="../templates/admin")

FREE_FIRE_MAPS = [
    "Bermuda",
    "Bermuda Remastered",
    "Purgatory",
    "Kalahari",
    "Alpine",
    "Nexterra",
    "Solara",
]
FREE_FIRE_MODES = [
    "Battle Royale - Solo",
    "Battle Royale - Duo",
    "Battle Royale - Squad",
    "Clash Squad",
    "Lone Wolf",
    "Craftland",
    "Rush Hour",
    "Big Head",
]


def _unique_slug(name, exclude_id=None):
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "tournament"
    slug = base[:130]
    counter = 2
    while True:
        query = Tournament.query.filter_by(slug=slug)
        if exclude_id:
            query = query.filter(Tournament.id != exclude_id)
        if not query.first():
            return slug
        suffix = f"-{counter}"
        slug = f"{base[:140 - len(suffix)]}{suffix}"
        counter += 1


# ---------- Admin Dashboard & Analytics ----------

@admin_bp.route("/")
@roles_required(Role.SUPER_ADMIN, Role.TOURNAMENT_MANAGER, Role.MODERATOR, Role.FINANCE_MANAGER)
def dashboard():
    total_revenue = (
        db.session.query(db.func.coalesce(db.func.sum(Payment.amount), 0))
        .filter(Payment.status == "verified")
        .scalar()
    )
    total_prize_paid = (
        db.session.query(db.func.coalesce(db.func.sum(Prize.amount), 0))
        .filter(Prize.status == "paid")
        .scalar()
    )

    stats = {
        "total_players": User.query.count(),
        "total_teams": Team.query.count(),
        "total_tournaments": Tournament.query.count(),
        "live_matches": Match.query.filter_by(status="live").count(),
        "total_matches": Match.query.count(),
        "pending_payments": Payment.query.filter(Payment.status.in_(["pending", "verification_required"])).count(),
        "pending_results": MatchResult.query.filter(MatchResult.status.in_(["pending", "under_review"])).count(),
        "open_disputes": Dispute.query.filter_by(status="open").count(),
        "open_tickets": SupportTicket.query.filter_by(status="open").count(),
        "total_revenue": total_revenue,
        "total_prize_paid": total_prize_paid,
    }

    recent_tournaments = Tournament.query.order_by(Tournament.created_at.desc()).limit(6).all()
    recent_registrations = TournamentRegistration.query.order_by(TournamentRegistration.created_at.desc()).limit(8).all()
    recent_payments = Payment.query.order_by(Payment.created_at.desc()).limit(6).all()

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        recent_tournaments=recent_tournaments,
        recent_registrations=recent_registrations,
        recent_payments=recent_payments,
    )


@admin_bp.route("/analytics")
@roles_required(Role.SUPER_ADMIN, Role.TOURNAMENT_MANAGER, Role.FINANCE_MANAGER)
def analytics():
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)

    total_revenue = (
        db.session.query(db.func.coalesce(db.func.sum(Payment.amount), 0))
        .filter(Payment.status == "verified")
        .scalar()
    )
    revenue_this_month = (
        db.session.query(db.func.coalesce(db.func.sum(Payment.amount), 0))
        .filter(Payment.status == "verified", Payment.created_at >= month_start)
        .scalar()
    )

    new_players_this_month = User.query.filter(User.created_at >= month_start).count()
    live_tournaments = Tournament.query.filter_by(status="live").count()

    stats = {
        "total_players": User.query.count(),
        "new_players_this_month": new_players_this_month,
        "total_tournaments": Tournament.query.count(),
        "live_tournaments": live_tournaments,
        "total_revenue": total_revenue,
        "revenue_this_month": revenue_this_month,
        "total_matches": Match.query.count(),
        "pending_payments": Payment.query.filter(Payment.status.in_(["pending", "verification_required"])).count(),
        "payments_verified": Payment.query.filter_by(status="verified").count(),
        "payments_pending": Payment.query.filter(Payment.status.in_(["pending", "verification_required"])).count(),
        "payments_rejected": Payment.query.filter_by(status="rejected").count(),
        "open_disputes": Dispute.query.filter_by(status="open").count(),
        "open_tickets": SupportTicket.query.filter_by(status="open").count(),
    }

    # Revenue last 6 months
    revenue_labels = []
    revenue_data = []
    reg_labels = []
    reg_data = []
    for i in range(5, -1, -1):
        m_date = now - timedelta(days=i * 30)
        lbl = m_date.strftime("%b %Y")
        revenue_labels.append(lbl)
        reg_labels.append(lbl)
        
        m_rev = (
            db.session.query(db.func.coalesce(db.func.sum(Payment.amount), 0))
            .filter(Payment.status == "verified", db.extract("month", Payment.created_at) == m_date.month, db.extract("year", Payment.created_at) == m_date.year)
            .scalar()
        )
        revenue_data.append(float(m_rev))

        m_regs = TournamentRegistration.query.filter(
            db.extract("month", TournamentRegistration.created_at) == m_date.month,
            db.extract("year", TournamentRegistration.created_at) == m_date.year
        ).count()
        reg_data.append(m_regs)

    dispute_data = [
        Dispute.query.filter_by(status="open").count(),
        Dispute.query.filter_by(status="under_review").count(),
        Dispute.query.filter(Dispute.status.in_(["resolved", "accepted"])).count(),
        Dispute.query.filter_by(status="rejected").count(),
    ]

    top_players = PlayerStatistic.query.order_by(PlayerStatistic.total_points.desc()).limit(5).all()
    top_teams = Team.query.filter_by(is_active=True).limit(5).all()

    return render_template(
        "admin/analytics.html",
        stats=stats,
        revenue_labels=revenue_labels,
        revenue_data=revenue_data,
        reg_labels=reg_labels,
        reg_data=reg_data,
        dispute_data=dispute_data,
        top_players=top_players,
        top_teams=top_teams,
    )


# ---------- Tournaments Management ----------

@admin_bp.route("/tournaments")
@roles_required(Role.SUPER_ADMIN, Role.TOURNAMENT_MANAGER)
def list_tournaments():
    tournaments = Tournament.query.order_by(Tournament.start_time.desc()).all()
    return render_template("admin/tournaments.html", tournaments=tournaments)


@admin_bp.route("/tournaments/create", methods=["GET", "POST"])
@roles_required(Role.SUPER_ADMIN, Role.TOURNAMENT_MANAGER, Role.MODERATOR, Role.FINANCE_MANAGER)
def create_tournament():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        game_mode = request.form.get("game_mode", "")
        map_name = request.form.get("map_name", "")
        tournament_type = request.form.get("tournament_type", "")
        try:
            deadline = datetime.strptime(request.form.get("registration_deadline", ""), "%Y-%m-%dT%H:%M")
            start = datetime.strptime(request.form.get("start_time", ""), "%Y-%m-%dT%H:%M")
            max_teams = int(request.form.get("max_teams", "48"))
            entry_fee = float(request.form.get("entry_fee", "0"))
            prize_pool = float(request.form.get("prize_pool", "0"))
            per_kill_prize = float(request.form.get("per_kill_prize", "5.0"))

            if not name or len(name) > 120:
                raise ValueError("Please provide a valid tournament name.")
            if deadline >= start:
                raise ValueError("Registration deadline must be before tournament start time.")

            banner_url = "default_banner.jpg"
            banner_file = request.files.get("banner")
            if banner_file and banner_file.filename:
                uploaded = save_uploaded_image(banner_file, "tournament_banners")
                if uploaded:
                    banner_url = uploaded

            tournament = Tournament(
                name=name,
                slug=_unique_slug(name),
                description=request.form.get("description", "").strip() or None,
                rules=request.form.get("rules", "").strip() or None,
                banner_url=banner_url,
                tournament_type=tournament_type,
                game_mode=game_mode,
                map_name=map_name,
                max_teams=max_teams,
                entry_fee=entry_fee,
                prize_pool=prize_pool,
                per_kill_prize=per_kill_prize,
                registration_deadline=deadline,
                start_time=start,
                status="registration_open",
                created_by_id=current_user.id,
            )
            db.session.add(tournament)
            db.session.flush()

            # Seed default scoring rules (1st: 12, 2nd: 9, 3rd: 8, 4th: 7, 5th: 6, 6th: 5, 7th: 4, 8th: 3, 9th: 2, 10th: 1)
            default_rules = [(1, 12), (2, 9), (3, 8), (4, 7), (5, 6), (6, 5), (7, 4), (8, 3), (9, 2), (10, 1)]
            for place, pts in default_rules:
                db.session.add(ScoringRule(tournament_id=tournament.id, placement=place, points=pts))

            db.session.commit()
            log_action("Tournament created", "Tournament", tournament.id)
            flash("Tournament created and published successfully!", "success")
            return redirect(url_for("admin.manage_tournament", tournament_id=tournament.id))
        except (TypeError, ValueError) as error:
            db.session.rollback()
            flash(str(error) or "Please verify the tournament fields.", "danger")

    return render_template("admin/create_tournament.html", maps=FREE_FIRE_MAPS, modes=FREE_FIRE_MODES)


@admin_bp.route("/tournaments/<int:tournament_id>/edit", methods=["GET", "POST"])
@roles_required(Role.SUPER_ADMIN, Role.TOURNAMENT_MANAGER, Role.MODERATOR, Role.FINANCE_MANAGER)
def edit_tournament(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        game_mode = request.form.get("game_mode", "")
        map_name = request.form.get("map_name", "")
        tournament_type = request.form.get("tournament_type", "")
        status = request.form.get("status", tournament.status)

        try:
            deadline = datetime.strptime(request.form.get("registration_deadline", ""), "%Y-%m-%dT%H:%M")
            start = datetime.strptime(request.form.get("start_time", ""), "%Y-%m-%dT%H:%M")
            max_teams = int(request.form.get("max_teams", "48"))
            entry_fee = float(request.form.get("entry_fee", "0"))
            prize_pool = float(request.form.get("prize_pool", "0"))
            per_kill_prize = float(request.form.get("per_kill_prize", "5.0"))

            if not name:
                raise ValueError("Tournament name cannot be blank.")

            tournament.name = name
            tournament.slug = _unique_slug(name, exclude_id=tournament.id)
            tournament.tournament_type = tournament_type
            tournament.game_mode = game_mode
            tournament.map_name = map_name
            tournament.max_teams = max_teams
            tournament.entry_fee = entry_fee
            tournament.prize_pool = prize_pool
            tournament.per_kill_prize = per_kill_prize
            tournament.registration_deadline = deadline
            tournament.start_time = start
            tournament.status = status
            tournament.description = request.form.get("description", "").strip() or None
            tournament.rules = request.form.get("rules", "").strip() or None

            banner_file = request.files.get("banner")
            if banner_file and banner_file.filename:
                uploaded = save_uploaded_image(banner_file, "tournament_banners")
                if uploaded:
                    tournament.banner_url = uploaded

            db.session.commit()
            log_action("Tournament updated", "Tournament", tournament.id)
            flash("Tournament updated successfully.", "success")
            return redirect(url_for("admin.manage_tournament", tournament_id=tournament.id))
        except (TypeError, ValueError) as error:
            db.session.rollback()
            flash(str(error), "danger")

    return render_template(
        "admin/edit_tournament.html",
        tournament=tournament,
        maps=FREE_FIRE_MAPS,
        modes=FREE_FIRE_MODES,
    )


@admin_bp.route("/tournaments/<int:tournament_id>")
@roles_required(Role.SUPER_ADMIN, Role.TOURNAMENT_MANAGER)
def manage_tournament(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    registrations = tournament.registrations.order_by(TournamentRegistration.created_at.desc()).all()
    matches = tournament.matches.order_by(Match.round_number.asc(), Match.match_number.asc()).all()
    prizes = Prize.query.filter_by(tournament_id=tournament.id).order_by(Prize.rank.asc()).all()
    return render_template(
        "admin/manage_tournament.html",
        tournament=tournament,
        registrations=registrations,
        matches=matches,
        prizes=prizes,
        maps=FREE_FIRE_MAPS,
    )


@admin_bp.route("/tournaments/<int:tournament_id>/status", methods=["POST"])
@roles_required(Role.SUPER_ADMIN, Role.TOURNAMENT_MANAGER)
def set_tournament_status(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    new_status = request.form.get("status")
    if new_status in {"registration_open", "closing_soon", "live", "completed", "closed"}:
        tournament.status = new_status
        db.session.commit()
        log_action(f"Tournament status changed to {new_status}", "Tournament", tournament.id)
        broadcast_tournament_notification(
            tournament.id,
            f"Tournament '{tournament.name}' status is now {new_status.replace('_', ' ').title()}.",
            link=f"/tournaments/{tournament.slug}",
            icon="🎮",
        )
        flash(f"Tournament status updated to '{new_status}'.", "success")
    return redirect(url_for("admin.manage_tournament", tournament_id=tournament.id))


@admin_bp.route("/tournaments/<int:tournament_id>/delete", methods=["POST"])
@roles_required(Role.SUPER_ADMIN)
def delete_tournament(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    db.session.delete(tournament)
    db.session.commit()
    log_action("Tournament deleted", "Tournament", tournament_id)
    flash("Tournament deleted permanently.", "info")
    return redirect(url_for("admin.list_tournaments"))


# ---------- Room Management UI & CRUD ----------

@admin_bp.route("/rooms")
@roles_required(Role.SUPER_ADMIN, Role.TOURNAMENT_MANAGER)
def room_management():
    tournament_id = request.args.get("tournament_id", type=int)
    tournaments = Tournament.query.order_by(Tournament.start_time.desc()).all()
    
    selected_tournament = None
    if tournament_id:
        selected_tournament = Tournament.query.get(tournament_id)

    query = Match.query
    if tournament_id:
        query = query.filter_by(tournament_id=tournament_id)
    matches = query.order_by(Match.scheduled_date.asc(), Match.scheduled_time.asc()).all()

    return render_template(
        "admin/room_management.html",
        matches=matches,
        tournaments=tournaments,
        selected_tournament=selected_tournament,
    )


@admin_bp.route("/rooms/<int:room_id>/delete", methods=["POST"])
@roles_required(Role.SUPER_ADMIN, Role.TOURNAMENT_MANAGER)
def delete_room(room_id):
    room = Room.query.get_or_404(room_id)
    match = room.match
    if match:
        match.room_id = None
        match.status = "scheduled"
    db.session.delete(room)
    db.session.commit()
    log_action("Room deleted", "Room", room_id)
    flash("Room credentials deleted successfully.", "info")
    return redirect(request.referrer or url_for("admin.room_management"))


@admin_bp.route("/rooms/<int:room_id>/release-now", methods=["POST"])
@roles_required(Role.SUPER_ADMIN, Role.TOURNAMENT_MANAGER)
def release_room_now(room_id):
    room = Room.query.get_or_404(room_id)
    room.status = "released"
    room.release_time = datetime.utcnow()
    if room.match:
        room.match.status = "room_released"
        try:
            socketio.emit(
                "room_released",
                {"match_id": room.match.id, "room_id": room.room_id_code, "password": room.room_password},
                room=f"tournament:{room.match.tournament_id}",
            )
        except Exception:
            pass
    db.session.commit()
    log_action("Room manually released", "Room", room_id)
    flash("Room credentials released immediately to all players!", "success")
    return redirect(request.referrer or url_for("admin.room_management"))


# ---------- Proofs & Evidence Gallery ----------

@admin_bp.route("/proofs")
@roles_required(Role.SUPER_ADMIN, Role.MODERATOR, Role.FINANCE_MANAGER)
def list_proofs():
    proof_type = request.args.get("type", "").strip()
    proofs = []

    if not proof_type or proof_type == "payment":
        payments = Payment.query.filter(Payment.proof_path.isnot(None)).order_by(Payment.created_at.desc()).limit(30).all()
        for p in payments:
            proofs.append({
                "id": p.id,
                "category": "payment",
                "title": f"Payment #{p.id} — ₹{p.amount} ({p.registration.tournament.name if p.registration and p.registration.tournament else 'N/A'})",
                "file_path": p.proof_path,
                "status": p.status,
                "created_at": p.created_at,
                "uploaded_by": p.registration.team.captain.username if p.registration and p.registration.team and p.registration.team.captain else None,
                "action_url": url_for("admin.list_payments", search=p.transaction_id or ""),
            })

    if not proof_type or proof_type == "result":
        results = MatchResult.query.filter(MatchResult.proof_url.isnot(None)).order_by(MatchResult.created_at.desc()).limit(30).all()
        for r in results:
            proofs.append({
                "id": r.id,
                "category": "result",
                "title": f"Scoreboard Result #{r.id} — {r.team.name if r.team else 'Team'} (Match #{r.match.match_number if r.match else '?'})",
                "file_path": r.proof_url,
                "status": r.status,
                "created_at": r.created_at,
                "uploaded_by": r.team.captain.username if r.team and r.team.captain else None,
                "action_url": url_for("admin.list_results"),
            })

    if not proof_type or proof_type == "dispute":
        disputes = Dispute.query.filter(Dispute.proof_url.isnot(None)).order_by(Dispute.created_at.desc()).limit(30).all()
        for d in disputes:
            proofs.append({
                "id": d.id,
                "category": "dispute",
                "title": f"Dispute #{d.id} — {d.reason} ({d.team.name if d.team else 'Team'})",
                "file_path": d.proof_url,
                "status": d.status,
                "created_at": d.created_at,
                "uploaded_by": d.team.captain.username if d.team and d.team.captain else None,
                "action_url": url_for("admin.list_disputes"),
            })

    # Sort all by created_at desc
    proofs.sort(key=lambda x: x["created_at"] or datetime.min, reverse=True)
    return render_template("admin/proofs.html", proofs=proofs, proof_type=proof_type)


# ---------- Payments Verification Management ----------

@admin_bp.route("/payments/update-qr", methods=["POST"])
@roles_required(Role.SUPER_ADMIN, Role.FINANCE_MANAGER)
def update_qr_settings():
    from app.models.setting import SystemSetting
    from app.utils.uploads import save_proof

    upi_id = request.form.get("upi_id", "").strip()
    upi_name = request.form.get("upi_name", "").strip()

    if upi_id:
        SystemSetting.set("admin_upi_id", upi_id)
    if upi_name:
        SystemSetting.set("admin_upi_name", upi_name)

    qr_file = request.files.get("qr_code")
    if qr_file and qr_file.filename:
        try:
            saved_file = save_proof(qr_file, category="qr_codes")
            if saved_file:
                SystemSetting.set("admin_qr_code", saved_file)
        except Exception as e:
            flash(f"QR Code Upload Error: {str(e)}", "danger")
            return redirect(url_for("admin.list_payments"))

    log_action("Admin updated UPI payment settings & QR code", "SystemSetting", current_user.id)
    flash("Payment Gateway QR Code & UPI details updated successfully!", "success")
    return redirect(url_for("admin.list_payments"))


@admin_bp.route("/payments")
@roles_required(Role.SUPER_ADMIN, Role.TOURNAMENT_MANAGER, Role.FINANCE_MANAGER, Role.MODERATOR)
def list_payments():
    from app.models.wallet import WalletTransaction
    status = request.args.get("status", "").strip()
    search = request.args.get("search", "").strip()
    page = request.args.get("page", 1, type=int)

    query = Payment.query.join(TournamentRegistration).join(Tournament)
    if status:
        query = query.filter(Payment.status == status)
    if search:
        query = query.filter(
            (Payment.transaction_id.ilike(f"%{search}%"))
            | (TournamentRegistration.registration_code.ilike(f"%{search}%"))
            | (Tournament.name.ilike(f"%{search}%"))
        )

    payments = query.order_by(Payment.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    
    # Query wallet deposit requests (both pending and recent)
    deposit_query = WalletTransaction.query.filter(WalletTransaction.transaction_type.ilike("deposit"))
    if status:
        st_map = {"pending": "pending", "verified": "SUCCESS", "confirmed": "SUCCESS", "rejected": "REJECTED"}
        if status in st_map:
            deposit_query = deposit_query.filter(WalletTransaction.status.ilike(st_map[status]))
    if search:
        deposit_query = deposit_query.filter(WalletTransaction.reference_id.ilike(f"%{search}%"))
    wallet_deposits = deposit_query.order_by(WalletTransaction.created_at.desc()).limit(50).all()

    return render_template(
        "admin/payments.html",
        payments=payments,
        wallet_deposits=wallet_deposits,
        status=status,
        search=search
    )


@admin_bp.route("/payments/<int:payment_id>/review", methods=["POST"])
@roles_required(Role.SUPER_ADMIN, Role.TOURNAMENT_MANAGER, Role.FINANCE_MANAGER, Role.MODERATOR)
def review_payment(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    decision = request.form.get("decision")
    if decision not in {"verified", "rejected"}:
        flash("Invalid payment decision.", "danger")
    else:
        payment.status = decision
        payment.verified_by_id = current_user.id
        payment.verified_at = datetime.utcnow()
        payment.transaction_id = request.form.get("transaction_id", "").strip() or payment.transaction_id
        payment.rejection_reason = (
            request.form.get("rejection_reason", "").strip() if decision == "rejected" else None
        )
        payment.registration.status = "confirmed" if decision == "verified" else "rejected"

        db.session.commit()
        log_action(f"Payment {decision}", "Payment", payment.id)

        # Notify the captain
        notify_user(
            payment.registration.registered_by_id,
            f"Payment of ₹{payment.amount} for {payment.registration.tournament.name} was {decision.upper()}."
            + (f" Reason: {payment.rejection_reason}" if payment.rejection_reason else ""),
            link=f"/tournaments/{payment.registration.tournament.slug}",
            icon="💳",
        )
        flash(f"Payment #{payment.id} has been marked as {decision}.", "success")

    return redirect(request.referrer or url_for("admin.list_payments"))


@admin_bp.route("/deposits/<int:deposit_id>/review", methods=["POST"])
@roles_required(Role.SUPER_ADMIN, Role.TOURNAMENT_MANAGER, Role.FINANCE_MANAGER, Role.MODERATOR)
def review_deposit(deposit_id):
    from app.models.wallet import WalletTransaction
    tx = WalletTransaction.query.get_or_404(deposit_id)
    decision = request.form.get("decision")

    if decision in ["yes", "approved", "verified"]:
        # STRICT DUPLICATE UTR CHECK IN ADMIN PANEL
        if tx.reference_id:
            ref_clean = tx.reference_id.strip()
            dup = WalletTransaction.query.filter(
                WalletTransaction.reference_id.ilike(ref_clean),
                WalletTransaction.id != tx.id,
                WalletTransaction.status == "SUCCESS"
            ).first()

            if dup:
                tx.status = "REJECTED"
                tx.rejection_reason = f"Duplicate UTR ({ref_clean}) already credited in Deposit #{dup.id}."
                db.session.commit()
                flash(f"❌ CANNOT APPROVE: Transaction UTR ({ref_clean}) has already been used in Deposit #{dup.id}! Marked as REJECTED.", "danger")
                return redirect(request.referrer or url_for("admin.list_payments"))

        tx.status = "SUCCESS"
        wallet = tx.wallet
        amt = float(tx.amount or 0)
        coins_to_add = int(amt)

        wallet.available_balance = float(wallet.available_balance or 0) + amt
        wallet.total_added = float(wallet.total_added or 0) + amt
        tx.balance_after = wallet.total_balance

        # Also credit user's coins_balance (₹1 = 1 Virtual Coin)
        user = wallet.user
        if user:
            user.coins_balance = (user.coins_balance or 0) + coins_to_add

        db.session.commit()

        log_action(f"Admin APPROVED wallet deposit of ⚡{coins_to_add} Virtual Coins for User #{wallet.user_id}", "WalletTransaction", tx.id)
        notify_user(
            wallet.user_id,
            f"🎉 DEPOSIT APPROVED! ⚡{coins_to_add} Virtual Coins (₹{amt}) have been credited to your profile balance.",
            link="/payments/my",
            icon="⚡"
        )
        flash(f"✅ Deposit Request #{tx.id} APPROVED! ⚡{coins_to_add} Virtual Coins credited to user's wallet.", "success")
    elif decision in ["no", "rejected"]:
        tx.status = "REJECTED"
        tx.rejection_reason = request.form.get("rejection_reason", "").strip() or "Payment screenshot or UTR invalid."
        db.session.commit()

        log_action(f"Admin REJECTED wallet deposit for User #{tx.wallet.user_id}", "WalletTransaction", tx.id)
        notify_user(
            tx.wallet.user_id,
            f"❌ DEPOSIT REJECTED! Request for ⚡{tx.amount} Tokens was rejected."
            + (f" Reason: {tx.rejection_reason}" if tx.rejection_reason else ""),
            link="/payments/my",
            icon="❌"
        )
        flash(f"❌ Deposit Request #{tx.id} REJECTED.", "warning")
    else:
        flash("Invalid deposit decision.", "danger")

    return redirect(request.referrer or url_for("admin.list_payments"))


@admin_bp.route("/deposits/bulk-action", methods=["POST"])
@roles_required(Role.SUPER_ADMIN, Role.TOURNAMENT_MANAGER, Role.FINANCE_MANAGER, Role.MODERATOR)
def bulk_deposit_action():
    from app.models.wallet import WalletTransaction
    deposit_ids = request.form.getlist("deposit_ids")
    action = request.form.get("action")

    if not deposit_ids:
        flash("No deposits selected. Please check at least one box.", "warning")
        return redirect(request.referrer or url_for("admin.list_payments"))

    deposit_ids = [int(i) for i in deposit_ids if i.isdigit()]

    if action == "delete":
        txs = WalletTransaction.query.filter(WalletTransaction.id.in_(deposit_ids)).all()
        count = len(txs)
        for tx in txs:
            db.session.delete(tx)
        db.session.commit()
        log_action(f"Admin bulk deleted {count} deposit records", "WalletTransaction", 0)
        flash(f"🗑️ Successfully deleted {count} selected deposit records.", "info")

    elif action == "approve":
        txs = WalletTransaction.query.filter(WalletTransaction.id.in_(deposit_ids), WalletTransaction.status == "pending").all()
        count = 0
        for tx in txs:
            tx.status = "SUCCESS"
            wallet = tx.wallet
            amt = float(tx.amount or 0)
            coins = int(amt)
            wallet.available_balance = float(wallet.available_balance or 0) + amt
            wallet.total_added = float(wallet.total_added or 0) + amt
            tx.balance_after = wallet.total_balance
            if wallet.user:
                wallet.user.coins_balance = (wallet.user.coins_balance or 0) + coins
            notify_user(wallet.user_id, f"🎉 DEPOSIT APPROVED! ⚡{coins} Virtual Coins credited.", link="/payments/my", icon="⚡")
            count += 1
        db.session.commit()
        flash(f"✅ Successfully approved {count} deposit requests.", "success")

    elif action == "reject":
        txs = WalletTransaction.query.filter(WalletTransaction.id.in_(deposit_ids), WalletTransaction.status == "pending").all()
        count = 0
        for tx in txs:
            tx.status = "REJECTED"
            tx.rejection_reason = "Bulk rejected by admin."
            notify_user(tx.wallet.user_id, f"❌ DEPOSIT REJECTED! Request for ⚡{tx.amount} Tokens was rejected.", link="/payments/my", icon="❌")
            count += 1
        db.session.commit()
        flash(f"❌ Rejected {count} deposit requests.", "warning")

    return redirect(request.referrer or url_for("admin.list_payments"))


@admin_bp.route("/deposits/<int:deposit_id>/delete", methods=["POST"])
@roles_required(Role.SUPER_ADMIN, Role.TOURNAMENT_MANAGER, Role.FINANCE_MANAGER, Role.MODERATOR)
def delete_deposit(deposit_id):
    from app.models.wallet import WalletTransaction
    tx = WalletTransaction.query.get_or_404(deposit_id)
    db.session.delete(tx)
    db.session.commit()
    log_action(f"Admin deleted deposit transaction #{deposit_id}", "WalletTransaction", deposit_id)
    flash(f"🗑️ Deposit #{deposit_id} record deleted successfully.", "info")
    return redirect(request.referrer or url_for("admin.list_payments"))


@admin_bp.route("/payments/<int:payment_id>/delete", methods=["POST"])
@roles_required(Role.SUPER_ADMIN, Role.TOURNAMENT_MANAGER, Role.FINANCE_MANAGER, Role.MODERATOR)
def delete_payment(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    db.session.delete(payment)
    db.session.commit()
    log_action(f"Admin deleted payment #{payment_id}", "Payment", payment_id)
    flash(f"🗑️ Payment #{payment_id} record deleted successfully.", "info")
    return redirect(request.referrer or url_for("admin.list_payments"))


@admin_bp.route("/registrations/<int:reg_id>/delete", methods=["POST"])
@roles_required(Role.SUPER_ADMIN, Role.TOURNAMENT_MANAGER, Role.FINANCE_MANAGER, Role.MODERATOR)
def delete_registration(reg_id):
    reg = TournamentRegistration.query.get_or_404(reg_id)
    tourn_id = reg.tournament_id
    db.session.delete(reg)
    db.session.commit()
    log_action(f"Admin deleted tournament registration #{reg_id}", "TournamentRegistration", reg_id)
    flash(f"🗑️ Tournament registration #{reg_id} deleted successfully.", "info")
    return redirect(request.referrer or url_for("admin.manage_tournament", tournament_id=tourn_id))





# ---------- Results Verification Management ----------

@admin_bp.route("/results")
@roles_required(Role.SUPER_ADMIN, Role.TOURNAMENT_MANAGER)
def list_results():
    status = request.args.get("status", "").strip()
    query = MatchResult.query.join(Match)
    if status:
        query = query.filter(MatchResult.status == status)
    results = query.order_by(MatchResult.created_at.desc()).paginate(
        page=request.args.get("page", 1, type=int), per_page=20, error_out=False
    )
    return render_template("admin/results.html", results=results, status=status)


@admin_bp.route("/results/<int:result_id>/review", methods=["POST"])
@roles_required(Role.SUPER_ADMIN, Role.TOURNAMENT_MANAGER)
def review_result(result_id):
    result = MatchResult.query.get_or_404(result_id)
    decision = request.form.get("decision")
    if decision == "verified":
        try:
            placement = request.form.get("placement", type=int)
            kills = request.form.get("kills", type=int)
            if placement is not None and kills is not None:
                pp, kp, total = calculate_result(result.match, result.team_id, placement, kills)
                result.placement = placement
                result.kills = kills
                result.placement_points = pp
                result.kill_points = kp
                result.total_points = total

            verify_result(result, current_user.id)
            db.session.commit()
            log_action("Result verified", "MatchResult", result.id)
            flash("Result verified and leaderboard & player stats updated!", "success")
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")
    else:
        result.status = "rejected"
        result.rejection_reason = request.form.get("rejection_reason", "").strip() or "Result proof invalid."
        db.session.commit()
        log_action("Result rejected", "MatchResult", result.id)
        flash("Result rejected.", "warning")

    return redirect(request.referrer or url_for("admin.list_results"))


# ---------- Prize Distribution Management ----------

@admin_bp.route("/prizes", methods=["GET", "POST"])
@roles_required(Role.SUPER_ADMIN, Role.FINANCE_MANAGER)
def list_prizes():
    if request.method == "POST":
        tournament_id = request.form.get("tournament_id", type=int)
        team_id = request.form.get("team_id", type=int)
        rank = request.form.get("rank", type=int)
        amount = float(request.form.get("amount", "0"))
        
        if not tournament_id or not team_id or not rank or amount <= 0:
            flash("Please provide valid prize details.", "danger")
        else:
            prize = Prize(
                tournament_id=tournament_id,
                team_id=team_id,
                rank=rank,
                amount=amount,
                status="pending",
            )
            db.session.add(prize)
            db.session.commit()
            log_action("Prize allocated", "Prize", prize.id)
            flash(f"Rank #{rank} prize of ₹{amount} assigned.", "success")

    prizes = Prize.query.order_by(Prize.created_at.desc()).all()
    tournaments = Tournament.query.order_by(Tournament.start_time.desc()).all()
    teams = Team.query.filter_by(is_active=True).all()
    return render_template("admin/prizes.html", prizes=prizes, tournaments=tournaments, teams=teams)


@admin_bp.route("/prizes/<int:prize_id>/status", methods=["POST"])
@roles_required(Role.SUPER_ADMIN, Role.FINANCE_MANAGER)
def update_prize_status(prize_id):
    prize = Prize.query.get_or_404(prize_id)
    status = request.form.get("status")
    if status in {"pending", "processing", "paid", "rejected"}:
        prize.status = status
        if status == "paid":
            prize.payment_date = datetime.utcnow()
            prize.reference_id = request.form.get("reference_id", "").strip() or None
            if prize.team and prize.team.captain_id:
                notify_user(
                    prize.team.captain_id,
                    f"Prize money of ₹{prize.amount} for Rank #{prize.rank} in {prize.tournament.name} has been PAID! (Ref: {prize.reference_id or 'N/A'})",
                    icon="💰",
                )
        db.session.commit()
        log_action(f"Prize status changed to {status}", "Prize", prize.id)
        flash(f"Prize status updated to {status.title()}.", "success")
    return redirect(url_for("admin.list_prizes"))


# ---------- Disputes Moderation Center ----------

@admin_bp.route("/disputes")
@roles_required(Role.SUPER_ADMIN, Role.MODERATOR)
def list_disputes():
    status = request.args.get("status", "").strip()
    query = Dispute.query
    if status:
        query = query.filter_by(status=status)
    disputes = query.order_by(Dispute.created_at.desc()).all()
    return render_template("admin/disputes.html", disputes=disputes, status=status)


@admin_bp.route("/disputes/<int:dispute_id>/resolve", methods=["POST"])
@roles_required(Role.SUPER_ADMIN, Role.MODERATOR)
def resolve_dispute(dispute_id):
    dispute = Dispute.query.get_or_404(dispute_id)
    status = request.form.get("status")
    note = request.form.get("resolution_note", "").strip()

    if status in {"under_review", "accepted", "rejected", "resolved"}:
        dispute.status = status
        dispute.handled_by_id = current_user.id
        dispute.resolution_note = note or None
        db.session.commit()

        log_action(f"Dispute {status}", "Dispute", dispute.id)
        notify_user(
            dispute.raised_by_id,
            f"Your dispute on Match #{dispute.match.match_number} is now {status.upper()}."
            + (f" Note: {note}" if note else ""),
            link=f"/matches/{dispute.match_id}",
            icon="⚖️",
        )
        flash(f"Dispute marked as {status}.", "success")

    return redirect(url_for("admin.list_disputes"))


# ---------- Announcements Management ----------

@admin_bp.route("/announcements", methods=["GET", "POST"])
@roles_required(Role.SUPER_ADMIN, Role.TOURNAMENT_MANAGER)
def list_announcements():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        message = request.form.get("message", "").strip()
        priority = request.form.get("priority", "normal")
        if not title or not message:
            flash("Title and message are required.", "danger")
        else:
            announcement = Announcement(
                title=title[:150],
                message=message,
                priority=priority,
                created_by_id=current_user.id,
                is_active=True,
            )
            db.session.add(announcement)
            db.session.commit()
            log_action("Announcement published", "Announcement", announcement.id)
            try:
                socketio.emit(
                    "announcement",
                    {"title": announcement.title, "message": announcement.message, "priority": priority},
                )
            except Exception:
                pass
            flash("Announcement published across platform.", "success")

    announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return render_template("admin/announcements.html", announcements=announcements)


@admin_bp.route("/announcements/<int:announcement_id>/toggle", methods=["POST"])
@roles_required(Role.SUPER_ADMIN, Role.TOURNAMENT_MANAGER)
def toggle_announcement(announcement_id):
    ann = Announcement.query.get_or_404(announcement_id)
    ann.is_active = not ann.is_active
    db.session.commit()
    flash("Announcement status updated.", "info")
    return redirect(url_for("admin.list_announcements"))


@admin_bp.route("/announcements/<int:announcement_id>/delete", methods=["POST"])
@roles_required(Role.SUPER_ADMIN)
def delete_announcement(announcement_id):
    ann = Announcement.query.get_or_404(announcement_id)
    db.session.delete(ann)
    db.session.commit()
    flash("Announcement deleted.", "info")
    return redirect(url_for("admin.list_announcements"))


# ---------- Support Tickets Management ----------

@admin_bp.route("/support")
@roles_required(Role.SUPER_ADMIN, Role.MODERATOR)
def list_support():
    status = request.args.get("status", "").strip()
    category = request.args.get("category", "").strip()

    query = SupportTicket.query
    if status:
        query = query.filter_by(status=status)
    if category:
        query = query.filter_by(category=category)

    tickets = query.order_by(SupportTicket.created_at.desc()).all()
    return render_template("admin/support.html", tickets=tickets, status=status, category=category)


# ---------- Users & Roles Management ----------

@admin_bp.route("/users")
@roles_required(Role.SUPER_ADMIN)
def list_users():
    search = request.args.get("search", "").strip()
    role_filter = request.args.get("role", "").strip()
    page = request.args.get("page", 1, type=int)

    query = User.query
    if search:
        query = query.filter(
            (User.username.ilike(f"%{search}%"))
            | (User.email.ilike(f"%{search}%"))
            | (User.full_name.ilike(f"%{search}%"))
        )
    if role_filter:
        query = query.join(Role).filter(Role.name == role_filter)

    users = query.order_by(User.id.desc()).paginate(page=page, per_page=25, error_out=False)
    roles = Role.query.all()
    return render_template("admin/users.html", users=users, roles=roles, search=search, role_filter=role_filter)


@admin_bp.route("/users/<int:user_id>/role", methods=["POST"])
@roles_required(Role.SUPER_ADMIN)
def change_user_role(user_id):
    user = User.query.get_or_404(user_id)
    role_id = request.form.get("role_id", type=int)
    role = Role.query.get_or_404(role_id)

    user.role_id = role.id
    db.session.commit()
    log_action(f"Role changed to {role.name} for @{user.username}", "User", user.id)
    flash(f"Role for @{user.username} updated to '{role.name}'.", "success")
    return redirect(url_for("admin.list_users"))


@admin_bp.route("/users/<int:user_id>/toggle-active", methods=["POST"])
@roles_required(Role.SUPER_ADMIN)
def toggle_user_active(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", "danger")
    else:
        user.is_active_account = not user.is_active_account
        db.session.commit()
        log_action(f"Account {'activated' if user.is_active_account else 'banned'}", "User", user.id)
        flash(f"User @{user.username} is now {'Active' if user.is_active_account else 'Disabled'}.", "info")
    return redirect(url_for("admin.list_users"))


# ---------- Audit Logs Browser ----------

@admin_bp.route("/audit-logs")
@roles_required(Role.SUPER_ADMIN)
def list_audit_logs():
    search = request.args.get("search", "").strip()
    page = request.args.get("page", 1, type=int)

    query = AuditLog.query
    if search:
        query = query.filter(
            (AuditLog.action.ilike(f"%{search}%"))
            | (AuditLog.target_type.ilike(f"%{search}%"))
            | (AuditLog.ip_address.ilike(f"%{search}%"))
        )

    logs = query.order_by(AuditLog.created_at.desc()).paginate(page=page, per_page=30, error_out=False)
    return render_template("admin/audit_logs.html", logs=logs, search=search)


# ---------- Reports Hub (Excel / CSV & PDF Downloads) ----------

@admin_bp.route("/reports")
@roles_required(Role.SUPER_ADMIN, Role.FINANCE_MANAGER, Role.TOURNAMENT_MANAGER)
def reports_hub():
    tournaments = Tournament.query.order_by(Tournament.start_time.desc()).all()
    return render_template("admin/reports.html", tournaments=tournaments)


@admin_bp.route("/reports/download/<string:entity>")
@roles_required(Role.SUPER_ADMIN, Role.FINANCE_MANAGER, Role.TOURNAMENT_MANAGER)
def download_report(entity):
    tournament_id = request.args.get("tournament_id", type=int)
    generators = {
        "users": generate_users_csv,
        "teams": generate_teams_csv,
        "tournaments": generate_tournaments_csv,
        "registrations": lambda: generate_registrations_csv(tournament_id),
        "payments": generate_payments_csv,
        "results": lambda: generate_results_csv(tournament_id),
        "prizes": generate_prizes_csv,
        "disputes": generate_disputes_csv,
    }

    if entity not in generators:
        abort(404)

    csv_data = generators[entity]()
    filename = f"{entity}_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={filename}"},
    )


@admin_bp.route("/reports/pdf/<string:entity>")
@roles_required(Role.SUPER_ADMIN, Role.FINANCE_MANAGER, Role.TOURNAMENT_MANAGER)
def download_pdf_report(entity):
    tournament_id = request.args.get("tournament_id", type=int)
    pdf_generators = {
        "users": generate_users_pdf,
        "teams": generate_teams_pdf,
        "tournaments": generate_tournaments_pdf,
        "registrations": lambda: generate_registrations_pdf(tournament_id),
        "payments": generate_payments_pdf,
        "results": lambda: generate_results_pdf(tournament_id),
        "prizes": generate_prizes_pdf,
        "disputes": generate_disputes_pdf,
    }

    if entity not in pdf_generators:
        abort(404)

    pdf_data = pdf_generators[entity]()
    filename = f"{entity}_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"

    return Response(
        pdf_data,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment;filename={filename}"},
    )
