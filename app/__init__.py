import os
from flask import Flask, abort, render_template, send_from_directory
from flask_login import current_user
from config import config_by_name
from app.extensions import db, migrate, login_manager, csrf, limiter, socketio


def _init_db_and_seed(app):
    """Auto-create tables and seed initial roles & super admin if needed."""
    with app.app_context():
        try:
            import app.models  # Register all models with SQLAlchemy metadata
            db.create_all()
            from app.models.user import User, Role
            from app.models.player import PlayerProfile, Achievement


            ROLES = [
                (Role.SUPER_ADMIN, "Full access to everything"),
                (Role.TOURNAMENT_MANAGER, "Create tournaments, manage matches/rooms/results"),
                (Role.MODERATOR, "Handle disputes, reports, player moderation"),
                (Role.FINANCE_MANAGER, "Manage payments and prize distribution"),
                (Role.PLAYER, "Default role for registered players"),
            ]

            ACHIEVEMENTS = [
                ("FIRST_BLOOD", "First Blood", "🔥", "Get your first kill in a tournament match."),
                ("HUNDRED_KILLS", "100 Kills", "💀", "Reach 100 career kills."),
                ("TOURNAMENT_WINNER", "Tournament Winner", "🏆", "Win a tournament."),
                ("FIVE_X_MVP", "5x MVP", "⭐", "Earn MVP 5 times."),
                ("TOP_RANKED", "Top Ranked", "👑", "Reach #1 on the global leaderboard."),
                ("TWENTY_KILL_GAME", "20 Kill Game", "🎯", "Get 20 kills in a single match."),
            ]

            for name, desc in ROLES:
                if not Role.query.filter_by(name=name).first():
                    db.session.add(Role(name=name, description=desc))

            for code, title, icon, desc in ACHIEVEMENTS:
                if not Achievement.query.filter_by(code=code).first():
                    db.session.add(Achievement(code=code, title=title, icon=icon, description=desc))

            db.session.commit()

            super_admin_role = Role.query.filter_by(name=Role.SUPER_ADMIN).first()
            if super_admin_role and not User.query.filter_by(role_id=super_admin_role.id).first():
                admin = User(
                    full_name="Super Admin",
                    username="subrat",
                    email="admin@ffcustomarena.local",
                    phone="+910000000000",
                    role_id=super_admin_role.id,
                    is_email_verified=True,
                )
                admin.set_password("subrat7894")
                db.session.add(admin)
                db.session.flush()
                db.session.add(PlayerProfile(user_id=admin.id))
                db.session.commit()
        except Exception as e:
            app.logger.warning(f"Database auto-init skipped or failed: {e}")


def create_app(config_name="development"):
    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    # Ensure upload directory exists
    try:
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    except Exception:
        pass

    # ---------- Init extensions ----------
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    if not os.environ.get("VERCEL"):
        try:
            socketio.init_app(app)
        except Exception:
            pass

    _init_db_and_seed(app)


    @app.route("/uploads/<path:filename>")
    def uploaded_file(filename):
        if filename.startswith(("proofs/", "payment_proofs/")):
            if not current_user.is_authenticated:
                abort(403)
            from app.models.payment import Payment
            from app.models.proof import UploadedProof
            evidence = UploadedProof.query.filter_by(file_path=filename).first()
            payment = Payment.query.filter_by(proof_path=filename).first()
            permitted = current_user.is_admin() or (evidence and evidence.uploaded_by_id == current_user.id) or (payment and payment.registration.registered_by_id == current_user.id)
            if not permitted:
                abort(403)
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

    @socketio.on("connect")
    def socket_connect():
        from flask_socketio import join_room
        if current_user.is_authenticated:
            join_room(f"user:{current_user.id}")

    @socketio.on("subscribe_tournament")
    def subscribe_tournament(payload):
        from flask_socketio import join_room
        tournament_id = (payload or {}).get("tournament_id")
        if current_user.is_authenticated and isinstance(tournament_id, int):
            join_room(f"tournament:{tournament_id}")

    # ---------- User loader ----------
    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # ---------- Blueprints ----------
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.teams import teams_bp
    from app.routes.tournaments import tournaments_bp
    from app.routes.api import api_bp
    from app.routes.admin import admin_bp
    from app.routes.competition import competition_bp
    from app.routes.support import support_bp
    from app.routes.payments import payments_bp
    from app.routes.player import player_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
    app.register_blueprint(teams_bp, url_prefix="/teams")
    app.register_blueprint(tournaments_bp, url_prefix="/tournaments")
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(competition_bp, url_prefix="/competition")
    app.register_blueprint(support_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(player_bp)

    # ---------- Error handlers ----------
    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(500)
    def server_error(e):
        app.logger.error(f"Server error: {e}")
        return render_template("errors/500.html"), 500

    @app.errorhandler(429)
    def too_many_requests(e):
        return render_template("errors/429.html"), 429

    # ---------- Context processors ----------
    from datetime import datetime

    @app.context_processor
    def inject_globals():
        unread_notifs = 0
        if current_user.is_authenticated:
            from app.models.notification import Notification
            try:
                unread_notifs = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
            except Exception:
                unread_notifs = 0

        from app.models.setting import SystemSetting
        upi_id = SystemSetting.get("admin_upi_id", "admin@upi")
        upi_name = SystemSetting.get("admin_upi_name", "FF Custom Arena Admin")
        qr_code = SystemSetting.get("admin_qr_code", "qr_codes/default_qr.png")

        return {
            "site_name": app.config["SITE_NAME"],
            "current_year": datetime.utcnow().year,
            "unread_notifications": unread_notifs,
            "admin_upi_id": upi_id,
            "admin_upi_name": upi_name,
            "admin_qr_code": qr_code,
        }

    return app
