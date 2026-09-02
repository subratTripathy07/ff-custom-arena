from functools import wraps
from flask import abort
from flask_login import current_user


def roles_required(*role_names):
    """Restrict a route to specific role slugs. Usage: @roles_required(Role.SUPER_ADMIN)"""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(403)
            if current_user.role_name not in role_names:
                abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator


def admin_required(f):
    """Any admin-tier role (super_admin, tournament_manager, moderator, finance_manager)."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            abort(403)
        return f(*args, **kwargs)
    return wrapped


def super_admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_super_admin():
            abort(403)
        return f(*args, **kwargs)
    return wrapped
