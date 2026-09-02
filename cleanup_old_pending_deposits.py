from app import create_app
from app.extensions import db
from app.models.wallet import WalletTransaction

def cleanup_all_pending():
    app = create_app("development")
    with app.app_context():
        pending_txs = WalletTransaction.query.filter_by(status="pending").all()
        print(f"Found {len(pending_txs)} old pending deposit transactions in DB.")

        for tx in pending_txs:
            tx.status = "SUCCESS"
            wallet = tx.wallet
            amt = float(tx.amount or 0)
            coins = int(amt)

            if wallet:
                wallet.available_balance = float(wallet.available_balance or 0) + amt
                wallet.total_added = float(wallet.total_added or 0) + amt
                if wallet.user:
                    wallet.user.coins_balance = (wallet.user.coins_balance or 0) + coins
                    print(f" -> Marked Tx #{tx.id} as SUCCESS & Credited ⚡{coins} Coins to User @{wallet.user.username}")

        db.session.commit()
        print("[SUCCESS] All old pending deposit transactions have been auto-approved & converted to SUCCESS!")

if __name__ == "__main__":
    cleanup_all_pending()
