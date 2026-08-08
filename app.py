from flask import Flask, render_template, request, redirect, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash

import os
import secrets
import psycopg2
from psycopg2.extras import RealDictCursor


# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-key-in-render"
)


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_connection():

    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured.")

    return psycopg2.connect(
        database_url,
        cursor_factory=RealDictCursor
    )


# =========================================================
# DATABASE TABLES
# =========================================================

def create_tables():

    conn = get_connection()
    cursor = conn.cursor()

    try:

        # USERS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                fullname VARCHAR(100) NOT NULL,
                username VARCHAR(50) UNIQUE NOT NULL,
                phone VARCHAR(20) UNIQUE NOT NULL,
                login_password TEXT NOT NULL,
                withdrawal_password TEXT NOT NULL,
                referral_code VARCHAR(20) UNIQUE NOT NULL,
                referred_by VARCHAR(20),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ACCOUNTS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE
                    UNIQUE,

                deposit_account NUMERIC(12,2) DEFAULT 0,
                income_account NUMERIC(12,2) DEFAULT 0,
                referral_account NUMERIC(12,2) DEFAULT 0
            )
        """)

        # PLANS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS plans (
                id SERIAL PRIMARY KEY,

                plan_name VARCHAR(100) NOT NULL,

                investment_amount NUMERIC(12,2) NOT NULL,

                daily_income NUMERIC(12,2) NOT NULL,

                duration INTEGER NOT NULL,

                status VARCHAR(20) DEFAULT 'Active'
            )
        """)

        # USER PLANS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_plans (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                plan_id INTEGER
                    REFERENCES plans(id)
                    ON DELETE CASCADE,

                status VARCHAR(20) DEFAULT 'Active',

                purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # TRANSACTIONS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                transaction_type VARCHAR(50),

                amount NUMERIC(12,2),

                description TEXT,

                status VARCHAR(30),

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # BIND ACCOUNTS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bind_accounts (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                account_name VARCHAR(100) NOT NULL,

                phone_number VARCHAR(20) NOT NULL,

                network VARCHAR(50) NOT NULL,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # REFERRALS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                referred_user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                level INTEGER DEFAULT 1,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # DEFAULT PLANS
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM plans
        """)

        result = cursor.fetchone()

        if result["total"] == 0:

            cursor.execute("""
                INSERT INTO plans
                (
                    plan_name,
                    investment_amount,
                    daily_income,
                    duration,
                    status
                )
                VALUES
                    ('Plan 1', 50, 8, 100, 'Active'),
                    ('Plan 2', 100, 20, 100, 'Active'),
                    ('Plan 3', 200, 40, 100, 'Active'),
                    ('Plan 4', 300, 65, 100, 'Active'),
                    ('Plan 5', 500, 100, 100, 'Active'),
                    ('Plan 6', 600, 200, 100, 'Active'),
                    ('Plan 7', 1000, 360, 100, 'Active')
            """)

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        cursor.close()
        conn.close()


# Create tables when application starts
create_tables()


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    if "user_id" in session:
        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


# =========================================================
# REGISTER
# =========================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    invite_code = request.args.get(
        "ref",
        ""
    ).strip().upper()

    if request.method == "POST":

        fullname = request.form.get(
            "fullname",
            ""
        ).strip()

        username = request.form.get(
            "username",
            ""
        ).strip()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        withdrawal_password = request.form.get(
            "withdrawal_password",
            ""
        )

        referred_by = request.form.get(
            "referred_by",
            ""
        ).strip().upper()

        # Validation
        if not fullname:
            return "Please enter your full name."

        if not username:
            return "Please enter your username."

        if not phone:
            return "Please enter your phone number."

        if not password:
            return "Please enter your login password."

        if not withdrawal_password:
            return "Please enter your withdrawal password."

        if len(password) < 6:
            return "Login password must be at least 6 characters."

        if len(withdrawal_password) < 4:
            return "Withdrawal password must be at least 4 characters."

        conn = get_connection()
        cursor = conn.cursor()

        try:

            # Check username
            cursor.execute("""
                SELECT id
                FROM users
                WHERE username = %s
            """, (username,))

            if cursor.fetchone():
                return "Username already exists."

            # Check phone
            cursor.execute("""
                SELECT id
                FROM users
                WHERE phone = %s
            """, (phone,))

            if cursor.fetchone():
                return "Phone number already exists."

            # Generate unique referral code
            while True:

                referral_code = secrets.token_hex(
                    4
                ).upper()

                cursor.execute("""
                    SELECT id
                    FROM users
                    WHERE referral_code = %s
                """, (referral_code,))

                if not cursor.fetchone():
                    break

            # Validate referral
            valid_referral = None
            inviter_id = None

            if referred_by:

                cursor.execute("""
                    SELECT id, referral_code
                    FROM users
                    WHERE referral_code = %s
                """, (referred_by,))

                inviter = cursor.fetchone()

                if inviter:

                    valid_referral = inviter["referral_code"]
                    inviter_id = inviter["id"]

            # Hash passwords
            login_hash = generate_password_hash(password)

            withdrawal_hash = generate_password_hash(
                withdrawal_password
            )

            # Create user
            cursor.execute("""
                INSERT INTO users
                (
                    fullname,
                    username,
                    phone,
                    login_password,
                    withdrawal_password,
                    referral_code,
                    referred_by
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                RETURNING id
            """, (
                fullname,
                username,
                phone,
                login_hash,
                withdrawal_hash,
                referral_code,
                valid_referral
            ))

            new_user = cursor.fetchone()

            user_id = new_user["id"]

            # Create wallet
            cursor.execute("""
                INSERT INTO accounts
                (
                    user_id,
                    deposit_account,
                    income_account,
                    referral_account
                )
                VALUES
                (
                    %s,
                    0,
                    0,
                    0
                )
            """, (user_id,))

            # Referral record
            if inviter_id:

                cursor.execute("""
                    INSERT INTO referrals
                    (
                        user_id,
                        referred_user_id,
                        level
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        1
                    )
                """, (
                    inviter_id,
                    user_id
                ))

            conn.commit()

            return redirect(url_for("login"))

        except psycopg2.Error:

            conn.rollback()

            return "Registration could not be completed."

        finally:

            cursor.close()
            conn.close()

    return render_template(
        "register.html",
        invite_code=invite_code
    )


# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        if not phone or not password:
            return "Please enter your phone number and password."

        conn = get_connection()
        cursor = conn.cursor()

        try:

            cursor.execute("""
                SELECT *
                FROM users
                WHERE phone = %s
                LIMIT 1
            """, (phone,))

            user = cursor.fetchone()

            if not user:
                return "Invalid phone number or password."

            if not check_password_hash(
                user["login_password"],
                password
            ):
                return "Invalid phone number or password."

            session.clear()

            session["user_id"] = user["id"]

            return redirect(
                url_for("dashboard")
            )

        finally:

            cursor.close()
            conn.close()

    return render_template("login.html")


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    conn = get_connection()
    cursor = conn.cursor()

    try:

        # User
        cursor.execute("""
            SELECT
                id,
                fullname,
                username,
                phone,
                referral_code,
                referred_by,
                created_at
            FROM users
            WHERE id = %s
        """, (user_id,))

        user = cursor.fetchone()

        if not user:

            session.clear()

            return redirect(url_for("login"))

        # Account
        cursor.execute("""
            SELECT *
            FROM accounts
            WHERE user_id = %s
        """, (user_id,))

        account = cursor.fetchone()

        # Plans
        cursor.execute("""
            SELECT *
            FROM plans
            WHERE status = 'Active'
            ORDER BY id ASC
        """)

        plans = cursor.fetchall()

        # Referral count
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM referrals
            WHERE user_id = %s
        """, (user_id,))

        referral_count = cursor.fetchone()["total"]

        return render_template(
            "dashboard.html",
            user=user,
            account=account,
            plans=plans,
            referral_count=referral_count
        )

    finally:

        cursor.close()
        conn.close()


