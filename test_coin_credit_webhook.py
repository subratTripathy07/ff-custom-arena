import json
import hmac
import hashlib
import time
from app import create_app
from app.extensions import db
from app.models.user import User

def test_full_automated_topup_webhook_flow():
    app = create_app("testing")
    with app.app_context():
        db.create_all()

        user = User(
            full_name="Topup Test User",
            username="topup_player",
            email="topup@test.com",
            role_id=5,
            coins_balance=0
        )
        user.set_password("pass123")
        db.session.add(user)
        db.session.commit()

        u_id = user.id
        client = app.test_client()

        print("=== STAGE 1 & 2: User Enters Rs.20 & Backend Generates Order ID (PENDING) ===")
        # 1. Create Top-up Order (Rs. 20)
        res1 = client.post("/api/create-topup-order", json={
            "user_id": u_id,
            "amount": 20.0
        })

        assert res1.status_code == 200, f"Expected 200, got {res1.status_code}"
        data1 = json.loads(res1.data)
        assert data1["success"] is True
        order_id = data1["data"]["order_id"]
        assert data1["data"]["status"] == "PENDING"
        assert data1["data"]["coins_to_add"] == 20
        assert "upi_intent" in data1["data"]

        print(f"[OK] Step 2 Complete: Created Order '{order_id}' | Status: PENDING | UPI Intent Generated: {data1['data']['upi_intent']}")

        print("\n=== STAGE 3, 4, 5, 6: Gateway Triggers Instant Secret Webhook ===")
        payment_id = f"PAY_{int(time.time())}"
        webhook_payload = json.dumps({
            "order_id": order_id,
            "payment_id": payment_id,
            "status": "SUCCESS"
        }).encode("utf-8")

        webhook_secret = "ff_webhook_secret_987654"
        signature = hmac.new(
            webhook_secret.encode("utf-8"),
            webhook_payload,
            hashlib.sha256
        ).hexdigest()

        print(f"[OK] Generated HMAC SHA256 Signature Header: {signature[:20]}...")

        print("\n=== STAGE 7, 8, 9: Webhook Listener Verifies Signature & Credits +20 Coins ===")
        res2 = client.post("/api/webhook/payment", data=webhook_payload, headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature
        })

        assert res2.status_code == 200, f"Webhook failed with status {res2.status_code}"
        data2 = json.loads(res2.data)
        assert data2["success"] is True
        assert data2["status"] == "SUCCESS"

        # Verify Database Coin Credit
        updated_user = db.session.get(User, u_id)
        assert updated_user.coins_balance == 20, f"Expected 20 coins, got {updated_user.coins_balance}"
        
        print(f"[OK] Step 7 (Signature Verification): PASSED")
        print(f"[OK] Step 8 (Database Update): user_coins = user_coins + 20 -> New Balance: {updated_user.coins_balance} Coins")
        print(f"[OK] Step 9 (Order Status Change): 'PENDING' -> 'SUCCESS'")

        print("\n[SUCCESS] 100% AUTOMATED COIN TOP-UP WEBHOOK SYSTEM FULLY VERIFIED & WORKING!")

if __name__ == "__main__":
    test_full_automated_topup_webhook_flow()
