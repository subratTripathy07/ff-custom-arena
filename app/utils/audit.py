from flask import request
from flask_login import current_user
from app.extensions import db
from app.models.audit import AuditLog


def log_action(action: str, target_type: str = None, target_id: int = None):
    try:
        user_id = current_user.id if (current_user and getattr(current_user, 'is_authenticated', False)) else None
        entry = AuditLog(
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            ip_address=getattr(request, 'remote_addr', None),
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        db.session.rollback()
