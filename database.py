import os
import psycopg2
from psycopg2.extras import RealDictCursor


def get_db():
    return psycopg2.connect(
        os.environ.get("DATABASE_URL"),
        cursor_factory=RealDictCursor
    )


def create_tables():

    db = get_db()
    cursor = db.cursor()

    # =========================
    # USERS
    # =========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            fullname VARCHAR(150) NOT NULL,
            username VARCHAR(100) UNIQUE NOT NULL,
            phone VARCHAR(30) UNIQUE NOT NULL,
            login_password TEXT NOT NULL,
            withdrawal_password TEXT NOT NULL,
            referral_code VARCHAR(50) UNIQUE NOT NULL,
            referred_by VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


    # =========================
    # ACCOUNTS
    # =========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id SERIAL PRIMARY KEY,
            user_id INTEGER UNIQUE NOT NULL,
            deposit_account NUMERIC(12,2) DEFAULT 0,
            withdraw_account NUMERIC(12,2) DEFAULT 0,
            income_account NUMERIC(12,2) DEFAULT 0,
            referral_account NUMERIC(12,2) DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id)
                ON DELETE CASCADE
        )
    """)


    # =========================
    # PLANS
    # =========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            id SERIAL PRIMARY KEY,
            plan_name VARCHAR(100) NOT NULL,
            investment_amount NUMERIC(12,2) NOT NULL,
            daily_income NUMERIC(12,2) NOT NULL,
            duration INTEGER NOT NULL,
            status VARCHAR(30) DEFAULT 'Active'
        )
    """)


    # =========================
    # USER PLANS
    # =========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_plans (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            plan_id INTEGER NOT NULL,
            status VARCHAR(30) DEFAULT 'Active',
            last_claim_time TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
                ON DELETE CASCADE,
            FOREIGN KEY (plan_id) REFERENCES plans(id)
                ON DELETE CASCADE
        )
    """)


    # =========================
    # DEPOSITS
    # =========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS deposits (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            amount NUMERIC(12,2) NOT NULL,
            phone VARCHAR(30),
            payment_reference VARCHAR(150),
            payment_method VARCHAR(50),
            status VARCHAR(30) DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
                ON DELETE CASCADE
        )
    """)


    # =========================
    # WITHDRAWALS
    # =========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            amount NUMERIC(12,2) NOT NULL,
            account_id INTEGER,
            withdrawal_fee NUMERIC(12,2) DEFAULT 0,
            status VARCHAR(30) DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
                ON DELETE CASCADE
        )
    """)


    # =========================
    # TRANSACTIONS
    # =========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            transaction_type VARCHAR(100) NOT NULL,
            amount NUMERIC(12,2) NOT NULL,
            description TEXT,
            status VARCHAR(30) DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
                ON DELETE CASCADE
        )
    """)


    # =========================
    # CLAIM HISTORY
    # =========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS claim_history (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            plan_id INTEGER NOT NULL,
            amount NUMERIC(12,2) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
                ON DELETE CASCADE,
            FOREIGN KEY (plan_id) REFERENCES plans(id)
                ON DELETE CASCADE
        )
    """)


    # =========================
    # REFERRALS
    # =========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            referred_user_id INTEGER NOT NULL,
            level INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
                ON DELETE CASCADE,
            FOREIGN KEY (referred_user_id) REFERENCES users(id)
                ON DELETE CASCADE
        )
    """)


    # =========================
    # BIND ACCOUNTS
    # =========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bind_accounts (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            account_name VARCHAR(150) NOT NULL,
            phone_number VARCHAR(30) NOT NULL,
            network VARCHAR(50) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
                ON DELETE CASCADE
        )
    """)


    # =========================
    # SUPPORT MESSAGES
    # =========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS support_messages (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
                ON DELETE CASCADE
        )
    """)


    # =========================
    # ADMINS
    # =========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


    # =========================
    # CURRENT DASHBOARD PLANS
    # =========================

    plans = [
        ("Plan 1", 50, 8, 100),
        ("Plan 2", 100, 20, 100),
        ("Plan 3", 200, 40, 100),
        ("Plan 4", 300, 65, 100),
        ("Plan 5", 500, 100, 100),
        ("Plan 6", 600, 200, 100),
        ("Plan 7", 1000, 360, 100),
        ("Plan 8", 2000, 500, 100),
        ("Plan 9", 4000, 800, 100)
    ]

    for plan in plans:

        cursor.execute("""
            SELECT id
            FROM plans
            WHERE plan_name = %s
        """, (plan[0],))

        existing = cursor.fetchone()

        if not existing:

            cursor.execute("""
                INSERT INTO plans
                (
                    plan_name,
                    investment_amount,
                    daily_income,
                    duration,
                    status
                )
                VALUES (%s, %s, %s, %s, 'Active')
            """, plan)


    db.commit()

    cursor.close()
    db.close()
