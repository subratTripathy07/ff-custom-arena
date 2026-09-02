from datetime import datetime, timedelta
from email.message import EmailMessage
import secrets
import smtplib

from flask import Blueprint, current_app, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from itsdangerous import BadSignature, URLSafeSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, limiter
from app.forms.auth_forms import RegisterForm, LoginForm, ForgotPasswordForm, ResetPasswordForm
from app.models.user import User, Role
from app.models.player import PlayerProfile
from app.utils.audit import log_action

auth_bp = Blueprint("auth", __name__, template_folder="../templates/auth")

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def _reset_token_serializer():
    return URLSafeSerializer(current_app.config["SECRET_KEY"], salt="password-reset")


def _send_password_reset_email(recipient, reset_url):
    """Deliver a reset URL through the configured SMTP account.

    Returning a boolean keeps the public response identical for existing and
    non-existing accounts, which prevents email-address enumeration.
    """
    config = current_app.config
    sender = config.get("MAIL_SENDER")
    server = config.get("MAIL_SERVER")
    if not sender or not server:
        if current_app.debug:
            current_app.logger.info("Development password-reset URL: %s", reset_url)
        else:
            current_app.logger.error("Password reset email is not configured.")
        return False

    message = EmailMessage()
    message["Subject"] = f"{config['SITE_NAME']} password reset"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(
        "A password reset was requested for your account. Open this link within one hour:\n\n"
        f"{reset_url}\n\n"
        "If you did not request this, you can safely ignore this email."
    )

    try:
        with smtplib.SMTP(server, config["MAIL_PORT"], timeout=10) as smtp:
            if config["MAIL_USE_TLS"]:
                smtp.starttls()
            if config.get("MAIL_USERNAME"):
                smtp.login(config["MAIL_USERNAME"], config.get("MAIL_PASSWORD") or "")
            smtp.send_message(message)
        return True
    except (OSError, smtplib.SMTPException):
        current_app.logger.exception("Unable to deliver password reset email")
        return False


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    form = RegisterForm()
    if form.validate_on_submit():
        player_role = Role.query.filter_by(name=Role.PLAYER).first()
        try:
            if not player_role:
                # Safety net: seed roles if missing.  Keep it in the same
                # transaction as the new account so partial records are not left behind.
                player_role = Role(name=Role.PLAYER, description="Default player role")
                db.session.add(player_role)
                db.session.flush()

            user = User(
                full_name=form.full_name.data.strip(),
                username=form.username.data.strip(),
                email=form.email.data.strip().lower(),
                phone=form.phone.data.strip(),
                role_id=player_role.id,
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.flush()  # get user.id before commit
            db.session.add(PlayerProfile(user_id=user.id))
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Unable to register account")
            flash("We could not create your account. Please try again.", "danger")
            return render_template("auth/register.html", form=form)

        log_action("Player registered", "User", user.id)
        flash("Account created successfully! Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    portal = request.args.get("portal", "").lower()
    if portal not in {"user", "admin"}:
        return render_template("auth/login_choice.html", next_page=request.args.get("next"))

    admin_level = request.args.get("admin_level", "").lower()
    if portal == "admin" and admin_level not in {"head", "admin"}:
        return render_template("auth/admin_login_choice.html", next_page=request.args.get("next"))

    form = LoginForm()
    if form.validate_on_submit():
        identifier = form.identifier.data.strip()
        user = User.query.filter(
            (User.username == identifier) | (User.email == identifier.lower())
        ).first()

        # Account lockout check
        if user and user.locked_until and user.locked_until > datetime.utcnow():
            remaining = int((user.locked_until - datetime.utcnow()).total_seconds() // 60) + 1
            flash(f"Account locked. Try again in {remaining} minute(s).", "danger")
            return render_template("auth/login.html", form=form)

        if user and user.check_password(form.password.data):
            if not user.is_active_account:
                flash("Your account has been disabled. Contact support.", "danger")
                return render_template("auth/login.html", form=form, portal=portal)

            if portal == "user" and user.is_admin():
                flash("Please use Admin Login for an administrator account.", "warning")
                return render_template("auth/login.html", form=form, portal=portal)

            if portal == "admin":
                if admin_level == "head" and not user.is_super_admin():
                    flash("This account is not a Head Admin account.", "danger")
                    return render_template("auth/login.html", form=form, portal=portal)
                if admin_level == "admin" and (not user.is_admin() or user.is_super_admin()):
                    flash("Please choose the correct admin login type for this account.", "danger")
                    return render_template("auth/login.html", form=form, portal=portal)

            user.failed_login_attempts = 0
            user.locked_until = None
            user.last_login_at = datetime.utcnow()
            user.last_login_ip = request.remote_addr
            db.session.commit()

            login_user(user, remember=form.remember_me.data)
            log_action("User logged in", "User", user.id)

            next_page = request.args.get("next", "")
            # Only honour local paths; accepting an arbitrary URL here enables
            # phishing via an open redirect after login.
            destination = next_page if next_page.startswith("/") and not next_page.startswith("//") else url_for("main.home")
            return redirect(destination)

        # Failed login handling
        if user:
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
                user.locked_until = datetime.utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
                flash(f"Too many failed attempts. Account locked for {LOCKOUT_MINUTES} minutes.", "danger")
            db.session.commit()

        flash("Invalid username/email or password.", "danger")

    return render_template("auth/login.html", form=form, portal=portal, admin_level=admin_level)


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    log_action("User logged out", "User", current_user.id)
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.home"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per hour")
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.strip().lower()).first()
        # Always show the same message - never reveal whether the email exists
        if user:
            nonce = secrets.token_urlsafe(32)
            user.password_reset_token = generate_password_hash(nonce)
            user.password_reset_expires = datetime.utcnow() + timedelta(hours=1)
            db.session.commit()
            token = _reset_token_serializer().dumps({"user_id": user.id, "nonce": nonce})
            reset_url = url_for("auth.reset_password", token=token, _external=True)
            _send_password_reset_email(user.email, reset_url)

        flash("If that email is registered, a reset link has been sent.", "info")
        return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html", form=form)


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        payload = _reset_token_serializer().loads(token)
        user_id = int(payload["user_id"])
        nonce = payload["nonce"]
    except (BadSignature, KeyError, TypeError, ValueError):
        flash("This password-reset link is invalid or has expired.", "danger")
        return redirect(url_for("auth.forgot_password"))

    user = User.query.get(user_id)
    valid_token = (
        user
        and user.password_reset_token
        and user.password_reset_expires
        and user.password_reset_expires > datetime.utcnow()
        and check_password_hash(user.password_reset_token, nonce)
    )
    if not valid_token:
        flash("This password-reset link is invalid or has expired.", "danger")
        return redirect(url_for("auth.forgot_password"))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        user.password_reset_token = None
        user.password_reset_expires = None
        user.failed_login_attempts = 0
        user.locked_until = None
        db.session.commit()
        flash("Password reset successfully. Please log in.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/reset_password.html", form=form, token=token)
