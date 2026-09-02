<?php
/**
 * Tournament Slot Booking API - join_tournament.php
 * Handles Virtual Coins deduction, DB Row Locking (FOR UPDATE),
 * Unique Constraint (tournament_id, slot_number) race-condition protection,
 * and Atomic Transactions (BEGIN TRANSACTION ... COMMIT).
 */

header('Content-Type: application/json');

// Database credentials
$host = getenv('DB_HOST') ?: 'localhost';
$db   = getenv('DB_NAME') ?: 'ff_custom_arena';
$user = getenv('DB_USER') ?: 'root';
$pass = getenv('DB_PASSWORD') ?: 'subrat7894';

try {
    $pdo = new PDO("mysql:host=$host;dbname=$db;charset=utf8mb4", $user, $pass, [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        PDO::ATTR_EMULATE_PREPARES => false
    ]);

    // Parse Input (JSON or POST)
    $rawInput = file_get_contents('php://input');
    $input = json_decode($rawInput, true) ?: $_POST;

    $userId       = isset($input['user_id']) ? (int)$input['user_id'] : 0;
    $tournamentId = isset($input['tournament_id']) ? (int)$input['tournament_id'] : 0;
    $slotNumber   = isset($input['slot_number']) ? (int)$input['slot_number'] : 0;
    $teamId       = isset($input['team_id']) ? (int)$input['team_id'] : 0;
    $inGameName   = isset($input['in_game_name']) ? trim($input['in_game_name']) : '';

    if ($userId <= 0 || $tournamentId <= 0 || $slotNumber <= 0) {
        http_response_code(400);
        echo json_encode([
            "success" => false,
            "message" => "user_id, tournament_id, and slot_number are required."
        ]);
        exit;
    }

    // =========================================================================
    // START ATOMIC DATABASE TRANSACTION WITH ROW LOCKING (FOR UPDATE)
    // =========================================================================
    $pdo->beginTransaction();

    // 1. Lock User Record with FOR UPDATE to inspect coins_balance safely
    $stmtUser = $pdo->prepare("SELECT id, username, coins_balance FROM users WHERE id = :user_id FOR UPDATE");
    $stmtUser->execute([':user_id' => $userId]);
    $userRow = $stmtUser->fetch();

    if (!$userRow) {
        $pdo->rollBack();
        http_response_code(444);
        echo json_encode(["success" => false, "message" => "User record not found."]);
        exit;
    }

    // 2. Lock Tournament Record with FOR UPDATE to inspect entry_fee & status safely
    $stmtTourney = $pdo->prepare(
        "SELECT id, name, entry_fee, max_teams, status, registration_deadline 
         FROM tournaments WHERE id = :tournament_id FOR UPDATE"
    );
    $stmtTourney->execute([':tournament_id' => $tournamentId]);
    $tourneyRow = $stmtTourney->fetch();

    if (!$tourneyRow) {
        $pdo->rollBack();
        http_response_code(404);
        echo json_encode(["success" => false, "message" => "Tournament not found."]);
        exit;
    }

    if ($tourneyRow['status'] !== 'registration_open') {
        $pdo->rollBack();
        http_response_code(400);
        echo json_encode(["success" => false, "message" => "Registration is closed for this tournament."]);
        exit;
    }

    if ($slotNumber < 1 || $slotNumber > (int)$tourneyRow['max_teams']) {
        $pdo->rollBack();
        http_response_code(400);
        echo json_encode([
            "success" => false, 
            "message" => "Invalid slot number. Choose between 1 and " . $tourneyRow['max_teams']
        ]);
        exit;
    }

    // 3. Lock & Check if Slot Number is already booked for this tournament
    $stmtSlot = $pdo->prepare(
        "SELECT id FROM tournament_registrations 
         WHERE tournament_id = :tournament_id AND slot_number = :slot_number FOR UPDATE"
    );
    $stmtSlot->execute([
        ':tournament_id' => $tournamentId,
        ':slot_number'   => $slotNumber
    ]);

    if ($stmtSlot->fetch()) {
        $pdo->rollBack();
        http_response_code(409);
        echo json_encode([
            "success" => false,
            "message" => "Slot #{$slotNumber} has already been booked by another player. Please select a different slot."
        ]);
        exit;
    }

    // 4. CHECK USER VIRTUAL COINS BALANCE
    $entryFee = (int)$tourneyRow['entry_fee'];
    $currentCoins = (int)$userRow['coins_balance'];

    if ($currentCoins < $entryFee) {
        $pdo->rollBack();
        http_response_code(400);
        echo json_encode([
            "success" => false,
            "error_code" => "INSUFFICIENT_COINS",
            "message" => "Insufficient Coins! Required: {$entryFee} Coins, but your balance is {$currentCoins} Coins. Please Top-Up your wallet."
        ]);
        exit;
    }

    // 5. Check/Fallback Team ID
    if ($teamId <= 0) {
        $stmtTeam = $pdo->prepare("SELECT id FROM teams WHERE captain_id = :user_id AND is_active = 1 LIMIT 1");
        $stmtTeam->execute([':user_id' => $userId]);
        $teamRow = $stmtTeam->fetch();
        if ($teamRow) {
            $teamId = (int)$teamRow['id'];
        } else {
            // Auto-create individual/solo team for user
            $teamName = $userRow['username'] . "'s Squad";
            $stmtNewTeam = $pdo->prepare(
                "INSERT INTO teams (name, captain_id, tag, is_active) VALUES (:name, :captain_id, :tag, 1)"
            );
            $stmtNewTeam->execute([
                ':name' => $teamName,
                ':captain_id' => $userId,
                ':tag' => strtoupper(substr($userRow['username'], 0, 4))
            ]);
            $teamId = (int)$pdo->lastInsertId();
        }
    }

    // 6. DEDUCT VIRTUAL COINS ATOMICALLY
    $stmtDeduct = $pdo->prepare(
        "UPDATE users SET coins_balance = coins_balance - :entry_fee WHERE id = :user_id"
    );
    $stmtDeduct->execute([
        ':entry_fee' => $entryFee,
        ':user_id'   => $userId
    ]);

    // 7. CONFIRM SLOT RESERVATION & INSERT REGISTRATION
    $regCode = "FF-REG-" . strtoupper(bin2hex(random_bytes(4)));
    $ign = !empty($inGameName) ? $inGameName : $userRow['username'];

    $stmtInsertReg = $pdo->prepare(
        "INSERT INTO tournament_registrations 
         (registration_code, tournament_id, team_id, registered_by_id, slot_number, in_game_name, status, created_at)
         VALUES (:code, :tournament_id, :team_id, :user_id, :slot_number, :ign, 'confirmed', NOW())"
    );
    $stmtInsertReg->execute([
        ':code'          => $regCode,
        ':tournament_id' => $tournamentId,
        ':team_id'       => $teamId,
        ':user_id'       => $userId,
        ':slot_number'   => $slotNumber,
        ':ign'           => $ign
    ]);

    $regId = $pdo->lastInsertId();

    // 8. RECORD WALLET TRANSACTION LOG FOR AUDITING
    $stmtWalletTx = $pdo->prepare(
        "INSERT INTO wallet_transactions 
         (wallet_id, transaction_type, amount, balance_after, status, description, reference_id, created_at)
         SELECT id, 'tournament_entry', :amount, (available_balance + winning_balance), 'SUCCESS', :desc, :ref, NOW()
         FROM wallets WHERE user_id = :user_id"
    );
    $stmtWalletTx->execute([
        ':amount'  => -$entryFee,
        ':desc'    => "Entry fee deduction ({$entryFee} Coins) for " . $tourneyRow['name'] . " (Slot #{$slotNumber})",
        ':ref'     => "REG-{$regCode}",
        ':user_id' => $userId
    ]);

    // COMMIT TRANSACTION
    $pdo->commit();

    $remainingCoins = $currentCoins - $entryFee;

    echo json_encode([
        "success" => true,
        "message" => "🎉 MATCH SLOT BOOKED SUCCESSFULLY! {$entryFee} Coins deducted. Slot #{$slotNumber} confirmed!",
        "registration_id" => (int)$regId,
        "registration_code" => $regCode,
        "tournament_id" => $tournamentId,
        "slot_number" => $slotNumber,
        "deducted_coins" => $entryFee,
        "remaining_coins" => $remainingCoins
    ]);

} catch (PDOException $e) {
    if (isset($pdo) && $pdo->inTransaction()) {
        $pdo->rollBack();
    }

    // Handle Microsecond Race Condition SQL Duplicate Error (23000)
    if ($e->getCode() == 23000 || strpos($e->getMessage(), 'uq_tournament_slot') !== false) {
        http_response_code(409);
        echo json_encode([
            "success" => false,
            "message" => "Race condition detected! Slot #{$slotNumber} was reserved micro-seconds earlier by another player."
        ]);
    } else {
        http_response_code(500);
        echo json_encode([
            "success" => false,
            "message" => "Database error: " . $e->getMessage()
        ]);
    }
} catch (Exception $e) {
    if (isset($pdo) && $pdo->inTransaction()) {
        $pdo->rollBack();
    }
    http_response_code(500);
    echo json_encode([
        "success" => false,
        "message" => "Server error: " . $e->getMessage()
    ]);
}
