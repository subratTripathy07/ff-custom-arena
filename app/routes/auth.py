from datetime import datetime, timedelta
from email.message import EmailMessage
import secrets
import random
import smtplib

from flask import Blueprint, current_app, render_template, redirect, url_for, flash, request, session
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


def _send_otp_email(recipient, username, otp_code):
    """Send a 6-digit OTP to the user's email for password reset.
    Returns (success: bool, is_smtp: bool, error_msg: str).
    """
    config = current_app.config
    sender = config.get("MAIL_SENDER", "")
    server = config.get("MAIL_SERVER", "")
    mail_user = config.get("MAIL_USERNAME", "")

    # Check if mail is unconfigured or placeholder
    is_placeholder = (
        not sender or not server or not mail_user or 
        "your_gmail" in mail_user.lower() or "example" in mail_user.lower()
    )

    if is_placeholder:
        current_app.logger.info(f"[DEV MODE] Password Reset OTP for {recipient}: {otp_code}")
        print(f"\n{'='*50}")
        print(f"  🔐 [DEV OTP] Email: {recipient} | OTP: {otp_code}")
        print(f"{'='*50}\n")
        return True, False, "Dev mode (SMTP placeholder)"

    message = EmailMessage()
    message["Subject"] = f"🔐 {config['SITE_NAME']} — Your Password Reset OTP"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(
        f"Hi {username},\n\n"
        f"Your FF Custom Arena password reset OTP is:\n\n"
        f"  {otp_code}\n\n"
        f"This OTP is valid for 10 minutes only.\n"
        f"Do NOT share this code with anyone.\n\n"
        f"If you did not request this, please ignore this email.\n\n"
        f"— FF Custom Arena Team"
    )
    message.add_alternative(f"""
    <html><body style="font-family:sans-serif; background:#0a0814; color:#fff; padding:40px; text-align:center;">
      <div style="max-width:480px; margin:0 auto; background:#120d24; border:1px solid rgba(139,92,246,0.3); border-radius:20px; padding:40px;">
        <div style="font-size:2.5rem; margin-bottom:8px;">🔐</div>
        <h2 style="color:#a78bfa; margin:0 0 8px;">FF Custom Arena</h2>
        <p style="color:#94a3b8; font-size:0.9rem; margin:0 0 32px;">Password Reset OTP</p>
        <div style="background:#1e1535; border:1px solid rgba(139,92,246,0.4); border-radius:14px; padding:24px; margin-bottom:24px;">
          <p style="color:#94a3b8; font-size:0.8rem; margin:0 0 8px; text-transform:uppercase; letter-spacing:0.08em;">Your OTP Code</p>
          <div style="font-size:3rem; font-weight:900; letter-spacing:0.3em; color:#a78bfa; font-family:monospace;">{otp_code}</div>
          <p style="color:#64748b; font-size:0.78rem; margin:12px 0 0;">Valid for 10 minutes only</p>
        </div>
        <p style="color:#475569; font-size:0.8rem;">Do NOT share this OTP with anyone.</p>
      </div>
    </body></html>
    """, subtype='html')

    try:
        with smtplib.SMTP(server, config["MAIL_PORT"], timeout=8) as smtp:
            if config["MAIL_USE_TLS"]:
                smtp.starttls()
            if mail_user:
                smtp.login(mail_user, config.get("MAIL_PASSWORD") or "")
            smtp.send_message(message)
        return True, True, ""
    except Exception as e:
        current_app.logger.exception("Unable to deliver OTP email: %s", e)
        print(f"\n{'='*50}")
        print(f"  ⚠️ [SMTP FAIL] Email: {recipient} | OTP: {otp_code} | Error: {e}")
        print(f"{'='*50}\n")
        return False, True, str(e)


def _send_password_changed_email(recipient, username):
    """Send notification email when password is successfully changed."""
    config = current_app.config
    sender = config.get("MAIL_SENDER")
    server = config.get("MAIL_SERVER")
    mail_user = config.get("MAIL_USERNAME", "")
    if not sender or not server or "your_gmail" in mail_user.lower():
        return False

    message = EmailMessage()
    message["Subject"] = f"⚠️ {config['SITE_NAME']} — Password Changed Successfully"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(
        f"Hi {username},\n\n"
        "Your FF Custom Arena account password was changed successfully.\n\n"
        "If you did NOT make this change, please reset your password immediately.\n\n"
        "— FF Custom Arena Team"
    )
    try:
        with smtplib.SMTP(server, config["MAIL_PORT"], timeout=8) as smtp:
            if config["MAIL_USE_TLS"]:
                smtp.starttls()
            if mail_user:
                smtp.login(mail_user, config.get("MAIL_PASSWORD") or "")
            smtp.send_message(message)
        return True
    except Exception:
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
            db.session.flush()
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
@limiter.limit("30 per minute")
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
            destination = next_page if next_page.startswith("/") and not next_page.startswith("//") else url_for("main.home")
            return redirect(destination)

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


