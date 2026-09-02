from flask import request
from flask_login import current_user
from app.extensions import db
from app.models.audit import AuditLog


def log_action(action: str, target_type: str = None, target_id: int = None):
    entry = AuditLog(
        user_id=current_user.id if current_user.is_authenticated else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        ip_address=request.remote_addr,
    )
    db.session.add(entry)
    db.session.commit()
