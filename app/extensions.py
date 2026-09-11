"""
Central place for all Flask extension instances.
Instantiated here (unbound) and initialized in app/__init__.py via init_app()
to avoid circular imports.
"""
import os

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)

# SocketIO is NOT compatible with Vercel serverless (stateless, no persistent connections).
# On Vercel, we create a dummy stub so imports don't break.
if os.environ.get("VERCEL"):
    class _DummySocketIO:
        """No-op SocketIO stub for Vercel serverless environment."""
        async_mode = None

        def init_app(self, app, **kwargs):
            pass

        def on(self, event, **kwargs):
            def decorator(f):
                return f
            return decorator

        def emit(self, *args, **kwargs):
            pass

        def run(self, app, **kwargs):
            from werkzeug.serving import run_simple
            run_simple("0.0.0.0", 5000, app)

    socketio = _DummySocketIO()
else:
    from flask_socketio import SocketIO
    # Auto-detect: uses eventlet when running with gunicorn on Railway, threading locally
    _async_mode = "eventlet" if (os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("GUNICORN_CMD_ARGS")) else None
    socketio = SocketIO(
        cors_allowed_origins="*",
        async_mode=_async_mode
    )


login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "warning"