# ============================================================
#  OTP-BASED PASSWORD RESET FLOW
#  Step 1: Enter Email / Username → Send OTP & Redirect to Verify OTP
#  Step 2: Enter OTP → Verify (Wrong OTP => Show error on same page)
#  Step 3: Enter New Password + Username → Saved → Redirect to Login
# ============================================================

@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("20 per hour")
def forgot_password():
    if request.method == "POST":
        input_text = request.form.get("email", "").strip()
        if not input_text:
            return render_template("auth/forgot_password.html", error="Please enter your email or username.")

        # Find user by Email or Username
        user = User.query.filter(
            (User.email == input_text.lower()) | (User.username == input_text)
        ).first()

        if not user:
            return render_template(
                "auth/forgot_password.html",
                error=f"❌ No account found for '{input_text}'. Please check your email/username."
            )

        # Generate 6-digit OTP
        otp = str(random.randint(100000, 999999))
        otp_expiry = datetime.utcnow() + timedelta(minutes=10)

        # Save OTP hash & expiry in DB
        user.password_reset_token = generate_password_hash(otp)
        user.password_reset_expires = otp_expiry
        db.session.commit()

        # Send OTP
        success, is_smtp, err_msg = _send_otp_email(user.email, user.username, otp)

        session["reset_email"] = user.email

        if success and is_smtp:
            flash(f"✅ OTP sent successfully to {user.email}! Please enter it below.", "success")
        elif not is_smtp:
            # Dev mode (SMTP placeholder)
            flash(f"🔑 [DEV MODE] OTP generated: {otp} (sent to console for {user.email})", "warning")
        else:
            # SMTP failed (e.g. invalid credentials)
            flash(f"⚠️ Could not deliver email via SMTP. [DEV OTP]: {otp}", "warning")

        # ALWAYS REDIRECT TO VERIFY OTP PAGE
        return redirect(url_for("auth.verify_otp"))

    return render_template("auth/forgot_password.html")


@auth_bp.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    """Step 2: User enters the 6-digit OTP."""
    reset_email = session.get("reset_email")
    if not reset_email:
        flash("Session expired. Please start again.", "danger")
        return redirect(url_for("auth.forgot_password"))

    user = User.query.filter_by(email=reset_email).first()
    if not user:
        flash("Account not found. Please start again.", "danger")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        otp_entered = request.form.get("otp", "").strip()

        if not user.password_reset_token or not user.password_reset_expires:
            flash("No active OTP session. Please request a new OTP.", "danger")
            return redirect(url_for("auth.forgot_password"))

        if user.password_reset_expires < datetime.utcnow():
            return render_template(
                "auth/verify_otp.html",
                email=reset_email,
                error="⏰ OTP has expired (10 min limit). Please request a new one.",
                expired=True
            )

        # Verify OTP code
        if not check_password_hash(user.password_reset_token, otp_entered):
            return render_template(
                "auth/verify_otp.html",
                email=reset_email,
                error="❌ Incorrect OTP code. Please check and try again."
            )

        # OTP is CORRECT!
        session["reset_verified"] = True
        session["reset_user_id"] = user.id

        # Clear token in DB
        user.password_reset_token = None
        user.password_reset_expires = None
        db.session.commit()

        flash("✅ OTP verified successfully! Create your new password below.", "success")
        return redirect(url_for("auth.reset_credentials"))

    return render_template("auth/verify_otp.html", email=reset_email)


@auth_bp.route("/reset-credentials", methods=["GET", "POST"])
def reset_credentials():
    """Step 3: Change password and/or username."""
    if not session.get("reset_verified") or not session.get("reset_user_id"):
        flash("Unauthorized access. Please complete OTP verification first.", "danger")
        return redirect(url_for("auth.forgot_password"))

    user = User.query.get(session["reset_user_id"])
    if not user:
        flash("User not found. Please try again.", "danger")
        return redirect(url_for("auth.forgot_password"))

    error = None
    if request.method == "POST":
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()
        new_username = request.form.get("new_username", "").strip()

        if not new_password:
            error = "New password is required."
        elif len(new_password) < 8:
            error = "Password must be at least 8 characters long."
        elif new_password != confirm_password:
            error = "Passwords do not match."
        elif new_username and len(new_username) < 3:
            error = "Username must be at least 3 characters."
        elif new_username and new_username != user.username:
            existing = User.query.filter_by(username=new_username).first()
            if existing:
                error = "That username is already taken. Please choose another one."

        if not error:
            user.set_password(new_password)
            if new_username and new_username != user.username:
                user.username = new_username

            user.failed_login_attempts = 0
            user.locked_until = None
            db.session.commit()

            # Send confirmation email
            _send_password_changed_email(user.email, user.username)

            # Clear session
            session.pop("reset_verified", None)
            session.pop("reset_user_id", None)
            session.pop("reset_email", None)

            flash("🎉 Password updated successfully! Please log in with your new password.", "success")
            return redirect(url_for("auth.login"))

    return render_template("auth/reset_credentials.html", user=user, error=error)


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    """Legacy token-based reset (kept for backward compatibility)."""
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
        _send_password_changed_email(user.email, user.username)
        flash("Password reset successfully!", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/reset_password.html", form=form, token=token)
