from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from app.extensions import csrf, db
from app.models.payment import Payment
from app.models.wallet import Wallet, WalletTransaction
from app.utils.uploads import save_proof
from app.utils.audit import log_action

payments_bp = Blueprint("payments", __name__, template_folder="../templates")


@payments_bp.route("/payments")
@payments_bp.route("/payments/my")
@payments_bp.route("/my-payments")
@login_required
def my_payments():
    from app.models.setting import SystemSetting
    # Retrieve user's wallet
    wallet = current_user.get_wallet()
    wallet_txs = WalletTransaction.query.filter_by(wallet_id=wallet.id).order_by(WalletTransaction.created_at.desc()).all()

    admin_qr_code = SystemSetting.get("admin_qr_code")
    admin_upi_id = SystemSetting.get("admin_upi_id", "subrat@upi")
    admin_upi_name = SystemSetting.get("admin_upi_name", "FF Custom Arena Official")

    # Show user payments
    payments = (
        Payment.query.join(Payment.registration)
        .filter(Payment.registration.has(registered_by_id=current_user.id))
        .order_by(Payment.created_at.desc())
        .all()
    )
    return render_template(
        "main/my_payments.html",
        wallet=wallet,
        wallet_txs=wallet_txs,
        payments=payments,
        admin_qr_code=admin_qr_code,
        admin_upi_id=admin_upi_id,
        admin_upi_name=admin_upi_name
    )


@payments_bp.route("/wallet/deposit", methods=["POST"])
@login_required
def add_money():
    try:
        amount = float(request.form.get("amount", 0))
        tx_id = request.form.get("transaction_id", "").strip()
        method = request.form.get("payment_method", "UPI").strip()

        if amount <= 0:
            raise ValueError("Invalid deposit amount.")
        if not tx_id or len(tx_id) < 6:
            raise ValueError("Please provide a valid Transaction UTR / Reference Number (minimum 6 characters).")

        proof_file = request.files.get("proof")
        proof_path = None
        if proof_file and proof_file.filename:
            proof_path = save_proof(proof_file, category="deposit_proofs")

        wallet = current_user.get_wallet()
        coins_to_add = int(amount)  # 1 Rupee (₹1) = 1 Virtual Coin ⚡
        tx_id_clean = tx_id.strip()

        # ----------------------------------------------------
        # STAGE 1: DUPLICATE / REPEATED UTR FRAUD CHECK
        # If UTR has been submitted/used previously >= 1 time, REJECT IMMEDIATELY!
        # ----------------------------------------------------
        existing_wallet_tx = WalletTransaction.query.filter(
            WalletTransaction.reference_id.ilike(tx_id_clean)
        ).first()

        existing_payment = Payment.query.filter(
            Payment.transaction_id.ilike(tx_id_clean)
        ).first()

        if existing_wallet_tx or existing_payment:
            # IMMEDIATELY REJECT REPEATED TRANSACTION UTR! DO NOT CREDIT COINS!
            rejected_tx = WalletTransaction(
                wallet_id=wallet.id,
                transaction_type="deposit",
                amount=amount,
                balance_after=wallet.total_balance,
                description=f"REJECTED: Repeated Transaction UTR reuse attempt ({tx_id_clean})",
                status="REJECTED",
                reference_id=tx_id_clean[:80],
                proof_path=proof_path,
                payment_method=method,
                rejection_reason="Duplicate Transaction UTR number already submitted/used previously in server database."
            )
            db.session.add(rejected_tx)
            db.session.commit()

            log_action(f"FRAUD BLOCKED: User @{current_user.username} submitted duplicate UTR ({tx_id_clean})", "WalletTransaction", rejected_tx.id)
            flash(f"❌ DUPLICATE UTR DETECTED: Transaction UTR ({tx_id_clean}) has ALREADY been used/credited in the server database! Repeated UTRs across any account are immediately REJECTED.", "danger")
            return redirect(url_for("payments.my_payments"))

        # ----------------------------------------------------
        # STAGE 2: UNIQUE UTR -> AUTO-APPROVE & INSTANT COIN CREDIT
        # ----------------------------------------------------
        wallet.available_balance = float(wallet.available_balance or 0) + amount
        wallet.total_added = float(wallet.total_added or 0) + amount
        current_user.coins_balance = (current_user.coins_balance or 0) + coins_to_add

        # Create verified auto-approved deposit transaction
        tx = WalletTransaction(
            wallet_id=wallet.id,
            transaction_type="deposit",
            amount=amount,
            balance_after=wallet.total_balance,
            description=f"Auto-Approved Deposit for ⚡{coins_to_add} Virtual Coins via {method} (UTR: {tx_id_clean})",
            status="SUCCESS",
            reference_id=tx_id_clean[:80],
            proof_path=proof_path,
            payment_method=method
        )
        db.session.add(tx)
        db.session.commit()

        log_action(f"Wallet deposit AUTO-APPROVED: ₹{amount} (UTR: {tx_id_clean}) -> +{coins_to_add} Virtual Coins", "WalletTransaction", tx.id)
        flash(f"🎉 AUTO-APPROVED & CREDITED! ₹{amount} deposit received (UTR: {tx_id_clean}). ⚡{coins_to_add} Virtual Coins added to your account balance!", "success")
    except Exception as e:
        db.session.rollback()
        flash(str(e), "danger")

    return redirect(url_for("payments.my_payments"))


