import sqlite3


DATABASE = "zenith.db"



def get_db():

    conn = sqlite3.connect(DATABASE)

    conn.row_factory = sqlite3.Row

    return conn





def create_tables():

    conn = get_db()

    cursor = conn.cursor()



    # USERS

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        fullname TEXT NOT NULL,

        username TEXT UNIQUE NOT NULL,

        phone TEXT UNIQUE NOT NULL,

        login_password TEXT NOT NULL,

        withdrawal_password TEXT NOT NULL,

        referral_code TEXT UNIQUE,

        referred_by TEXT,

        status TEXT DEFAULT 'Active',

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

    )
    """)





    # USER ACCOUNTS

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS accounts (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        user_id INTEGER UNIQUE,

        deposit_account REAL DEFAULT 0,

        withdrawal_account REAL DEFAULT 0,

        income_account REAL DEFAULT 0,

        referral_account REAL DEFAULT 0,

        FOREIGN KEY(user_id) REFERENCES users(id)

    )
    """)





    # BIND WITHDRAWAL ACCOUNTS

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bind_accounts (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        user_id INTEGER,

        account_name TEXT,

        phone_number TEXT,

        network TEXT,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY(user_id) REFERENCES users(id)

    )
    """)





    # INVESTMENT PLANS

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS plans (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        plan_name TEXT,

        investment_amount REAL,

        daily_income REAL,

        duration INTEGER,

        status TEXT DEFAULT 'Active'

    )
    """)





    # USER ACTIVE PLANS

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_plans (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        user_id INTEGER,

        plan_id INTEGER,

        start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        end_date TIMESTAMP,

        last_claim_time TIMESTAMP,

        status TEXT DEFAULT 'Active',

        FOREIGN KEY(user_id) REFERENCES users(id),

        FOREIGN KEY(plan_id) REFERENCES plans(id)

    )
    """)





    # DEPOSITS

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS deposits (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        user_id INTEGER,

        amount REAL,

        phone TEXT,

        payment_reference TEXT,

        payment_method TEXT DEFAULT 'Paystack',

        status TEXT DEFAULT 'Pending',

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY(user_id) REFERENCES users(id)

    )
    """)





    # WITHDRAWALS

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS withdrawals (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        user_id INTEGER,

        amount REAL,

        account_id INTEGER,

        withdrawal_fee REAL DEFAULT 0,

        status TEXT DEFAULT 'Pending',

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY(user_id) REFERENCES users(id),

        FOREIGN KEY(account_id) REFERENCES bind_accounts(id)

    )
    """)





    # ALL TRANSACTIONS

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        user_id INTEGER,

        transaction_type TEXT,

        amount REAL,

        description TEXT,

        status TEXT,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY(user_id) REFERENCES users(id)

    )
    """)





    # REFERRAL SYSTEM

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS referrals (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        user_id INTEGER,

        referred_user_id INTEGER,

        level INTEGER,

        commission REAL DEFAULT 0,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

    )
    """)





    # DAILY INCOME CLAIM HISTORY

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS claim_history (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        user_id INTEGER,

        plan_id INTEGER,

        amount REAL,

        claim_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY(user_id) REFERENCES users(id)

    )
    """)





    # ADMIN ACCOUNTS

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admins (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        username TEXT UNIQUE,

        password TEXT NOT NULL

    )
    """)





    # ADMIN ACTION LOG

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admin_actions (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        admin_id INTEGER,

        action TEXT,

        target_user INTEGER,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

    )
    """)





    # SUPPORT

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS support_messages (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        user_id INTEGER,

        message TEXT,

        status TEXT DEFAULT 'Open',

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

    )
    """)





    # PLATFORM SETTINGS

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        setting_name TEXT UNIQUE,

        setting_value TEXT

    )
    """)





    conn.commit()

    conn.close()






if __name__ == "__main__":

    create_tables()

    print("Zenith Capital database created successfully!")
