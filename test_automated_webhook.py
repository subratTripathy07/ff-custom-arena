import json
import hmac
import hashlib
from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.coin_topup import CoinTopup
from app.services.coin_service import CoinService

def test_automated_topup_flow():
    app = create_app("testing")
    with app.app_context():
        db.create_all()

        # Create test user
        user = User(
            full_name="Test Gamer",
            username="gamer_test_99",
            email="gamer@test.com",
            role_id=1,
            coins_balance=10
        )
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()

        initial_coins = user.coins_balance
        print(f"[+] Initial User Coins Balance: {initial_coins}")

        # Step 1: Create PENDING Top-Up Order
        client = app.test_client()
        res = client.post("/api/create-topup-order", data={
            "user_id": user.id,
            "amount": 20.0,
            "coins_to_add": 20
        })

        assert res.status_code == 200, f"Order creation failed: {res.data}"
        resp_data = res.get_json()["data"]
        order_id = resp_data["order_id"]
        upi_intent = resp_data["upi_intent"]

        print(f"[+] Top-up Order Created Successfully: {order_id}")
        print(f"[+] Status: {resp_data['status']}")
        print(f"[+] UPI Intent: {upi_intent}")

        # Step 2: Trigger Webhook with HMAC SHA256 Signature Header
        webhook_secret = "ff_webhook_secret_987654"
        webhook_payload = json.dumps({
            "order_id": order_id,
            "payment_id": "PAY_TEST_998877",
            "status": "SUCCESS"
        }).encode("utf-8")

        signature = hmac.new(
            webhook_secret.encode("utf-8"),
            webhook_payload,
            hashlib.sha256
        ).hexdigest()

        webhook_res = client.post(
            "/api/webhook/payment",
            data=webhook_payload,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": signature
            }
        )

        assert webhook_res.status_code == 200, f"Webhook failed: {webhook_res.data}"
        webhook_resp = webhook_res.get_json()
        print(f"[+] Webhook Response: {webhook_resp}")

        # Step 3: Verify User Coins Credit in Database
        updated_user = User.query.get(user.id)
        print(f"[+] Updated User Coins Balance: {updated_user.coins_balance}")
        assert updated_user.coins_balance == initial_coins + 20, "Coins balance was not credited correctly!"

        topup_record = CoinTopup.query.filter_by(order_id=order_id).first()
        assert topup_record.status == "SUCCESS", "Topup status not updated to SUCCESS!"
        print(f"[+] Verified Topup Record Status: {topup_record.status}, Payment ID: {topup_record.payment_id}")

        print("\n[SUCCESS] 100% Automated Coin Credit & Webhook Flow Test Passed!")

if __name__ == "__main__":
    test_automated_topup_flow()
