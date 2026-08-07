import sqlite3
from werkzeug.security import generate_password_hash


DATABASE = "zenith.db"



def get_db():

    conn = sqlite3.connect(DATABASE)

    conn.row_factory = sqlite3.Row

    return conn





def create_tables():

    conn = get_db()

    cursor = conn.cursor()


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



    cursor.execute("""
    CREATE TABLE IF NOT EXISTS accounts (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        user_id INTEGER UNIQUE,

        deposit_account REAL DEFAULT 0,

        income_account REAL DEFAULT 0,

        referral_account REAL DEFAULT 0,

        withdrawal_account REAL DEFAULT 0,

        FOREIGN KEY(user_id) REFERENCES users(id)

    )
    """)



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



    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_plans (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        user_id INTEGER,

        plan_id INTEGER,

        last_claim_time TIMESTAMP,

        status TEXT DEFAULT 'Active',

        FOREIGN KEY(user_id) REFERENCES users(id),

        FOREIGN KEY(plan_id) REFERENCES plans(id)

    )
    """)



    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admins (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        username TEXT UNIQUE,

        password TEXT NOT NULL

    )
    """)



    conn.commit()

    conn.close()
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



    cursor.execute("""
    CREATE TABLE IF NOT EXISTS deposits (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        user_id INTEGER,

        amount REAL,

        phone TEXT,

        payment_reference TEXT,

        payment_method TEXT,

        status TEXT DEFAULT 'Pending',

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY(user_id) REFERENCES users(id)

    )
    """)



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



    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        user_id INTEGER,

        transaction_type TEXT,

        amount REAL,

        description TEXT,

        status TEXT,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

    )
    """)



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



    cursor.execute("""
    CREATE TABLE IF NOT EXISTS claim_history (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        user_id INTEGER,

        plan_id INTEGER,

        amount REAL,

        claim_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP

    )
    """)



    cursor.execute("""
    CREATE TABLE IF NOT EXISTS support_messages (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        user_id INTEGER,

        message TEXT,

        status TEXT DEFAULT 'Open',

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

    )
    """)



    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        setting_name TEXT UNIQUE,

        setting_value TEXT

    )
    """)



    conn.commit()

    conn.close()

def create_plans():

    conn = get_db()

    cursor = conn.cursor()


    plans = [

        ("Plan 1",50,8,30),
        ("Plan 2",100,20,30),
        ("Plan 3",200,40,30),
        ("Plan 4",300,65,30),
        ("Plan 5",500,100,30),
        ("Plan 6",600,200,30),
        ("Plan 7",1000,360,30),
        ("Locked Plan 8",2000,500,30),
        ("Locked Plan 9",4000,800,30)

    ]


    for plan in plans:

        exists = cursor.execute(
        """
        SELECT id FROM plans 
        WHERE plan_name=?
        """,
        (plan[0],)
        ).fetchone()


        if not exists:

            cursor.execute("""
            INSERT INTO plans
            (
            plan_name,
            investment_amount,
            daily_income,
            duration
            )

            VALUES(?,?,?,?)

            """, plan)



    conn.commit()

    conn.close()





def create_admin():

    conn = get_db()

    cursor = conn.cursor()


    username = "Williams"

    password = "Williams12"


    hashed_password = generate_password_hash(password)



    exists = cursor.execute(
    """
    SELECT id FROM admins
    WHERE username=?
    """,
    (username,)
    ).fetchone()



    if not exists:

        cursor.execute("""
        INSERT INTO admins
        (
        username,
        password
        )

        VALUES(?,?)

        """,
        (
        username,
        hashed_password
        ))



    conn.commit()

    conn.close()






if __name__ == "__main__":

    create_tables()

    create_plans()

    create_admin()


    print("Zenith Capital Database Created Successfully")

    print("Admin Login:")

    print("Username: Williams")

    print("Password: Williams12")
