<?php
/**
 * Virtual Coin & Top-Up System - PDO Database Service
 * Implements Prepared Statements & Transactional Exception Handling
 */

class CoinTopupPDO {
    private $pdo;

    public function __construct(PDO $pdo) {
        $this->pdo = $pdo;
        // Ensure PDO raises exceptions on error
        $this->pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    }

    /**
     * Audit and verify/create schema tables
     */
    public function auditAndUpdateSchema(): bool {
        try {
            $this->pdo->beginTransaction();

            // 1. Check and add coins_balance / winnings_balance to users table if missing
            $checkCoins = $this->pdo->query("SHOW COLUMNS FROM `users` LIKE 'coins_balance'");
            if ($checkCoins->rowCount() === 0) {
                $this->pdo->exec("ALTER TABLE `users` ADD COLUMN `coins_balance` INT NOT NULL DEFAULT 0");
            }

            $checkWinnings = $this->pdo->query("SHOW COLUMNS FROM `users` LIKE 'winnings_balance'");
            if ($checkWinnings->rowCount() === 0) {
                $this->pdo->exec("ALTER TABLE `users` ADD COLUMN `winnings_balance` DECIMAL(10, 2) NOT NULL DEFAULT 0.00");
            }

            // 2. Create coin_topups table if missing
            $sql = "CREATE TABLE IF NOT EXISTS `coin_topups` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `user_id` INT NOT NULL,
                `order_id` VARCHAR(100) NOT NULL UNIQUE,
                `amount` DECIMAL(10, 2) NOT NULL,
                `coins_to_add` INT NOT NULL,
                `status` VARCHAR(20) NOT NULL DEFAULT 'PENDING',
                `payment_id` VARCHAR(100) NULL,
                `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4";
            
            $this->pdo->exec($sql);
            $this->pdo->commit();
            return true;

        } catch (PDOException $e) {
            if ($this->pdo->inTransaction()) {
                $this->pdo->rollBack();
            }
            error_log("DB Audit Error: " . $e->getMessage());
            throw $e;
        }
    }

    /**
     * Create a new top-up order with status 'PENDING'
     */
    public function createTopupOrder(int $userId, string $orderId, float $amount, int $coinsToAdd): bool {
        $sql = "INSERT INTO `coin_topups` (`user_id`, `order_id`, `amount`, `coins_to_add`, `status`) 
                VALUES (:user_id, :order_id, :amount, :coins_to_add, 'PENDING')";

        try {
            $stmt = $this->pdo->prepare($sql);
            return $stmt->execute([
                ':user_id' => $userId,
                ':order_id' => $orderId,
                ':amount' => $amount,
                ':coins_to_add' => $coinsToAdd
            ]);
        } catch (PDOException $e) {
            error_log("Failed to create topup order: " . $e->getMessage());
            throw $e;
        }
    }

    /**
     * Fulfill top-up order: Updates status to SUCCESS/FAILED and credits user coins balance atomically
     */
    public function completeTopupOrder(string $orderId, string $paymentId, bool $isSuccess): bool {
        try {
            $this->pdo->beginTransaction();

            // Fetch order with prepared statement
            $selectStmt = $this->pdo->prepare("SELECT * FROM `coin_topups` WHERE `order_id` = :order_id FOR UPDATE");
            $selectStmt->execute([':order_id' => $orderId]);
            $order = $selectStmt->fetch(PDO::FETCH_ASSOC);

            if (!$order) {
                throw new Exception("Top-up order not found.");
            }

            if ($order['status'] !== 'PENDING') {
                $this->pdo->commit();
                return true; // Already processed
            }

            $newStatus = $isSuccess ? 'SUCCESS' : 'FAILED';

            // 1. Update topup order status and payment_id
            $updateOrderStmt = $this->pdo->prepare(
                "UPDATE `coin_topups` SET `status` = :status, `payment_id` = :payment_id WHERE `order_id` = :order_id"
            );
            $updateOrderStmt->execute([
                ':status' => $newStatus,
                ':payment_id' => $paymentId,
                ':order_id' => $orderId
            ]);

            // 2. If success, add coins to user balance
            if ($isSuccess) {
                $updateUserStmt = $this->pdo->prepare(
                    "UPDATE `users` SET `coins_balance` = `coins_balance` + :coins WHERE `id` = :user_id"
                );
                $updateUserStmt->execute([
                    ':coins' => $order['coins_to_add'],
                    ':user_id' => $order['user_id']
                ]);
            }

            $this->pdo->commit();
            return [
                "success" => true,
                "order_id" => $orderId,
                "user_id" => $order['user_id'],
                "coins_added" => $order['coins_to_add'],
                "amount" => $order['amount'],
                "status" => $newStatus
            ];

        } catch (Exception $e) {
            if ($this->pdo->inTransaction()) {
                $this->pdo->rollBack();
            }
            error_log("Topup processing error: " . $e->getMessage());
            throw $e;
        }
    }
}
