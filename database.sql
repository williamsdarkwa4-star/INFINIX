-- =====================================
-- TESLA PLATFORM DATABASE MIGRATION
-- PostgreSQL SAFE VERSION
-- =====================================


CREATE TABLE IF NOT EXISTS users (

    id SERIAL PRIMARY KEY,

    phone VARCHAR(20) UNIQUE NOT NULL,

    password TEXT NOT NULL,

    withdraw_password TEXT NOT NULL,

    balance NUMERIC(12,2) DEFAULT 10.00,

    income NUMERIC(12,2) DEFAULT 0.00,

    referral_code VARCHAR(20) UNIQUE NOT NULL,

    invited_by VARCHAR(20),

    account_name VARCHAR(100),

    network VARCHAR(50),

    account_number VARCHAR(30),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);



CREATE TABLE IF NOT EXISTS user_plans (

    id SERIAL PRIMARY KEY,

    user_id INTEGER NOT NULL,

    plan_name VARCHAR(100) NOT NULL,

    investment NUMERIC(12,2) NOT NULL,

    daily_income NUMERIC(12,2) NOT NULL,

    duration INTEGER DEFAULT 100,

    days_completed INTEGER DEFAULT 0,

    total_earned NUMERIC(12,2) DEFAULT 0.00,

    last_claim TIMESTAMP,

    status VARCHAR(30) DEFAULT 'Active',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(user_id)
    REFERENCES users(id)
    ON DELETE CASCADE
);



-- FIX OLD USER_PLANS TABLES

ALTER TABLE user_plans
ADD COLUMN IF NOT EXISTS days_completed INTEGER DEFAULT 0;

ALTER TABLE user_plans
ADD COLUMN IF NOT EXISTS total_earned NUMERIC(12,2) DEFAULT 0.00;

ALTER TABLE user_plans
ADD COLUMN IF NOT EXISTS last_claim TIMESTAMP;



CREATE TABLE IF NOT EXISTS deposits (

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



CREATE TABLE IF NOT EXISTS withdrawals (

    id SERIAL PRIMARY KEY,

    user_id INTEGER NOT NULL,

    amount NUMERIC(12,2) NOT NULL,

    fee NUMERIC(12,2) DEFAULT 0,

    receive_amount NUMERIC(12,2) DEFAULT 0,

    status VARCHAR(30) DEFAULT 'Processing',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(user_id)
    REFERENCES users(id)
    ON DELETE CASCADE
);



CREATE TABLE IF NOT EXISTS admins (

    id SERIAL PRIMARY KEY,

    username VARCHAR(50) UNIQUE NOT NULL,

    password TEXT NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);



-- FIX EXISTING EMPTY VALUES

UPDATE user_plans
SET days_completed = 0
WHERE days_completed IS NULL;


UPDATE user_plans
SET total_earned = 0
WHERE total_earned IS NULL;



-- INDEXES

CREATE INDEX IF NOT EXISTS users_phone_index
ON users(phone);


CREATE INDEX IF NOT EXISTS users_referral_index
ON users(referral_code);


CREATE INDEX IF NOT EXISTS deposits_status_index
ON deposits(status);


CREATE INDEX IF NOT EXISTS withdrawals_status_index
ON withdrawals(status);


CREATE INDEX IF NOT EXISTS plans_user_index
ON user_plans(user_id);




-- =====================================
-- TESLA INVESTMENT PLATFORM DATABASE
-- PostgreSQL
-- =====================================


-- USERS TABLE
-- =====================================

CREATE TABLE users (

    id SERIAL PRIMARY KEY,

    phone VARCHAR(20) UNIQUE NOT NULL,

    password TEXT NOT NULL,

    withdraw_password TEXT NOT NULL,


    balance NUMERIC(12,2)
    DEFAULT 10.00,


    income NUMERIC(12,2)
    DEFAULT 0.00,


    referral_code VARCHAR(20)
    UNIQUE NOT NULL,


    invited_by VARCHAR(20),


    account_name VARCHAR(100),

    network VARCHAR(50),

    account_number VARCHAR(30),


    created_at TIMESTAMP
    DEFAULT CURRENT_TIMESTAMP

);



-- USER PLANS TABLE
-- =====================================

CREATE TABLE user_plans (

    id SERIAL PRIMARY KEY,


    user_id INTEGER NOT NULL,


    plan_name VARCHAR(100) NOT NULL,


    investment NUMERIC(12,2)
    NOT NULL,


    daily_income NUMERIC(12,2)
    NOT NULL,


    duration INTEGER
    DEFAULT 100,


    days_completed INTEGER
    DEFAULT 0,


    total_earned NUMERIC(12,2)
    DEFAULT 0.00,


    last_claim TIMESTAMP,


    status VARCHAR(30)
    DEFAULT 'Active',


    created_at TIMESTAMP
    DEFAULT CURRENT_TIMESTAMP,


    CONSTRAINT fk_user_plan

    FOREIGN KEY(user_id)

    REFERENCES users(id)

    ON DELETE CASCADE

);



-- DEPOSITS TABLE
-- =====================================

CREATE TABLE deposits (

    id SERIAL PRIMARY KEY,


    user_id INTEGER NOT NULL,


    amount NUMERIC(12,2)
    NOT NULL,


    screenshot TEXT,


    status VARCHAR(30)
    DEFAULT 'Processing',


    created_at TIMESTAMP
    DEFAULT CURRENT_TIMESTAMP,


    FOREIGN KEY(user_id)

    REFERENCES users(id)

    ON DELETE CASCADE

);

SELECT column_name
FROM information_schema.columns
WHERE table_name = 'user_plans';
ALTER TABLE user_plans 
ADD COLUMN days_completed INTEGER DEFAULT 0;

ALTER TABLE user_plans 
ADD COLUMN total_earned NUMERIC(12,2) DEFAULT 0.00;

ALTER TABLE user_plans 
ADD COLUMN last_claim TIMESTAMP;
-- WITHDRAWALS TABLE
-- =====================================

CREATE TABLE withdrawals (

    id SERIAL PRIMARY KEY,


    user_id INTEGER NOT NULL,


    amount NUMERIC(12,2)
    NOT NULL,


    fee NUMERIC(12,2)
    DEFAULT 0,


    receive_amount NUMERIC(12,2)
    DEFAULT 0,


    status VARCHAR(30)
    DEFAULT 'Processing',


    created_at TIMESTAMP
    DEFAULT CURRENT_TIMESTAMP,


    FOREIGN KEY(user_id)

    REFERENCES users(id)

    ON DELETE CASCADE

);



-- ADMINS TABLE
-- =====================================

CREATE TABLE admins (

    id SERIAL PRIMARY KEY,


    username VARCHAR(50)
    UNIQUE NOT NULL,


    password TEXT NOT NULL,


    created_at TIMESTAMP
    DEFAULT CURRENT_TIMESTAMP

);



-- CREATE FIRST ADMIN
-- Password should be generated using:
-- generate_password_hash()
-- from Python


INSERT INTO admins
(
    username,
    password
)

VALUES
(
    'Williams12',
    'CHANGE_THIS_TO_HASHED_PASSWORD'
);



-- INDEXES FOR SPEED
-- =====================================

CREATE INDEX users_phone_index
ON users(phone);


CREATE INDEX users_referral_index
ON users(referral_code);


CREATE INDEX deposits_status_index
ON deposits(status);


CREATE INDEX withdrawals_status_index
ON withdrawals(status);


CREATE INDEX plans_user_index
ON user_plans(user_id);
