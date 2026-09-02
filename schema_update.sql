-- ============================================================
-- SQL Schema Update Script: Virtual Coin & Top-Up System
-- Target Database: MySQL / MariaDB / PostgreSQL / SQLite
-- ============================================================

-- 1. Update `users` table to add coins_balance and winnings_balance
ALTER TABLE `users` 
ADD COLUMN IF NOT EXISTS `coins_balance` INT NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS `winnings_balance` DECIMAL(10, 2) NOT NULL DEFAULT 0.00;

-- 2. Create `coin_topups` table
CREATE TABLE IF NOT EXISTS `coin_topups` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `order_id` VARCHAR(100) NOT NULL UNIQUE,
    `amount` DECIMAL(10, 2) NOT NULL,
    `coins_to_add` INT NOT NULL,
    `status` VARCHAR(20) NOT NULL DEFAULT 'PENDING', -- Options: 'PENDING', 'SUCCESS', 'FAILED'
    `payment_id` VARCHAR(100) NULL,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
    INDEX `idx_order_id` (`order_id`),
    INDEX `idx_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
