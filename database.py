import os
import psycopg2
from psycopg2.extras import RealDictCursor


class Database:

    def __init__(self):

        self.conn = psycopg2.connect(
            os.environ.get("DATABASE_URL"),
            cursor_factory=RealDictCursor
        )


    def execute(self, query, params=()):

        cur = self.conn.cursor()

        query = query.replace("?", "%s")

        cur.execute(query, params)

        self.conn.commit()

        return cur



    def fetchone(self, query, params=()):

        cur = self.execute(query, params)

        return cur.fetchone()



    def fetchall(self, query, params=()):

        cur = self.execute(query, params)

        return cur.fetchall()



    def commit(self):

        self.conn.commit()



def get_db():

    return Database()



def create_tables():

    db = get_db()


    db.execute("""

    CREATE TABLE IF NOT EXISTS users(

        id SERIAL PRIMARY KEY,

        fullname TEXT,

        username TEXT UNIQUE,

        phone TEXT UNIQUE,

        login_password TEXT,

        withdrawal_password TEXT,

        referral_code TEXT UNIQUE,

        referred_by TEXT,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

    )

    """)



    db.execute("""

    CREATE TABLE IF NOT EXISTS accounts(

        id SERIAL PRIMARY KEY,

        user_id INTEGER REFERENCES users(id),

        deposit_account NUMERIC DEFAULT 0,

        income_account NUMERIC DEFAULT 0,

        withdraw_account NUMERIC DEFAULT 0,

        referral_account NUMERIC DEFAULT 0

    )

    """)



    db.execute("""

    CREATE TABLE IF NOT EXISTS plans(

        id SERIAL PRIMARY KEY,

        plan_name TEXT,

        investment_amount NUMERIC,

        daily_income NUMERIC,

        duration INTEGER,

        status TEXT DEFAULT 'Active'

    )

    """)



    db.execute("""

    CREATE TABLE IF NOT EXISTS user_plans(

        id SERIAL PRIMARY KEY,

        user_id INTEGER REFERENCES users(id),

        plan_id INTEGER REFERENCES plans(id),

        status TEXT,

        last_claim_time TIMESTAMP

    )

    """)



    db.execute("""

    CREATE TABLE IF NOT EXISTS bind_accounts(

        id SERIAL PRIMARY KEY,

        user_id INTEGER REFERENCES users(id),

        account_name TEXT,

        phone_number TEXT,

        network TEXT

    )

    """)



    db.execute("""

    CREATE TABLE IF NOT EXISTS deposits(

        id SERIAL PRIMARY KEY,

        user_id INTEGER REFERENCES users(id),

        amount NUMERIC,

        phone TEXT,

        payment_reference TEXT,

        payment_method TEXT,

        status TEXT

    )

    """)



    db.execute("""

    CREATE TABLE IF NOT EXISTS withdrawals(

        id SERIAL PRIMARY KEY,

        user_id INTEGER REFERENCES users(id),

        amount NUMERIC,

        account_id INTEGER,

        withdrawal_fee NUMERIC,

        status TEXT

    )

    """)



    db.execute("""

    CREATE TABLE IF NOT EXISTS transactions(

        id SERIAL PRIMARY KEY,

        user_id INTEGER REFERENCES users(id),

        transaction_type TEXT,

        amount NUMERIC,

        description TEXT,

        status TEXT,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

    )

    """)



    db.execute("""

    CREATE TABLE IF NOT EXISTS claim_history(

        id SERIAL PRIMARY KEY,

        user_id INTEGER,

        plan_id INTEGER,

        amount NUMERIC,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

    )

    """)



    db.execute("""

    CREATE TABLE IF NOT EXISTS support_messages(

        id SERIAL PRIMARY KEY,

        user_id INTEGER,

        message TEXT,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

    )

    """)



    db.execute("""

    CREATE TABLE IF NOT EXISTS admins(

        id SERIAL PRIMARY KEY,

        username TEXT UNIQUE,

        password TEXT

    )

    """)



    db.commit()
