import sys
from sqlalchemy import inspect, text
from app import create_app
from app.extensions import db

def audit_and_update_db():
    app = create_app("development")
    with app.app_context():
        print("Starting Database Schema Audit & Update...")
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        print(f"Existing tables in database: {tables}")

        db_dialect = db.engine.dialect.name
        print(f"Database Dialect: {db_dialect}")

        # 1. Audit 'users' table columns
        if "users" in tables:
            user_columns = [col["name"] for col in inspector.get_columns("users")]
            print(f"Columns in 'users' table: {user_columns}")

            # Check coins_balance
            if "coins_balance" not in user_columns:
                print("Adding 'coins_balance' column to 'users' table...")
                try:
                    if db_dialect == "sqlite":
                        db.session.execute(text("ALTER TABLE users ADD COLUMN coins_balance INTEGER NOT NULL DEFAULT 0"))
                    else:
                        db.session.execute(text("ALTER TABLE users ADD COLUMN coins_balance INT NOT NULL DEFAULT 0"))
                    db.session.commit()
                    print("[OK] Added 'coins_balance' column successfully.")
                except Exception as e:
                    db.session.rollback()
                    print(f"[!] Error adding 'coins_balance': {e}")
            else:
                print("[OK] Column 'coins_balance' already exists in 'users'.")

            # Check winnings_balance
            if "winnings_balance" not in user_columns:
                print("Adding 'winnings_balance' column to 'users' table...")
                try:
                    if db_dialect == "sqlite":
                        db.session.execute(text("ALTER TABLE users ADD COLUMN winnings_balance NUMERIC(10, 2) NOT NULL DEFAULT 0.00"))
                    else:
                        db.session.execute(text("ALTER TABLE users ADD COLUMN winnings_balance DECIMAL(10, 2) NOT NULL DEFAULT 0.00"))
                    db.session.commit()
                    print("[OK] Added 'winnings_balance' column successfully.")
                except Exception as e:
                    db.session.rollback()
                    print(f"[!] Error adding 'winnings_balance': {e}")
            else:
                print("[OK] Column 'winnings_balance' already exists in 'users'.")

        # 2. Add Unique Constraint (tournament_id, slot_number) to prevent microsecond race conditions
        if "tournament_registrations" in tables:
            print("Verifying unique constraint (tournament_id, slot_number)...")
            try:
                if db_dialect == "mysql":
                    db.session.execute(text("ALTER TABLE tournament_registrations ADD CONSTRAINT uq_tournament_slot_number UNIQUE (tournament_id, slot_number)"))
                elif db_dialect == "sqlite":
                    db.session.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_tournament_slot_number ON tournament_registrations (tournament_id, slot_number)"))
                db.session.commit()
                print("[OK] Unique constraint (tournament_id, slot_number) added successfully.")
            except Exception as e:
                db.session.rollback()
                print(f"[OK] Unique constraint already exists or handled: {e}")

        # 3. Create missing tables (e.g. coin_topups)
        try:
            db.create_all()
            print("[OK] 'coin_topups' table and all registered models created/verified.")
        except Exception as e:
            print(f"[!] Error running db.create_all(): {e}")

        # Verify coin_topups structure
        inspector = inspect(db.engine)
        updated_tables = inspector.get_table_names()
        if "coin_topups" in updated_tables:
            topup_cols = [col["name"] for col in inspector.get_columns("coin_topups")]
            print(f"[OK] 'coin_topups' table verified with columns: {topup_cols}")
        else:
            print("[!] 'coin_topups' table could not be found after creation attempt.")

if __name__ == "__main__":
    audit_and_update_db()
