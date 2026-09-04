from datetime import datetime
from flask import Blueprint, render_template, request
from flask_login import login_required
from app.models.tournament import Tournament
from app.models.notification import Announcement
from app.models.user import User
from app.models.team import Team
from app.models.match import Match
from app.models.player import PlayerStatistic
from app.extensions import db

main_bp = Blueprint("main", __name__, template_folder="../templates/main")


@main_bp.route("/")
@login_required
def home():
    now = datetime.utcnow()

    try:
        live_tournaments = (
            Tournament.query.filter_by(status="live").order_by(Tournament.start_time).limit(3).all()
        )
    except Exception:
        live_tournaments = []

    try:
        upcoming_tournaments = (
            Tournament.query.filter(Tournament.status.in_(["registration_open", "closing_soon"]))
            .order_by(Tournament.start_time).limit(6).all()
        )
    except Exception:
        upcoming_tournaments = []

    featured = upcoming_tournaments[0] if upcoming_tournaments else None

    try:
        announcements = (
            Announcement.query.filter_by(is_active=True)
            .order_by(Announcement.created_at.desc()).limit(5).all()
        )
    except Exception:
        announcements = []

    try:
        top_players = (
            PlayerStatistic.query.order_by(PlayerStatistic.total_points.desc()).limit(5).all()
        )
    except Exception:
        top_players = []

    try:
        stats = {
            "total_players": User.query.count(),
            "total_teams": Team.query.count(),
            "total_matches": Match.query.count(),
            "total_prize_pool": db.session.query(
                db.func.coalesce(db.func.sum(Tournament.prize_pool), 0)
            ).scalar(),
        }
    except Exception:
        stats = {"total_players": 0, "total_teams": 0, "total_matches": 0, "total_prize_pool": 0}

    try:
        next_match = (
            Match.query.filter(Match.status.in_(["scheduled", "upcoming"]))
            .order_by(Match.scheduled_date, Match.scheduled_time).first()
        )
    except Exception:
        next_match = None

    return render_template(
        "main/home.html",
        live_tournaments=live_tournaments,
        upcoming_tournaments=upcoming_tournaments,
        featured=featured,
        announcements=announcements,
        top_players=top_players,
        stats=stats,
        next_match=next_match,
        now=now,
    )


@main_bp.route("/how-it-works")
def how_it_works():
    return render_template("main/how_it_works.html")


@main_bp.route("/faq")
def faq():
    return render_template("main/faq.html")


@main_bp.route("/search")
def search():
    """Global search for tournaments, teams, and players."""
    query = request.args.get("q", "").strip()
    search_type = request.args.get("type", "").strip()

    tournaments = []
    teams = []
    players = []

    if query:
        try:
            if not search_type or search_type == "tournament":
                tournaments = (
                    Tournament.query.filter(Tournament.name.ilike(f"%{query}%"))
                    .order_by(Tournament.start_time.desc())
                    .limit(12)
                    .all()
                )
        except Exception:
            tournaments = []

        try:
            if not search_type or search_type == "team":
                teams = (
                    Team.query.filter(
                        Team.is_active == True,
                        (Team.name.ilike(f"%{query}%")) | (Team.tag.ilike(f"%{query}%"))
                    )
                    .limit(12)
                    .all()
                )
        except Exception:
            teams = []

        try:
            if not search_type or search_type == "player":
                players = (
                    User.query.filter(
                        (User.username.ilike(f"%{query}%"))
                        | (User.full_name.ilike(f"%{query}%"))
                    )
                    .limit(12)
                    .all()
                )
        except Exception:
            players = []

    return render_template(
        "main/search_results.html",
        query=query,
        search_type=search_type,
        tournaments=tournaments,
        teams=teams,
        players=players,
    )


@main_bp.route("/matches")
def matches_redirect():
    from flask import redirect, url_for
    return redirect(url_for("competition.matches"))
