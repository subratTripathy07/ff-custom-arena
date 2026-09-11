import os
import sys
import traceback

# Force VERCEL environment flag BEFORE any app imports
# This ensures extensions.py uses the SocketIO stub instead of real SocketIO
os.environ.setdefault("VERCEL", "1")
os.environ.setdefault("FLASK_ENV", "production")

# Ensure root project directory is in python path
basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if basedir not in sys.path:
    sys.path.insert(0, basedir)

# ─── Try to boot the real app ───────────────────────────────────────────────
_boot_error = None
app = None

try:
    from app import create_app
    app = create_app("production")
except Exception:
    _boot_error = traceback.format_exc()

# ─── If boot failed, serve a diagnostic app ─────────────────────────────────
if app is None:
    from flask import Flask, request as flask_request
    app = Flask(__name__)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def boot_error_page(path):
        """Show the exact Python error that prevented the app from starting."""
        return (
            f"<html><body style='font-family:monospace;background:#0d0020;color:#ff6b6b;padding:2em'>"
            f"<h2 style='color:#fff'>⚠️ FF Custom Arena — Startup Error</h2>"
            f"<p style='color:#94a3b8'>The server crashed during boot. Error details below:</p>"
            f"<pre style='background:#1a0040;padding:1.5em;border-radius:8px;white-space:pre-wrap;color:#fbbf24;font-size:0.85rem'>{_boot_error}</pre>"
            f"<p style='color:#64748b;font-size:0.8rem'>Check Vercel Function Logs for more details.</p>"
            f"</body></html>",
            500,
        )

handler = app
