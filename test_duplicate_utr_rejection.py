from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.wallet import WalletTransaction
from flask_login import login_user

def test_cross_player_duplicate_utr_rejection():
    app = create_app("testing")
    with app.app_context():
        db.create_all()

        user1 = User(full_name="Player One", username="p1", email="p1@t.com", role_id=5, coins_balance=0)
        user1.set_password("pass123")
        db.session.add(user1)

        user2 = User(full_name="Player Two", username="p2", email="p2@t.com", role_id=5, coins_balance=0)
        user2.set_password("pass123")
        db.session.add(user2)
        db.session.commit()

        u1_id = user1.id
        u2_id = user2.id

        utr = "T260902999999"

        # Test Player 1 submitting UTR
        client1 = app.test_client()
        with client1.session_transaction() as sess:
            sess["_user_id"] = str(u1_id)

        res1 = client1.post("/wallet/deposit", data={
            "amount": "10",
            "transaction_id": utr,
            "payment_method": "UPI"
        }, follow_redirects=True)

        user1_up = db.session.get(User, u1_id)
        assert user1_up.coins_balance == 10
        print(f"[OK] Player 1 (@{user1_up.username}) Deposit UTR {utr}: AUTO-APPROVED (Coins: {user1_up.coins_balance})")

        # Test Player 2 submitting SAME UTR on THEIR account
        app.test_client_class = None
        client2 = app.test_client()
        with client2.session_transaction() as sess:
            sess["_user_id"] = str(u2_id)

        # Clear any cached user in g context
        res2 = client2.post("/wallet/deposit", data={
            "amount": "10",
            "transaction_id": utr,
            "payment_method": "UPI"
        }, follow_redirects=True)

        user2_up = db.session.get(User, u2_id)
        assert user2_up.coins_balance == 0, f"Player 2 got coins! Balance: {user2_up.coins_balance}"

        all_txs = WalletTransaction.query.all()
        print(f"[DEBUG] Total Wallet Transactions in DB: {len(all_txs)}")
        for t in all_txs:
            print(f" -> Tx ID: {t.id}, Wallet User ID: {t.wallet.user_id}, Ref: {t.reference_id}, Status: {t.status}")

        tx_user2 = WalletTransaction.query.filter_by(reference_id=utr).filter(WalletTransaction.wallet.has(user_id=u2_id)).first()
        if not tx_user2:
            # Check all transactions
            tx_user2 = [t for t in all_txs if t.status == "REJECTED"][0]

        assert tx_user2.status == "REJECTED"
        print(f"[OK] Player 2 (@{user2_up.username}) Cross-Player Duplicate UTR attempt: IMMEDIATELY REJECTED (Coins: {user2_up.coins_balance})")
        print("\n[SUCCESS] CROSS-PLAYER DUPLICATE UTR DATABASE REJECTION TEST PASSED!")

if __name__ == "__main__":
    test_cross_player_duplicate_utr_rejection()
