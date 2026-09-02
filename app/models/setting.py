from app.extensions import db

class SystemSetting(db.Model):
    __tablename__ = "system_settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)

    @classmethod
    def get(cls, key, default=None):
        try:
            setting = cls.query.filter_by(key=key).first()
            return setting.value if setting and setting.value is not None else default
        except Exception:
            return default

    @classmethod
    def set(cls, key, value):
        try:
            setting = cls.query.filter_by(key=key).first()
            if not setting:
                setting = cls(key=key, value=str(value))
                db.session.add(setting)
            else:
                setting.value = str(value)
            db.session.commit()
        except Exception:
            db.session.rollback()
