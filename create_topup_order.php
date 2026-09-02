<?php
header('Content-Type: application/json');
require_once __DIR__ . '/db_operations_pdo.php';

// Database connection setup
$host = getenv('DB_HOST') ?: 'localhost';
$db   = getenv('DB_NAME') ?: 'ff_custom_arena';
$user = getenv('DB_USER') ?: 'root';
$pass = getenv('DB_PASSWORD') ?: 'subrat7894';
$charset = 'utf8mb4';

$dsn = "mysql:host=$host;dbname=$db;charset=$charset";
$options = [
    PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
    PDO::ATTR_EMULATE_PREPARES   => false,
];

try {
    $pdo = new PDO($dsn, $user, $pass, $options);
    $topupService = new CoinTopupPDO($pdo);

    // Parse input from JSON payload or POST body
    $rawInput = file_get_contents('php://input');
    $input = json_decode($rawInput, true) ?: $_POST;

    $userId = isset($input['user_id']) ? (int)$input['user_id'] : 0;
    $amount = isset($input['amount']) ? (float)$input['amount'] : 0.0;
    $coinsToAdd = isset($input['coins_to_add']) ? (int)$input['coins_to_add'] : (int)$amount; // ₹1 = 1 Coin default

    if ($userId <= 0 || $amount <= 0) {
        http_response_code(400);
        echo json_encode([
            "success" => false,
            "message" => "Valid user_id and positive amount are required."
        ]);
        exit;
    }

    // Generate unique server-side Order ID
    $orderId = "TOPUP_" . time() . "_" . bin2hex(random_bytes(4));

    // Save Topup Order with PENDING status using Prepared Statements
    $topupService->createTopupOrder($userId, $orderId, $amount, $coinsToAdd);

    // Admin UPI Config
    $adminUpiId = getenv('ADMIN_UPI_ID') ?: 'subrat@upi';
    $adminUpiName = getenv('ADMIN_UPI_NAME') ?: 'FF Custom Arena Official';

    // Generate Deep Link UPI Intent URI
    $upiIntent = "upi://pay?pa=" . urlencode($adminUpiId) .
                 "&pn=" . urlencode($adminUpiName) .
                 "&am=" . number_format($amount, 2, '.', '') .
                 "&tn=" . urlencode("Coin Topup " . $orderId) .
                 "&tr=" . urlencode($orderId) .
                 "&cu=INR";

    echo json_encode([
        "success" => true,
        "message" => "Top-up order created with status PENDING.",
        "order_id" => $orderId,
        "user_id" => $userId,
        "amount" => $amount,
        "coins_to_add" => $coinsToAdd,
        "status" => "PENDING",
        "upi_intent" => $upiIntent,
        "gateway_details" => [
            "currency" => "INR",
            "admin_upi_id" => $adminUpiId,
            "admin_upi_name" => $adminUpiName
        ]
    ]);

} catch (Exception $e) {
    http_response_code(500);
    echo json_encode([
        "success" => false,
        "message" => "Server error: " . $e->getMessage()
    ]);
}
