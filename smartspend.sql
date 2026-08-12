-- ============================================================
-- SmartSpend-Pro Database Schema
-- MySQL 8.0+
-- (The `smartspend_pro` database itself is created by database.py
--  before this script runs, so no CREATE DATABASE / USE here.)
-- ============================================================

-- ---------- USERS ----------
CREATE TABLE IF NOT EXISTS users (
    user_id        INT AUTO_INCREMENT PRIMARY KEY,
    full_name      VARCHAR(150) NOT NULL,
    username       VARCHAR(50)  NOT NULL UNIQUE,
    email          VARCHAR(150) NOT NULL UNIQUE,
    password_hash  VARCHAR(255) NOT NULL,
    salt           VARCHAR(64)  NOT NULL,
    currency       VARCHAR(10)  NOT NULL DEFAULT 'INR',
    theme          VARCHAR(10)  NOT NULL DEFAULT 'dark',
    monthly_budget DOUBLE       NOT NULL DEFAULT 0,
    is_verified    TINYINT(1)   NOT NULL DEFAULT 0,
    created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ---------- EMAIL OTP (signup / login verification codes) ----------
CREATE TABLE IF NOT EXISTS email_otp (
    otp_id       INT AUTO_INCREMENT PRIMARY KEY,
    user_id      INT NOT NULL,
    code         VARCHAR(6) NOT NULL,
    expires_at   DATETIME NOT NULL,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------- CATEGORIES ----------
CREATE TABLE IF NOT EXISTS categories (
    category_id  INT AUTO_INCREMENT PRIMARY KEY,
    user_id      INT NOT NULL,
    name         VARCHAR(100) NOT NULL,
    type         VARCHAR(10) NOT NULL,
    icon         VARCHAR(10) DEFAULT '💰',
    CONSTRAINT chk_category_type CHECK (type IN ('income','expense')),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------- INCOME ----------
CREATE TABLE IF NOT EXISTS income (
    income_id    INT AUTO_INCREMENT PRIMARY KEY,
    user_id      INT NOT NULL,
    category_id  INT,
    amount       DOUBLE NOT NULL,
    source       VARCHAR(150) NOT NULL,
    date         DATE NOT NULL,
    note         TEXT,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_income_amount CHECK (amount > 0),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES categories(category_id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- ---------- EXPENSE ----------
CREATE TABLE IF NOT EXISTS expense (
    expense_id   INT AUTO_INCREMENT PRIMARY KEY,
    user_id      INT NOT NULL,
    category_id  INT,
    amount       DOUBLE NOT NULL,
    payee        VARCHAR(150) NOT NULL,
    date         DATE NOT NULL,
    payment_mode VARCHAR(30) NOT NULL DEFAULT 'Cash',
    note         TEXT,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_expense_amount CHECK (amount > 0),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES categories(category_id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- ---------- INDEXES ----------
-- (created individually in database.py's schema runner, which
--  silently skips "duplicate key name" errors on repeat launches,
--  since MySQL has no native CREATE INDEX IF NOT EXISTS)
CREATE INDEX idx_income_user_date  ON income(user_id, date);
CREATE INDEX idx_expense_user_date ON expense(user_id, date);
CREATE INDEX idx_categories_user   ON categories(user_id);

-- ---------- DEFAULT CATEGORIES (inserted per-user at registration time via Python) ----------
