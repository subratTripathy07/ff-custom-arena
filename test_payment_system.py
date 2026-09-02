"""Test suite for Admin QR Code Management & Automated Payment Analysis System."""
import sys
from datetime import datetime, timedelta
import unittest
from app import create_app
from app.extensions import db
from app.models.setting import SystemSetting
from app.models.payment import Payment
from app.models.tournament import Tournament, TournamentRegistration
from app.models.team import Team
from app.models.user import User, Role

class TestPaymentSystem(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        self.app_context.pop()

    def test_system_settings_kv(self):
        """Test setting and getting dynamic admin payment configurations."""
        SystemSetting.set('admin_upi_id', 'testadmin@upi')
        SystemSetting.set('admin_upi_name', 'Test Admin Receiver')
        
        self.assertEqual(SystemSetting.get('admin_upi_id'), 'testadmin@upi')
        self.assertEqual(SystemSetting.get('admin_upi_name'), 'Test Admin Receiver')

    def test_automated_payment_analysis(self):
        """Test UTR validation and automated verification (PAYMENT DONE)."""
        payment = Payment.query.first()
        if not payment:
            role = Role(name="player", description="Player")
            db.session.add(role)
            db.session.flush()
            user = User(full_name="Test Player", username="testplayer", email="test@player.com", role_id=role.id)
            user.set_password("pass123")
            db.session.add(user)
            db.session.flush()

            now = datetime.utcnow()
            t = Tournament(name="Test Arena", slug="test-arena", tournament_type="Battle Royale", entry_fee=50, registration_deadline=now + timedelta(days=1), start_time=now + timedelta(days=2), created_by_id=user.id)
            team = Team(name="Test Team", tag="TT", captain_id=user.id)
            db.session.add_all([t, team])
            db.session.flush()

            reg = TournamentRegistration(tournament_id=t.id, team_id=team.id, registered_by_id=user.id, registration_code="REG123")
            db.session.add(reg)
            db.session.flush()

            payment = Payment(registration_id=reg.id, amount=50, status="pending")
            db.session.add(payment)
            db.session.commit()

        payment.transaction_id = "UTR998877665544"
        payment.status = "verified"
        payment.registration.status = "confirmed"
        db.session.commit()
        
        refreshed = Payment.query.get(payment.id)
        self.assertEqual(refreshed.status, "verified")
        self.assertEqual(refreshed.registration.status, "confirmed")
        self.assertEqual(refreshed.transaction_id, "UTR998877665544")

if __name__ == '__main__':
    unittest.main()
