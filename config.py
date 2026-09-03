import os
from datetime import timedelta
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, ".env"))


class Config:
    """Base configuration - shared by all environments."""

    SITE_NAME = os.environ.get("SITE_NAME", "FF Custom Arena")
    SITE_URL = os.environ.get("SITE_URL", "http://localhost:5000")

    SECRET_KEY = os.environ.get(
        "SECRET_KEY", "ff-custom-arena-secret-key-2026-production-fallback"
    )

    # ---------- Database ----------
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if DATABASE_URL:
        if DATABASE_URL.startswith("postgres://"):
            DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    else:
        DB_USER = os.environ.get("DB_USER", "root")
        DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
        DB_HOST = os.environ.get("DB_HOST", "localhost")
        DB_PORT = os.environ.get("DB_PORT", "3306")
        DB_NAME = os.environ.get("DB_NAME", "ff_custom_arena")

        # If deployed on Vercel or cloud without explicit DATABASE_URL, fall back to SQLite in /tmp
        if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
            db_path = os.path.join("/tmp", "ff_custom_arena.db")
            DATABASE_URL = f"sqlite:///{db_path}"
        else:
            DATABASE_URL = (
                f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
            )

    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    } if not DATABASE_URL.startswith("sqlite") else {}

    # ---------- Uploads ----------
    if os.environ.get("VERCEL"):
        UPLOAD_FOLDER = "/tmp/uploads"
    else:
        UPLOAD_FOLDER = os.path.join(basedir, os.environ.get("UPLOAD_FOLDER", "uploads"))

    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH_MB", 5)) * 1024 * 1024
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
    ALLOWED_PROOF_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "pdf", "mp4"}
    PROOF_MAX_BYTES = int(os.environ.get("PROOF_MAX_MB", 10)) * 1024 * 1024

    # ---------- Security / Sessions ----------
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "False") == "True"
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    REMEMBER_COOKIE_DURATION = timedelta(days=14)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE

    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = int(os.environ.get("WTF_CSRF_TIME_LIMIT", 3600))

    # ---------- Rate limiting ----------
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_DEFAULT = "200 per hour"

    # ---------- Mail ----------
    MAIL_SERVER = os.environ.get("MAIL_SERVER")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "True") == "True"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_SENDER = os.environ.get("MAIL_SENDER", MAIL_USERNAME)

    # ---------- App-specific ----------
    TEAM_ROSTER_MAX = 5          # 4 players + 1 substitute
    TEAM_ROSTER_MIN = 2
    ROOM_MASK_CHAR = "•"

    # ---------- Payment Gateway Config ----------
    PAYMENT_KEY_ID = os.environ.get("PAYMENT_KEY_ID", "rzp_test_ff_custom_arena")
    PAYMENT_SECRET_KEY = os.environ.get("PAYMENT_SECRET_KEY", "ff_secret_key_987654")
    PAYMENT_WEBHOOK_SECRET = os.environ.get("PAYMENT_WEBHOOK_SECRET", "ff_webhook_secret_987654")


class DevelopmentConfig(Config):
    DEBUG = True
    SECRET_KEY = os.environ.get("SECRET_KEY", "local-development-key-change-before-deploy")
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False


class ProductionConfig(Config):
    DEBUG = False


class TestingConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}

