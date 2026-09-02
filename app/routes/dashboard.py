from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.models.notification import Notification

dashboard_bp = Blueprint("dashboard", __name__, template_folder="../templates/main")


@dashboard_bp.route("/")
@login_required
def index():
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(5).all()
    return render_template("main/dashboard.html", user=current_user, notifications=notifications)
