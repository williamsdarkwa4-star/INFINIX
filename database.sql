-- =====================================
-- TESLA PLATFORM DATABASE
-- CLEAN POSTGRESQL VERSION
-- =====================================


-- USERS TABLE
CREATE TABLE users (

    id SERIAL PRIMARY KEY,

    phone VARCHAR(20) UNIQUE NOT NULL,

    password TEXT NOT NULL,

    withdraw_password TEXT NOT NULL,

    balance NUMERIC(12,2) DEFAULT 10.00,

    income NUMERIC(12,2) DEFAULT 0.00,

    referral_code VARCHAR(30) UNIQUE NOT NULL,

    invited_by VARCHAR(30),

    account_name VARCHAR(100),

    network VARCHAR(50),

    account_number VARCHAR(50),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

);

ALTER TABLE user_plans
ADD COLUMN IF NOT EXISTS days_completed INTEGER DEFAULT 0;

ALTER TABLE user_plans
ADD COLUMN IF NOT EXISTS total_earned NUMERIC(12,2) DEFAULT 0.00;

ALTER TABLE user_plans
ADD COLUMN IF NOT EXISTS last_claim TIMESTAMP;


UPDATE user_plans
SET days_completed = 0
WHERE days_completed IS NULL;


UPDATE user_plans
SET total_earned = 0
WHERE total_earned IS NULL;


-- Check the columns
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name='user_plans';

-- USER PLANS TABLE
CREATE TABLE user_plans (

    id SERIAL PRIMARY KEY,

    user_id INTEGER NOT NULL,

    plan_name VARCHAR(100) NOT NULL,

    investment NUMERIC(12,2) NOT NULL,

    daily_income NUMERIC(12,2) NOT NULL,

    duration INTEGER DEFAULT 180,

    days_completed INTEGER DEFAULT 0,

    total_earned NUMERIC(12,2) DEFAULT 0.00,

    last_claim TIMESTAMP DEFAULT NULL,

    status VARCHAR(30) DEFAULT 'Active',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT user_plan_fk

    FOREIGN KEY(user_id)

    REFERENCES users(id)

    ON DELETE CASCADE

);



-- DEPOSITS TABLE
CREATE TABLE deposits (

    id SERIAL PRIMARY KEY,

    user_id INTEGER NOT NULL,

    amount NUMERIC(12,2) NOT NULL,

    screenshot TEXT,

    status VARCHAR(30) DEFAULT 'Processing',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(user_id)

    REFERENCES users(id)

    ON DELETE CASCADE

);



-- WITHDRAWALS TABLE
CREATE TABLE withdrawals (

    id SERIAL PRIMARY KEY,

    user_id INTEGER NOT NULL,

    amount NUMERIC(12,2) NOT NULL,

    fee NUMERIC(12,2) DEFAULT 0.00,

    receive_amount NUMERIC(12,2) DEFAULT 0.00,

    status VARCHAR(30) DEFAULT 'Processing',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(user_id)

    REFERENCES users(id)

    ON DELETE CASCADE

);



-- ADMINS TABLE
CREATE TABLE admins (

    id SERIAL PRIMARY KEY,

    username VARCHAR(50) UNIQUE NOT NULL,

    password TEXT NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

);



-- ADMIN ACCOUNT
INSERT INTO admins
(username,password)
VALUES
(
'Williams12',
'CHANGE_TO_HASHED_PASSWORD'
);



-- INDEXES
CREATE INDEX users_phone_idx
ON users(phone);


CREATE INDEX users_referral_idx
ON users(referral_code);


CREATE INDEX plans_user_idx
ON user_plans(user_id);


CREATE INDEX deposits_user_idx
ON deposits(user_id);


CREATE INDEX withdrawals_user_idx
ON withdrawals(user_id);
