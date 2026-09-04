import os
import sys
import traceback

# Ensure root project directory is in python path
basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if basedir not in sys.path:
    sys.path.insert(0, basedir)

# ─── Try to boot the real app ───────────────────────────────────────────────
_boot_error = None
app = None

try:
    from app import create_app
    app = create_app(os.environ.get("FLASK_ENV", "production"))
except Exception:
    _boot_error = traceback.format_exc()

# ─── If boot failed, serve a diagnostic app ─────────────────────────────────
if app is None:
    from flask import Flask, jsonify
    app = Flask(__name__)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def boot_error_page(path):
        """Show the exact Python error that prevented the app from starting."""
        return (
            f"<html><body style='font-family:monospace;background:#111;color:#f55;padding:2em'>"
            f"<h2>FF Arena - Startup Error</h2>"
            f"<pre style='background:#222;padding:1em;white-space:pre-wrap'>{_boot_error}</pre>"
            f"</body></html>",
            500,
        )

handler = app
