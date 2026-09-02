from datetime import datetime, timedelta
from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.tournament import Tournament, TournamentRegistration
from app.models.team import Team, TeamMember

def test_join_tournament_coins_and_race_condition():
    app = create_app("testing")
    with app.app_context():
        db.create_all()

        # Create test admin user
        admin = User(
            full_name="Admin User",
            username="admin_test",
            email="admin@test.com",
            role_id=1
        )
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.flush()

        # Create test tournament
        tournament = Tournament(
            name="FF Pro Championship",
            slug="ff-pro-championship-coins-test",
            tournament_type="squad",
            max_teams=48,
            entry_fee=20, # 20 Coins
            prize_pool=1000,
            registration_deadline=datetime.utcnow() + timedelta(days=2),
            start_time=datetime.utcnow() + timedelta(days=3),
            status="registration_open",
            created_by_id=admin.id
        )
        db.session.add(tournament)
        db.session.flush()

        # Create test user 1 with low coins (5 Coins)
        user1 = User(
            full_name="Player One",
            username="player1",
            email="player1@test.com",
            role_id=5,
            coins_balance=5 # Insufficient!
        )
        user1.set_password("pass123")
        db.session.add(user1)
        db.session.flush()

        team1 = Team(name="Team Alpha", captain_id=user1.id, is_active=True)
        db.session.add(team1)
        db.session.flush()
        db.session.add(TeamMember(team_id=team1.id, user_id=user1.id))
        db.session.commit()

        client = app.test_client()

        headers = {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}

        # Test Case 1: Insufficient Coins Error Check
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user1.id)

        res1 = client.post(f"/tournaments/{tournament.slug}/join", json={
            "team_id": team1.id,
            "slot_number": 5,
            "in_game_name": "P1_Alpha"
        }, headers=headers)

        assert res1.status_code == 400, f"Expected 400 for insufficient coins, got {res1.status_code}: {res1.data}"
        data1 = res1.get_json()
        assert data1["error_code"] == "INSUFFICIENT_COINS", f"Expected INSUFFICIENT_COINS, got {data1}"
        print(f"[OK] Test 1 Passed: Insufficient Coins Error triggered correctly ({data1['message']})")

        # Test Case 2: Successful Slot Booking with Virtual Coins
        # Top-up user1 with 50 coins
        user1_up = User.query.get(user1.id)
        user1_up.coins_balance = 50
        db.session.commit()

        res2 = client.post(f"/tournaments/{tournament.slug}/join", json={
            "team_id": team1.id,
            "slot_number": 5,
            "in_game_name": "P1_Alpha"
        }, headers=headers)

        assert res2.status_code == 200, f"Expected 200 for valid booking, got {res2.status_code}: {res2.data}"
        data2 = res2.get_json()
        assert data2["success"] is True
        assert data2["remaining_coins"] == 30 # 50 - 20 = 30 Coins
        assert data2["slot_number"] == 5
        print(f"[OK] Test 2 Passed: Slot #5 booked successfully! Deducted 20 Coins. Remaining: {data2['remaining_coins']} Coins.")

        # Test Case 3: Race Condition / Microsecond Duplicate Slot Booking Block
        # Create user 2 with 50 coins trying to book the SAME slot #5
        user2 = User(
            full_name="Player Two",
            username="player2",
            email="player2@test.com",
            role_id=5,
            coins_balance=50
        )
        user2.set_password("pass123")
        db.session.add(user2)
        db.session.flush()

        team2 = Team(name="Team Beta", captain_id=user2.id, is_active=True)
        db.session.add(team2)
        db.session.flush()
        db.session.add(TeamMember(team_id=team2.id, user_id=user2.id))
        db.session.commit()

        with client.session_transaction() as sess:
            sess["_user_id"] = str(user2.id)

        res3 = client.post(f"/tournaments/{tournament.slug}/join", json={
            "team_id": team2.id,
            "slot_number": 5, # Same slot!
            "in_game_name": "P2_Beta"
        }, headers=headers)

        data3 = res3.get_json()
        print(f"[DEBUG] res3 status: {res3.status_code}, data: {data3}")
        assert res3.status_code in [400, 409], f"Expected 400 or 409 for duplicate slot booking, got {res3.status_code}"
        assert data3["success"] is False
        print(f"[OK] Test 3 Passed: Duplicate slot booking blocked! ({data3['message']})")

        print("\n[SUCCESS] ALL TOURNAMENT SLOT BOOKING & COINS TESTS PASSED!")

if __name__ == "__main__":
    test_join_tournament_coins_and_race_condition()
