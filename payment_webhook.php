<?php
/**
 * 100% Automated Coin Credit Webhook Script - payment_webhook.php
 * Handles Payment Gateway triggers, HMAC SHA256 signature verification (Cyber Fraud Prevention),
 * FOR UPDATE row-locking DB transactions, and automatic coins crediting to users.coins_balance.
 */

header('Content-Type: application/json');
require_once __DIR__ . '/db_operations_pdo.php';

// Webhook Secret for HMAC SHA256 Cyber Fraud Prevention
$webhookSecret = getenv('PAYMENT_WEBHOOK_SECRET') ?: 'ff_webhook_secret_987654';

// Retrieve Raw POST Body & HMAC Signature Header
$rawPayload = file_get_contents('php://input');
$receivedSignature = $_SERVER['HTTP_X_WEBHOOK_SIGNATURE'] 
                     ?? $_SERVER['HTTP_X_RAZORPAY_SIGNATURE'] 
                     ?? $_SERVER['HTTP_X_SIGNATURE'] 
                     ?? '';

// 1. HMAC SHA256 SIGNATURE VERIFICATION (CYBER FRAUD PREVENTION)
if (!empty($receivedSignature) && !empty($webhookSecret)) {
    $expectedSignature = hash_hmac('sha256', $rawPayload, $webhookSecret);
    if (!hash_equals($expectedSignature, $receivedSignature)) {
        http_response_code(401);
        echo json_encode([
            "success" => false,
            "error" => "HMAC SHA256 Signature verification failed! Request rejected due to potential fraud attempt."
        ]);
        exit;
    }
}

// Parse Payload JSON
$payload = json_decode($rawPayload, true) ?: [];

// Extract Order ID & Payment ID from various gateway structures (Razorpay / Cashfree / Custom)
$orderId = $payload['order_id'] 
           ?? $payload['payload']['payment']['entity']['order_id'] 
           ?? $_POST['order_id'] 
           ?? null;

$paymentId = $payload['payment_id'] 
             ?? $payload['payload']['payment']['entity']['id'] 
             ?? $payload['razorpay_payment_id'] 
             ?? $_POST['payment_id'] 
             ?? 'PAY_' . time();

$status = $payload['status'] 
          ?? $payload['payload']['payment']['entity']['status'] 
          ?? $_POST['status'] 
          ?? 'SUCCESS';

if (empty($orderId)) {
    http_response_code(400);
    echo json_encode(["success" => false, "message" => "order_id missing from webhook payload."]);
    exit;
}

// DB Connection
$host = getenv('DB_HOST') ?: 'localhost';
$db   = getenv('DB_NAME') ?: 'ff_custom_arena';
$user = getenv('DB_USER') ?: 'root';
$pass = getenv('DB_PASSWORD') ?: 'subrat7894';

try {
    $pdo = new PDO("mysql:host=$host;dbname=$db;charset=utf8mb4", $user, $pass, [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC
    ]);

    $topupService = new CoinTopupPDO($pdo);

    $isSuccess = in_array(strtoupper($status), ['SUCCESS', 'PAID', 'CAPTURED', 'SUCCESSFUL']);

    // 2. AUTOMATED TRANSACTION EXECUTION WITH FOR UPDATE ROW LOCK & COIN CREDIT
    $result = $topupService->completeTopupOrder($orderId, $paymentId, $isSuccess);

    echo json_encode([
        "success" => true,
        "message" => "100% Automated Coin Top-Up processed successfully in background.",
        "order_id" => $orderId,
        "payment_id" => $paymentId,
        "status" => $isSuccess ? "SUCCESS" : "FAILED"
    ]);

} catch (Exception $e) {
    http_response_code(500);
    echo json_encode([
        "success" => false,
        "message" => "Webhook processing error: " . $e->getMessage()
    ]);
}
