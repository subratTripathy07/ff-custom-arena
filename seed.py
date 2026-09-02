"""
Seed script — run once after migrations to populate roles, a super admin,
and default achievements.

Usage:
    flask shell < seed.py     (or)   python seed.py  (with app context)
"""
from app import create_app
from app.extensions import db
from app.models.user import User, Role
from app.models.player import PlayerProfile, Achievement

app = create_app("development")

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

with app.app_context():
    for name, desc in ROLES:
        if not Role.query.filter_by(name=name).first():
            db.session.add(Role(name=name, description=desc))

    for code, title, icon, desc in ACHIEVEMENTS:
        if not Achievement.query.filter_by(code=code).first():
            db.session.add(Achievement(code=code, title=title, icon=icon, description=desc))

    db.session.commit()

    # Create default super admin if none exists
    super_admin_role = Role.query.filter_by(name=Role.SUPER_ADMIN).first()
    if not User.query.filter_by(role_id=super_admin_role.id).first():
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
        print("Created default super admin -> username: subrat | password: subrat7894")
        print("IMPORTANT: change this password immediately after first login.")

    print("Seed complete: roles + achievements ready.")
