import os
from datetime import timedelta
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))

# Load .env
load_dotenv(os.path.join(basedir, ".env"))


class Config:
    """Base configuration - shared by all environments."""

    SITE_NAME = os.environ.get("SITE_NAME", "FF Custom Arena")
    SITE_URL = os.environ.get("SITE_URL", "http://localhost:5000")

    SECRET_KEY = os.environ.get(
        "SECRET_KEY",
        "ff-custom-arena-secret-key-2026-production-fallback"
    )

    # ==========================================================
    # DATABASE
    # ==========================================================

    DATABASE_URL = os.environ.get("DATABASE_URL")

    # Fix database URL automatically
    if DATABASE_URL:

        # PostgreSQL old format
        if DATABASE_URL.startswith("postgres://"):
            DATABASE_URL = DATABASE_URL.replace(
                "postgres://",
                "postgresql://",
                1
            )

        # Aiven MySQL URL
        elif DATABASE_URL.startswith("mysql://"):
            DATABASE_URL = DATABASE_URL.replace(
                "mysql://",
                "mysql+pymysql://",
                1
            )

    else:
        # Check if running on Vercel (read-only filesystem except /tmp)
        if os.environ.get("VERCEL"):
            sqlite_file = "/tmp/ff_custom_arena.db"
        else:
            sqlite_file = os.path.join(basedir, "ff_custom_arena.db")

        DATABASE_URL = f"sqlite:///{sqlite_file}"

    SQLALCHEMY_DATABASE_URI = DATABASE_URL

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Aiven Cloud MySQL requires SSL; local MySQL and SQLite do not
    if DATABASE_URL and DATABASE_URL.startswith("mysql+pymysql://") and "aivencloud.com" in DATABASE_URL:
        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_pre_ping": True,
            "pool_recycle": 280,
            "connect_args": {
                "ssl": {}
            }
        }
    else:
        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_pre_ping": True,
            "pool_recycle": 280
        }

    # ==========================================================
    # UPLOADS
    # ==========================================================

    if os.environ.get("VERCEL"):
        UPLOAD_FOLDER = "/tmp/uploads"
    else:
        UPLOAD_FOLDER = os.path.join(
            basedir,
            os.environ.get("UPLOAD_FOLDER", "uploads")
        )

    MAX_CONTENT_LENGTH = (
        int(os.environ.get("MAX_CONTENT_LENGTH_MB", 5))
        * 1024
        * 1024
    )

    ALLOWED_IMAGE_EXTENSIONS = {
        "png",
        "jpg",
        "jpeg",
        "webp"
    }

    ALLOWED_PROOF_EXTENSIONS = {
        "png",
        "jpg",
        "jpeg",
        "webp",
        "pdf",
        "mp4"
    }

    PROOF_MAX_BYTES = (
        int(os.environ.get("PROOF_MAX_MB", 10))
        * 1024
        * 1024
    )

    # ==========================================================
    # SECURITY / SESSIONS
    # ==========================================================

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    SESSION_COOKIE_SECURE = (
        os.environ.get("SESSION_COOKIE_SECURE", "False")
        == "True"
    )

    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    REMEMBER_COOKIE_DURATION = timedelta(days=14)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE

    WTF_CSRF_ENABLED = True

    WTF_CSRF_TIME_LIMIT = int(
        os.environ.get("WTF_CSRF_TIME_LIMIT", 3600)
    )

    # ==========================================================
    # RATE LIMITING
    # ==========================================================

    RATELIMIT_STORAGE_URI = os.environ.get(
        "RATELIMIT_STORAGE_URI",
        "memory://"
    )

    RATELIMIT_DEFAULT = "200 per hour"

    # ==========================================================
    # MAIL
    # ==========================================================

    MAIL_SERVER = os.environ.get("MAIL_SERVER")

    MAIL_PORT = int(
        os.environ.get("MAIL_PORT", 587)
    )

    MAIL_USE_TLS = (
        os.environ.get("MAIL_USE_TLS", "True")
        == "True"
    )

    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")

    MAIL_SENDER = os.environ.get(
        "MAIL_SENDER",
        MAIL_USERNAME
    )

    # ==========================================================
    # APP SETTINGS
    # ==========================================================

    TEAM_ROSTER_MAX = 5
    TEAM_ROSTER_MIN = 2

    ROOM_MASK_CHAR = "•"

    # ==========================================================
    # PAYMENT GATEWAY
    # ==========================================================

    PAYMENT_KEY_ID = os.environ.get(
        "PAYMENT_KEY_ID",
        "rzp_test_ff_custom_arena"
    )

    PAYMENT_SECRET_KEY = os.environ.get(
        "PAYMENT_SECRET_KEY",
        "ff_secret_key_987654"
    )

    PAYMENT_WEBHOOK_SECRET = os.environ.get(
        "PAYMENT_WEBHOOK_SECRET",
        "ff_webhook_secret_987654"
    )


class DevelopmentConfig(Config):

    DEBUG = True

    SECRET_KEY = os.environ.get(
        "SECRET_KEY",
        "local-development-key-change-before-deploy"
    )

    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False


class ProductionConfig(Config):

    DEBUG = False

    # On Vercel (HTTPS), cookies must be secure for sessions to work
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True

    # Longer CSRF window so users don't get logged out mid-session
    WTF_CSRF_TIME_LIMIT = 86400  # 24 hours

    # Vercel serverless: use memory-based rate limiting (no Redis needed)
    RATELIMIT_STORAGE_URI = "memory://"


class TestingConfig(Config):

    TESTING = True

    WTF_CSRF_ENABLED = False

    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"

    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
    }


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}