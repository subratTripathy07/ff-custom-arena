import os
import warnings

# Suppress warnings
warnings.filterwarnings("ignore")

from app import create_app

# Determine environment
env = os.environ.get("FLASK_ENV")
if not env:
    env = "production" if os.environ.get("VERCEL") else "development"

# WSGI Application entry point for Vercel / Production deployment
app = create_app(env)
handler = app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=app.config.get("DEBUG", False))

