-- USERS TABLE
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    fullname VARCHAR(100),
    username VARCHAR(50) UNIQUE,
    phone VARCHAR(20) UNIQUE,
    login_password TEXT NOT NULL,
    withdrawal_password TEXT NOT NULL,
    referral_code VARCHAR(20) UNIQUE,
    referred_by VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);



-- USER ACCOUNTS / WALLET
CREATE TABLE IF NOT EXISTS accounts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    deposit_account NUMERIC DEFAULT 0,
    withdraw_account NUMERIC DEFAULT 0,
    income_account NUMERIC DEFAULT 0,
    referral_account NUMERIC DEFAULT 0
);



-- INVESTMENT PLANS
CREATE TABLE IF NOT EXISTS plans (
    id SERIAL PRIMARY KEY,
    plan_name VARCHAR(100),
    investment_amount NUMERIC,
    daily_income NUMERIC,
    duration INTEGER,
    status VARCHAR(20) DEFAULT 'Active'
);



-- USER ACTIVE PLANS
CREATE TABLE IF NOT EXISTS user_plans (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    plan_id INTEGER REFERENCES plans(id) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'Active',
    last_claim_time TIMESTAMP
);



-- DEPOSITS
CREATE TABLE IF NOT EXISTS deposits (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    amount NUMERIC,
    phone VARCHAR(20),
    payment_reference VARCHAR(100),
    payment_method VARCHAR(50),
    status VARCHAR(20) DEFAULT 'Pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);



-- WITHDRAWALS
CREATE TABLE IF NOT EXISTS withdrawals (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    amount NUMERIC,
    account_id INTEGER,
    withdrawal_fee NUMERIC,
    status VARCHAR(20) DEFAULT 'Pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);



-- TRANSACTIONS
CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    transaction_type VARCHAR(50),
    amount NUMERIC,
    description TEXT,
    status VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);



-- PAYMENT BIND ACCOUNTS
CREATE TABLE IF NOT EXISTS bind_accounts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    account_name VARCHAR(100),
    phone_number VARCHAR(20),
    network VARCHAR(50)
);



-- REFERRALS
CREATE TABLE IF NOT EXISTS referrals (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    referred_user_id INTEGER,
    level INTEGER
);



-- DAILY CLAIM HISTORY
CREATE TABLE IF NOT EXISTS claim_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    plan_id INTEGER,
    amount NUMERIC,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);



-- SUPPORT MESSAGES
CREATE TABLE IF NOT EXISTS support_messages (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);



-- ADMIN TABLE
CREATE TABLE IF NOT EXISTS admins (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE,
    password TEXT NOT NULL
);



-- DEFAULT PLANS

INSERT INTO plans
(plan_name, investment_amount, daily_income, duration)
VALUES

('Plan 1',50,8,100),
('Plan 2',100,20,100),
('Plan 3',200,40,100),
('Plan 4',300,65,100),
('Plan 5',500,100,100),
('Plan 6',600,200,100),
('Plan 7',1000,360,100)

ON CONFLICT DO NOTHING;