# =========================================================
# BUY PLAN - STEP 1
# CHECK BALANCE BEFORE CONFIRMATION
# =========================================================

@app.route("/buy_plan/<int:plan_id>")
def buy_plan(plan_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    conn = get_connection()
    cursor = conn.cursor()

    try:

        # Find plan
        cursor.execute("""
            SELECT *
            FROM plans
            WHERE id = %s
            AND status = 'Active'
        """, (plan_id,))

        plan = cursor.fetchone()

        if not plan:
            return "Plan not found."

        # Find account
        cursor.execute("""
            SELECT *
            FROM accounts
            WHERE user_id = %s
        """, (user_id,))

        account = cursor.fetchone()

        if not account:
            return "Account not found."

        # CHECK BALANCE BEFORE SHOWING CONFIRMATION
        if account["deposit_account"] < plan["investment_amount"]:

            return render_template(
                "insufficient_balance.html",
                plan=plan,
                account=account
            )

        # Balance is enough.
        # Do NOT deduct anything yet.

        return render_template(
            "confirm_plan.html",
            plan=plan,
            account=account
        )

    finally:

        cursor.close()
        conn.close()


# =========================================================
# CONFIRM PLAN - STEP 2
# CHECK BALANCE AGAIN BEFORE PURCHASE
# =========================================================

@app.route(
    "/confirm_buy_plan/<int:plan_id>",
    methods=["POST"]
)
def confirm_buy_plan(plan_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    conn = get_connection()
    cursor = conn.cursor()

    try:

        # Find plan
        cursor.execute("""
            SELECT *
            FROM plans
            WHERE id = %s
            AND status = 'Active'
        """, (plan_id,))

        plan = cursor.fetchone()

        if not plan:
            return "Plan is no longer available."

        # Lock the account row during the transaction.
        cursor.execute("""
            SELECT *
            FROM accounts
            WHERE user_id = %s
            FOR UPDATE
        """, (user_id,))

        account = cursor.fetchone()

        if not account:
            return "Account not found."

        # SECOND BALANCE CHECK
        if account["deposit_account"] < plan["investment_amount"]:

            conn.rollback()

            return "Insufficient balance."

        # Deduct plan amount
        cursor.execute("""
            UPDATE accounts
            SET deposit_account =
                deposit_account - %s
            WHERE user_id = %s
        """, (
            plan["investment_amount"],
            user_id
        ))

        # Create active user plan
        cursor.execute("""
            INSERT INTO user_plans
            (
                user_id,
                plan_id,
                status
            )
            VALUES
            (
                %s,
                %s,
                'Active'
            )
        """, (
            user_id,
            plan_id
        ))

        # Transaction record
        cursor.execute("""
            INSERT INTO transactions
            (
                user_id,
                transaction_type,
                amount,
                description,
                status
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s
            )
        """, (
            user_id,
            "Plan Purchase",
            plan["investment_amount"],
            "Purchased " + plan["plan_name"],
            "Successful"
        ))

        conn.commit()

        return redirect(
            url_for("my_plan")
        )

    except Exception:

        conn.rollback()

        return "The plan purchase could not be completed."

    finally:

        cursor.close()
        conn.close()


# =========================================================
# MY PLAN
# =========================================================

@app.route("/my_plan")
def my_plan():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute("""
            SELECT
                user_plans.id,
                user_plans.status,
                user_plans.purchased_at,

                plans.plan_name,
                plans.investment_amount,
                plans.daily_income,
                plans.duration

            FROM user_plans

            JOIN plans
            ON user_plans.plan_id = plans.id

            WHERE user_plans.user_id = %s

            ORDER BY user_plans.id DESC
        """, (
            session["user_id"],
        ))

        user_plans = cursor.fetchall()

        return render_template(
            "my_plan.html",
            user_plans=user_plans
        )

    finally:

        cursor.close()
        conn.close()


# =========================================================
# PROFILE
# =========================================================

@app.route("/profile")
def profile():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute("""
            SELECT
                id,
                fullname,
                username,
                phone,
                referral_code,
                referred_by,
                created_at
            FROM users
            WHERE id = %s
        """, (
            session["user_id"],
        ))

        user = cursor.fetchone()

        cursor.execute("""
            SELECT *
            FROM accounts
            WHERE user_id = %s
        """, (
            session["user_id"],
        ))

        account = cursor.fetchone()

        return render_template(
            "profile.html",
            user=user,
            account=account
        )

    finally:

        cursor.close()
        conn.close()


# =========================================================
# BIND PAYMENT ACCOUNT
# =========================================================

@app.route(
    "/bind_account",
    methods=["GET", "POST"]
)
def bind_account():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor()

    try:

        if request.method == "POST":

            account_name = request.form.get(
                "account_name",
                ""
            ).strip()

            phone_number = request.form.get(
                "phone_number",
                ""
            ).strip()

            network = request.form.get(
                "network",
                ""
            ).strip()

            if not account_name:
                return "Please enter account name."

            if not phone_number:
                return "Please enter phone number."

            if not network:
                return "Please select a network."

            cursor.execute("""
                INSERT INTO bind_accounts
                (
                    user_id,
                    account_name,
                    phone_number,
                    network
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s
                )
            """, (
                session["user_id"],
                account_name,
                phone_number,
                network
            ))

            conn.commit()

            return redirect(
                url_for("bind_account")
            )

        cursor.execute("""
            SELECT *
            FROM bind_accounts
            WHERE user_id = %s
            ORDER BY id DESC
        """, (
            session["user_id"],
        ))

        accounts = cursor.fetchall()

        return render_template(
            "bind_account.html",
            accounts=accounts
        )

    finally:

        cursor.close()
        conn.close()


# =========================================================
# TEAM / REFERRALS
# =========================================================

@app.route("/team")
def team():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute("""
            SELECT referral_code
            FROM users
            WHERE id = %s
        """, (
            session["user_id"],
        ))

        user = cursor.fetchone()

        if not user:
            return redirect(url_for("login"))

        referral_code = user["referral_code"]

        # Level 1
        cursor.execute("""
            SELECT *
            FROM users
            WHERE referred_by = %s
            ORDER BY id DESC
        """, (referral_code,))

        level1 = cursor.fetchall()

        # Level 2
        level2 = []

        for member in level1:

            cursor.execute("""
                SELECT *
                FROM users
                WHERE referred_by = %s
            """, (
                member["referral_code"],
            ))

            level2.extend(
                cursor.fetchall()
            )

        # Level 3
        level3 = []

        for member in level2:

            cursor.execute("""
                SELECT *
                FROM users
                WHERE referred_by = %s
            """, (
                member["referral_code"],
            ))

            level3.extend(
                cursor.fetchall()
            )

        return render_template(
            "team.html",
            level1=level1,
            level2=level2,
            level3=level3,
            level1_count=len(level1),
            level2_count=len(level2),
            level3_count=len(level3)
        )

    finally:

        cursor.close()
        conn.close()


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        ),
        debug=False
    )
