from flask import Blueprint, abort, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.extensions import db
from app.models.team import Team, TeamMember
from app.models.user import User
from app.models.tournament import TournamentRegistration
from app.models.match import MatchResult
from app.utils.security import save_uploaded_image
from app.utils.audit import log_action

teams_bp = Blueprint("teams", __name__, template_folder="../templates/main")


@teams_bp.route("/")
def list_teams():
    search = request.args.get("search", "").strip()
    query = Team.query.filter_by(is_active=True)
    if search:
        query = query.filter((Team.name.ilike(f"%{search}%")) | (Team.tag.ilike(f"%{search}%")))
    teams = query.order_by(Team.created_at.desc()).all()
    return render_template("main/teams.html", teams=teams, search=search)


@teams_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_team():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        tag = request.form.get("tag", "").strip().upper()
        description = request.form.get("description", "").strip()

        if not name:
            flash("Team name is required.", "danger")
        elif len(name) > 80:
            flash("Team name must be 80 characters or fewer.", "danger")
        elif Team.query.filter_by(name=name).first():
            flash("A team with this name already exists.", "danger")
        elif tag and len(tag) > 10:
            flash("Team tag must be 10 characters or fewer.", "danger")
        else:
            logo_path = "default_team_logo.png"
            logo_file = request.files.get("logo")
            if logo_file and logo_file.filename:
                uploaded = save_uploaded_image(logo_file, "team_logos")
                if uploaded:
                    logo_path = uploaded

            team = Team(
                name=name,
                tag=tag or None,
                captain_id=current_user.id,
                description=description or None,
                logo_url=logo_path,
            )
            db.session.add(team)
            db.session.flush()
            db.session.add(TeamMember(team_id=team.id, user_id=current_user.id, is_substitute=False))
            db.session.commit()

            log_action("Team created", "Team", team.id)
            flash("Team created successfully! You can now invite roster players.", "success")
            return redirect(url_for("teams.manage_team", team_id=team.id))
    return render_template("main/create_team.html")


@teams_bp.route("/<int:team_id>", methods=["GET", "POST"])
@teams_bp.route("/<int:team_id>/detail", methods=["GET", "POST"])
@login_required
def manage_team(team_id):
    team = Team.query.get_or_404(team_id)
    is_captain = team.captain_id == current_user.id or current_user.is_admin()

    if request.method == "POST" and is_captain:
        action = request.form.get("action")
        
        if action == "edit_info":
            name = request.form.get("name", "").strip()
            tag = request.form.get("tag", "").strip().upper()
            description = request.form.get("description", "").strip()

            if name and name != team.name:
                existing = Team.query.filter_by(name=name).first()
                if existing:
                    flash("Team name is already in use.", "danger")
                    return redirect(url_for("teams.manage_team", team_id=team.id))
                team.name = name
            
            if tag is not None:
                team.tag = tag or None
            team.description = description or None

            logo_file = request.files.get("logo")
            if logo_file and logo_file.filename:
                uploaded = save_uploaded_image(logo_file, "team_logos")
                if uploaded:
                    team.logo_url = uploaded

            db.session.commit()
            log_action("Team info updated", "Team", team.id)
            flash("Team details updated successfully!", "success")

        elif action == "add":
            username = request.form.get("username", "").strip()
            user = User.query.filter_by(username=username).first()
            if not user:
                flash("No player found with that username.", "danger")
            elif TeamMember.query.filter_by(team_id=team.id, user_id=user.id).first():
                flash("That player is already in this team.", "warning")
            elif team.members.count() >= 5:
                flash("A team can have at most 5 members (4 Main + 1 Substitute).", "danger")
            else:
                is_sub = request.form.get("is_substitute") == "1"
                db.session.add(TeamMember(team_id=team.id, user_id=user.id, is_substitute=is_sub))
                db.session.commit()
                log_action("Team member added", "Team", team.id)
                flash(f"Added @{user.username} as {'Substitute' if is_sub else 'Main Player'}.", "success")

        elif action == "remove":
            user_id = request.form.get("user_id", type=int)
            member = TeamMember.query.filter_by(team_id=team.id, user_id=user_id).first()
            if not member:
                flash("Member not found in team.", "danger")
            elif member.user_id == team.captain_id:
                flash("The Captain cannot be removed. Transfer captaincy first.", "danger")
            else:
                db.session.delete(member)
                db.session.commit()
                log_action("Team member removed", "Team", team.id)
                flash("Member removed from team roster.", "success")

        elif action == "captain":
            user_id = request.form.get("user_id", type=int)
            member = TeamMember.query.filter_by(team_id=team.id, user_id=user_id, is_substitute=False).first()
            if not member:
                flash("New captain must be an active main team player.", "danger")
            else:
                team.captain_id = member.user_id
                db.session.commit()
                log_action("Team captain transferred", "Team", team.id)
                flash(f"Captaincy successfully transferred to @{member.user.username}!", "success")
                return redirect(url_for("teams.manage_team", team_id=team.id))

        elif action == "delete":
            team.is_active = False
            db.session.commit()
            log_action("Team deleted / archived", "Team", team.id)
            flash("Team deleted successfully.", "info")
            return redirect(url_for("teams.list_teams"))

        return redirect(url_for("teams.manage_team", team_id=team.id))

    # Team history
    registrations = (
        TournamentRegistration.query.filter_by(team_id=team.id)
        .order_by(TournamentRegistration.created_at.desc())
        .all()
    )
    results = (
        MatchResult.query.filter_by(team_id=team.id, status="verified")
        .order_by(MatchResult.created_at.desc())
        .all()
    )

    return render_template(
        "main/manage_team.html",
        team=team,
        is_captain=is_captain,
        registrations=registrations,
        results=results,
    )


@teams_bp.route("/team-detail/<int:team_id>")
def team_detail(team_id):
    return manage_team(team_id)