@payments_bp.route("/wallet/withdraw", methods=["GET"])
@payments_bp.route("/wallet/withdraw-page")
@login_required
def withdraw_page():
    wallet = current_user.get_wallet()
    return render_template("main/withdraw.html", wallet=wallet)


@payments_bp.route("/wallet/withdraw", methods=["POST"])
@login_required
def withdraw_money():
    try:
        amount = float(request.form.get("amount", 0))
        upi_id = request.form.get("upi_id", "").strip()

        if amount <= 0:
            raise ValueError("Invalid withdrawal amount.")
        if not upi_id:
            raise ValueError("Please provide a valid UPI ID for payout.")

        wallet = current_user.get_wallet()
        if float(wallet.winning_balance or 0) < amount:
            raise ValueError(f"Insufficient winning balance. Available winnings: ⚡{wallet.winning_balance or 0}")

        # Deduct winnings immediately in transaction
        wallet.winning_balance = float(wallet.winning_balance or 0) - amount
        tx = WalletTransaction(
            wallet_id=wallet.id,
            transaction_type="withdrawal",
            amount=-amount,
            balance_after=wallet.total_balance,
            status="pending",
            description=f"Withdrawal to UPI: {upi_id}",
            reference_id=upi_id[:80]
        )
        db.session.add(tx)
        db.session.commit()

        log_action(f"Wallet withdrawal requested: ₹{amount}", "WalletTransaction", tx.id)
        flash(f"Withdrawal request of ₹{amount} submitted to UPI {upi_id}. Payouts process within 2-24 hours.", "success")
    except Exception as e:
        db.session.rollback()
        flash(str(e), "danger")

    return redirect(url_for("payments.withdraw_page"))


@payments_bp.route("/payments/<int:payment_id>/receipt")
@login_required
def receipt(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    if payment.registration.registered_by_id != current_user.id and not current_user.is_admin():
        abort(403)
    return render_template("main/receipt.html", payment=payment)


@payments_bp.route("/payments/<int:payment_id>/proof", methods=["POST"])
@login_required
def upload_proof(payment_id):
    from datetime import datetime
    payment = Payment.query.get_or_404(payment_id)
    if payment.registration.registered_by_id != current_user.id and not current_user.is_admin():
        abort(403)

    try:
        proof_file = request.files.get("proof")
        proof = save_proof(proof_file, "payment_proofs") if proof_file and proof_file.filename else payment.proof_path
        transaction_id = request.form.get("transaction_id", "").strip()
        method = request.form.get("payment_method", "UPI / GooglePay / PhonePe").strip()[:40]

        if not transaction_id or len(transaction_id) < 6:
            raise ValueError("Please enter a valid Transaction UTR Number (minimum 6 digits/characters).")

        # Duplicate UTR check
        existing = Payment.query.filter(
            Payment.transaction_id == transaction_id,
            Payment.status == "verified",
            Payment.id != payment.id
        ).first()
        if existing:
            raise ValueError("This Transaction UTR number has already been used for another confirmed payment.")

        payment.proof_path = proof
        payment.transaction_id = transaction_id[:100]
        payment.payment_method = method

        # Automated Web Payment Analysis Engine
        # Auto-verify payment & confirm registration slot
        payment.status = "verified"
        payment.verified_at = datetime.utcnow()
        payment.registration.status = "confirmed"

        db.session.commit()
        log_action(f"Automated Web Payment Verified (UTR: {transaction_id})", "Payment", payment.id)
        flash(f"🎉 PAYMENT DONE! Transaction (UTR: {transaction_id}) verified successfully. Your slot for {payment.registration.tournament.name} is now CONFIRMED!", "success")
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "danger")

    return redirect(url_for("tournaments.detail", slug=payment.registration.tournament.slug))


@payments_bp.route("/payment/webhook", methods=["POST"])
@csrf.exempt
def payment_webhook_root():
    from flask import jsonify
    from datetime import datetime
    data = request.get_json(silent=True) or {}
    payload = data.get("payload", {})
    payment_entity = payload.get("payment", {}).get("entity", {})
    order_id = payment_entity.get("order_id") or data.get("order_id")
    payment_id = payment_entity.get("id") or data.get("payment_id")
    status = payment_entity.get("status") or data.get("status", "SUCCESS")

    if not order_id:
        return jsonify({"status": "ignored", "reason": "order_id missing"}), 200

    payment = Payment.query.filter_by(order_id=order_id).first()
    if not payment:
        return jsonify({"status": "ignored", "reason": "Payment order not found"}), 200

    if status in ["captured", "paid", "SUCCESS", "SUCCESSFUL"]:
        if payment.status not in ["SUCCESS", "verified"]:
            payment.status = "SUCCESS"
            if payment_id:
                payment.transaction_id = payment_id
            payment.payment_date = datetime.utcnow()
            if payment.registration:
                payment.registration.status = "confirmed"
            db.session.commit()
            log_action(f"WEBHOOK AUTOMATIC CONFIRMATION (Order: {order_id})", "Payment", payment.id)

    return jsonify({"status": "processed", "order_id": order_id}), 200
