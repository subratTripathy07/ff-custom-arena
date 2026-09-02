from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from app.extensions import db
from app.models.notification import Notification
from app.models.support import SupportMessage, SupportTicket
from app.models.user import Role
from app.services.tournament_service import notify_user
from app.utils.decorators import roles_required
from app.utils.audit import log_action

support_bp = Blueprint("support", __name__, template_folder="../templates")

@support_bp.route("/support", methods=["GET", "POST"])
@support_bp.route("/support/tickets", methods=["GET", "POST"])
@support_bp.route("/tickets", methods=["GET", "POST"])
@login_required
def tickets():
    if request.method == "POST":
        category, subject, message = request.form.get("category", "other"), request.form.get("subject", "").strip(), request.form.get("message", "").strip()
        if category not in {"payment", "tournament", "match", "account", "technical", "other"} or not subject or not message:
            flash("Select a category and provide a subject and message.", "danger")
        else:
            ticket = SupportTicket(user_id=current_user.id, category=category, subject=subject[:150], message=message)
            db.session.add(ticket); db.session.commit(); log_action("Support ticket created", "SupportTicket", ticket.id)
            flash("Support ticket created.", "success")
    rows = SupportTicket.query.filter_by(user_id=current_user.id).order_by(SupportTicket.created_at.desc()).all()
    return render_template("support/tickets.html", tickets=rows)

@support_bp.route("/support/<int:ticket_id>", methods=["GET", "POST"])
@support_bp.route("/support/tickets/<int:ticket_id>", methods=["GET", "POST"])
@support_bp.route("/tickets/<int:ticket_id>", methods=["GET", "POST"])
@login_required
def ticket_detail(ticket_id):
    ticket = SupportTicket.query.get_or_404(ticket_id)
    if ticket.user_id != current_user.id and not current_user.is_admin(): abort(403)
    if request.method == "POST":
        message = request.form.get("message", "").strip()
        if message and ticket.status not in {"closed", "resolved"}:
            db.session.add(SupportMessage(ticket_id=ticket.id, sender_id=current_user.id, message=message))
            if current_user.is_admin():
                ticket.status = "waiting_for_user"; notify_user(ticket.user_id, f"Support replied to ticket #{ticket.id}.", url_for("support.ticket_detail", ticket_id=ticket.id), "🎫")
            else: ticket.status = "open"
            db.session.commit(); flash("Reply sent.", "success")
    return render_template("support/ticket_detail.html", ticket=ticket)

@support_bp.route("/admin/support/<int:ticket_id>/status", methods=["POST"])
@roles_required(Role.SUPER_ADMIN, Role.MODERATOR)
def ticket_status(ticket_id):
    ticket = SupportTicket.query.get_or_404(ticket_id); status = request.form.get("status")
    if status not in {"open", "in_progress", "waiting_for_user", "resolved", "closed"}: abort(400)
    ticket.status = status; notify_user(ticket.user_id, f"Ticket #{ticket.id} is now {status.replace('_', ' ')}.", url_for("support.ticket_detail", ticket_id=ticket.id), "🎫")
    db.session.commit(); log_action("Support ticket status changed", "SupportTicket", ticket.id)
    return redirect(url_for("support.ticket_detail", ticket_id=ticket.id))

@support_bp.route("/notifications/read-all", methods=["POST"])
@login_required
def mark_notifications_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
    db.session.commit(); return redirect(request.referrer or url_for("dashboard.index"))
