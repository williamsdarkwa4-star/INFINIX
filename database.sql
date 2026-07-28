-- ==================================
-- TESLA DEMO PLATFORM DATABASE
-- PostgreSQL / Render
-- ==================================


-- USERS TABLE

CREATE TABLE IF NOT EXISTS users (

    id SERIAL PRIMARY KEY,

    phone VARCHAR(20) UNIQUE NOT NULL,

    password TEXT NOT NULL,

    withdraw_password TEXT,

    invite_code VARCHAR(50),

    balance NUMERIC(12,2) DEFAULT 10.00,

    income NUMERIC(12,2) DEFAULT 0.00

    account_name VARCHAR(100),

    network VARCHAR(50),

    account_number VARCHAR(30),


    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

);





-- ADMINS TABLE

CREATE TABLE IF NOT EXISTS admins (

    id SERIAL PRIMARY KEY,

    username VARCHAR(50) UNIQUE NOT NULL,

    password TEXT NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

);





-- DEPOSITS TABLE

CREATE TABLE IF NOT EXISTS deposits (

    id SERIAL PRIMARY KEY,

    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,

    amount NUMERIC(12,2) NOT NULL,

    screenshot TEXT,

    status VARCHAR(30) DEFAULT 'Processing',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

);






-- WITHDRAWALS TABLE

CREATE TABLE IF NOT EXISTS withdrawals (

    id SERIAL PRIMARY KEY,


    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,


    amount NUMERIC(12,2) NOT NULL,


    fee NUMERIC(12,2) DEFAULT 0,


    receive_amount NUMERIC(12,2) DEFAULT 0,


    status VARCHAR(30) DEFAULT 'Processing',


    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

);







-- USER PURCHASED PLANS TABLE

CREATE TABLE IF NOT EXISTS user_plans (

    id SERIAL PRIMARY KEY,


    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,


    plan_name VARCHAR(100),


    investment NUMERIC(12,2),


    daily_income NUMERIC(12,2),


    duration INTEGER,


    status VARCHAR(30) DEFAULT 'Active',


    start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP


);







-- TESLA PLANS TABLE

CREATE TABLE IF NOT EXISTS plans (

    id SERIAL PRIMARY KEY,


    name VARCHAR(100),


    investment NUMERIC(12,2),


    daily_income NUMERIC(12,2),


    duration INTEGER,


    image TEXT


);







-- DEFAULT ADMIN ACCOUNT
-- Password is a placeholder hash.
-- Change it after creating your own admin.


INSERT INTO admins
(username,password)

VALUES

(
'admin',
'CHANGE_THIS_PASSWORD_HASH'
)

ON CONFLICT(username) DO NOTHING;







-- TESLA VIP PLANS

INSERT INTO plans
(name,investment,daily_income,duration,image)

VALUES


(
'TESLA VIP 1',
100,
20,
100,
'tesla1.jpg'
),


(
'TESLA VIP 2',
300,
40,
100,
'tesla2.jpg'
),


(
'TESLA VIP 3',
500,
60,
100,
'tesla3.jpg'
),


(
'TESLA VIP 4',
700,
80,
100,
'tesla4.jpg'
),


(
'TESLA VIP 5',
850,
166,
100,
'tesla5.jpg'
),


(
'TESLA VIP 6',
1500,
280,
100,
'tesla6.jpg'
);
