from app import create_app
from app.extensions import db
from app.models.wallet import WalletTransaction, Wallet
from app.models.user import User

def auto_credit_pending_deposits():
    app = create_app("development")
    with app.app_context():
        pending_txs = WalletTransaction.query.filter(
            WalletTransaction.transaction_type == "deposit",
            WalletTransaction.status == "pending"
        ).all()

        print(f"Found {len(pending_txs)} pending deposit transactions.")

        for tx in pending_txs:
            wallet = tx.wallet
            amt = float(tx.amount or 0)
            coins = int(amt)

            tx.status = "SUCCESS"
            wallet.available_balance = float(wallet.available_balance or 0) + amt
            wallet.total_added = float(wallet.total_added or 0) + amt
            tx.balance_after = wallet.total_balance

            if wallet.user:
                wallet.user.coins_balance = (wallet.user.coins_balance or 0) + coins
                print(f"[+] Credited {coins} Virtual Coins to User @{wallet.user.username} (User #{wallet.user_id}) for Deposit Tx #{tx.id} (₹{amt})")

        db.session.commit()
        print("[SUCCESS] All pending deposits processed & coins credited!")

if __name__ == "__main__":
    auto_credit_pending_deposits()
