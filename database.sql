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


CREATE TABLE IF NOT EXISTS accounts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    deposit_account DECIMAL(10,2) DEFAULT 0,
    withdraw_account DECIMAL(10,2) DEFAULT 0,
    income_account DECIMAL(10,2) DEFAULT 0,
    referral_account DECIMAL(10,2) DEFAULT 0
);


CREATE TABLE IF NOT EXISTS plans (
    id SERIAL PRIMARY KEY,
    plan_name VARCHAR(100),
    investment_amount DECIMAL(10,2),
    daily_income DECIMAL(10,2),
    duration INTEGER,
    status VARCHAR(20) DEFAULT 'Active'
);


CREATE TABLE IF NOT EXISTS user_plans (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    plan_id INTEGER REFERENCES plans(id) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'Active',
    last_claim_time TIMESTAMP
);


CREATE TABLE IF NOT EXISTS referrals (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    referred_user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    level INTEGER DEFAULT 1
);


CREATE TABLE IF NOT EXISTS bind_accounts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    account_name VARCHAR(100),
    phone_number VARCHAR(20),
    network VARCHAR(50)
);


CREATE TABLE IF NOT EXISTS deposits (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    amount DECIMAL(10,2),
    phone VARCHAR(20),
    payment_reference VARCHAR(100),
    payment_method VARCHAR(50),
    status VARCHAR(20) DEFAULT 'Pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS withdrawals (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    amount DECIMAL(10,2),
    account_id INTEGER,
    withdrawal_fee DECIMAL(10,2),
    status VARCHAR(20) DEFAULT 'Pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    transaction_type VARCHAR(50),
    amount DECIMAL(10,2),
    description TEXT,
    status VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS claim_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    plan_id INTEGER REFERENCES plans(id),
    amount DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS support_messages (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS admins (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE,
    password TEXT NOT NULL
);



-- INSERT YOUR CURRENT PLANS

INSERT INTO plans
(plan_name, investment_amount, daily_income, duration)
VALUES
('Plan 1',50,8,100),
('Plan 2',100,20,100),
('Plan 3',200,40,100),
('Plan 4',300,65,100),
('Plan 5',500,100,100),
('Plan 6',600,200,100),
('Plan 7',1000,360,100);
