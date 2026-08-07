import os
import psycopg2
from psycopg2.extras import RealDictCursor


class Database:

    def __init__(self):
        self.conn = psycopg2.connect(
            os.environ.get("DATABASE_URL")
        )


    def execute(self, query, params=()):

        cursor = self.conn.cursor(
            cursor_factory=RealDictCursor
        )

        cursor.execute(query, params)

        self.conn.commit()

        return cursor


    def execute_one(self, query, params=()):

        cursor = self.conn.cursor(
            cursor_factory=RealDictCursor
        )

        cursor.execute(query, params)

        result = cursor.fetchone()

        cursor.close()

        return result


    def execute_all(self, query, params=()):

        cursor = self.conn.cursor(
            cursor_factory=RealDictCursor
        )

        cursor.execute(query, params)

        result = cursor.fetchall()

        cursor.close()

        return result


    def commit(self):
        self.conn.commit()



def get_db():
    return Database()



def create_tables():

    db = get_db()

    cursor = db.conn.cursor()


    cursor.execute("""
    
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

    """)


    cursor.execute("""
    
    CREATE TABLE IF NOT EXISTS accounts (

        id SERIAL PRIMARY KEY,

        user_id INTEGER REFERENCES users(id)
        ON DELETE CASCADE,

        deposit_account NUMERIC DEFAULT 0,

        income_account NUMERIC DEFAULT 0,

        referral_account NUMERIC DEFAULT 0

    );

    """)


    cursor.execute("""
    
    CREATE TABLE IF NOT EXISTS bind_accounts (

        id SERIAL PRIMARY KEY,

        user_id INTEGER REFERENCES users(id)
        ON DELETE CASCADE,

        account_name VARCHAR(100),

        phone_number VARCHAR(20),

        network VARCHAR(50)

    );

    """)


    db.conn.commit()

    cursor.close()
