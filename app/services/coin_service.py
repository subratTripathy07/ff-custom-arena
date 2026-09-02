import logging
from sqlalchemy import text
from app.extensions import db
from app.models.user import User
from app.models.coin_topup import CoinTopup

logger = logging.getLogger(__name__)


class CoinService:
    """
    Service class handling Virtual Coins & Top-Up operations with exception handling and atomic transactions.
    """

    @staticmethod
    def create_topup_order(user_id: int, order_id: str, amount: float, coins_to_add: int) -> CoinTopup:
        """
        Creates a new coin top-up record with status 'PENDING'.
        Uses parameterized statements & Exception Handling.
        """
        try:
            topup = CoinTopup(
                user_id=user_id,
                order_id=order_id,
                amount=amount,
                coins_to_add=coins_to_add,
                status="PENDING"
            )
            db.session.add(topup)
            db.session.commit()
            logger.info(f"Created topup order {order_id} for user {user_id}")
            return topup
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating topup order: {e}")
            raise e

    @staticmethod
    def complete_topup_order(order_id: str, payment_id: str, is_success: bool = True) -> bool:
        """
        Completes topup order: updates status to SUCCESS/FAILED and credits user coins_balance atomically.
        """
        try:
            topup = CoinTopup.query.filter_by(order_id=order_id).with_for_update().first()
            if not topup:
                raise ValueError(f"Top-up order {order_id} not found.")

            if topup.status != "PENDING":
                return True # Already processed

            topup.status = "SUCCESS" if is_success else "FAILED"
            topup.payment_id = payment_id

            if is_success:
                user = User.query.filter_by(id=topup.user_id).with_for_update().first()
                if user:
                    user.coins_balance = (user.coins_balance or 0) + topup.coins_to_add

            db.session.commit()
            logger.info(f"Topup order {order_id} marked as {topup.status}")
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error completing topup order {order_id}: {e}")
            raise e
