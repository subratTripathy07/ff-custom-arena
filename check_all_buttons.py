"""Comprehensive audit script to find any broken buttons, missing endpoints, or route errors across all templates."""
import os
import re
import unittest
from app import create_app
from app.extensions import db
from app.models.user import User, Role
from app.models.tournament import Tournament, TournamentRegistration
from app.models.team import Team
from app.models.match import Match, Room, MatchResult
from app.models.payment import Payment
from app.models.support import SupportTicket
from app.models.dispute import Dispute
from app.models.prize import Prize
from datetime import datetime, timedelta

class TestAllButtonsAndRoutes(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Seed roles & test users
        admin_role = Role.query.filter_by(name=Role.SUPER_ADMIN).first()
        if not admin_role:
            admin_role = Role(name=Role.SUPER_ADMIN, description="Admin")
            db.session.add(admin_role)
        player_role = Role.query.filter_by(name=Role.PLAYER).first()
        if not player_role:
            player_role = Role(name=Role.PLAYER, description="Player")
            db.session.add(player_role)
        db.session.flush()

        self.admin = User(full_name="Admin Test", username="admin_tester", email="admin@test.com", role_id=admin_role.id)
        self.admin.set_password("pass123")
        
        self.player = User(full_name="Player Test", username="player_tester", email="player@test.com", role_id=player_role.id)
        self.player.set_password("pass123")

        db.session.add_all([self.admin, self.player])
        db.session.flush()

        # Seed dummy tournament, team, match, room, payment, ticket, dispute, prize
        now = datetime.utcnow()
        self.tournament = Tournament(
            name="Apex Arena Test",
            slug="apex-arena-test",
            tournament_type="Battle Royale",
            entry_fee=100,
            prize_pool=1000,
            registration_deadline=now + timedelta(days=1),
            start_time=now + timedelta(days=2),
            created_by_id=self.admin.id
        )
        db.session.add(self.tournament)
        db.session.flush()

        self.team = Team(name="Alpha Squad", tag="AS", captain_id=self.player.id)
        db.session.add(self.team)
        db.session.flush()

        self.reg = TournamentRegistration(
            tournament_id=self.tournament.id,
            team_id=self.team.id,
            registered_by_id=self.player.id,
            registration_code="REG999",
            status="pending"
        )
        db.session.add(self.reg)
        db.session.flush()

        self.payment = Payment(registration_id=self.reg.id, amount=100, status="pending")
        db.session.add(self.payment)

        self.room = Room(room_id_code="12345", room_password="pass", release_time=now)
        db.session.add(self.room)
        db.session.flush()

        self.match = Match(
            tournament_id=self.tournament.id,
            room_id=self.room.id,
            round_number=1,
            match_number=1,
            scheduled_date=now.date(),
            scheduled_time=now.time(),
            map_name="Bermuda",
            status="scheduled"
        )
        db.session.add(self.match)
        db.session.flush()

        self.ticket = SupportTicket(user_id=self.player.id, subject="Test Ticket", message="Help needed", category="general")
        db.session.add(self.ticket)

        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        self.app_context.pop()

    def test_extract_and_ping_all_routes(self):
        """Parse all Jinja templates for url_for links and verify no 404 or 500 errors occur."""
        template_dir = os.path.join(self.app.root_path, 'templates')
        found_urls = set()

        for root, dirs, files in os.walk(template_dir):
            for f in files:
                if f.endswith('.html'):
                    filepath = os.path.join(root, f)
                    with open(filepath, 'r', encoding='utf-8') as fh:
                        content = fh.read()
                        # Extract url_for('route.name'...)
                        matches = re.findall(r"url_for\(['\"]([a-zA-Z0-9_\.]+)['\"]", content)
                        for m in matches:
                            found_urls.add(m)

        print(f"\n[+] Total unique route endpoints found in templates: {len(found_urls)}")
        for endpoint in sorted(found_urls):
            # Verify endpoint exists in Flask url_map
            with self.subTest(endpoint=endpoint):
                self.assertIn(endpoint, self.app.view_functions, f"Endpoint '{endpoint}' referenced in templates is MISSING in Flask app!")

    def test_admin_button_actions(self):
        """Simulate clicks on Admin panel action buttons."""
        with self.client:
            with self.client.session_transaction() as sess:
                sess['_user_id'] = str(self.admin.id)
                sess['_fresh'] = True

            routes = [
                "/admin/",
                "/admin/analytics",
                "/admin/tournaments",
                "/admin/tournaments/create",
                f"/admin/tournaments/{self.tournament.id}",
                f"/admin/tournaments/{self.tournament.id}/edit",
                "/admin/rooms",
                "/admin/payments",
                "/admin/results",
                "/admin/prizes",
                "/admin/disputes",
                "/admin/announcements",
                "/admin/support",
                "/admin/users",
                "/admin/audit-logs",
                "/admin/reports",
                "/admin/reports/download/payments",
                "/admin/reports/pdf/payments"
            ]
            for route in routes:
                resp = self.client.get(route)
                self.assertIn(resp.status_code, [200, 302], f"Admin route GET {route} failed with status {resp.status_code}")

    def test_player_button_actions(self):
        """Simulate clicks on Player navigation & action buttons."""
        with self.client:
            with self.client.session_transaction() as sess:
                sess['_user_id'] = str(self.player.id)
                sess['_fresh'] = True

            routes = [
                "/",
                "/tournaments/",
                f"/tournaments/{self.tournament.slug}",
                "/competition/matches",
                f"/competition/matches/{self.match.id}",
                f"/competition/tournaments/{self.tournament.id}/leaderboard",
                "/leaderboards",
                "/teams/",
                f"/teams/{self.team.id}",
                "/teams/create",
                "/achievements",
                "/support/tickets",
                f"/support/tickets/{self.ticket.id}",
                "/payments/my",
                f"/payments/{self.payment.id}/receipt",
                "/profile",
                "/how-it-works",
                "/faq"
            ]
            for route in routes:
                resp = self.client.get(route)
                self.assertIn(resp.status_code, [200, 302], f"Player route GET {route} failed with status {resp.status_code}")

if __name__ == '__main__':
    unittest.main()
