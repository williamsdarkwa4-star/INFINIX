from flask import Flask, render_template, request, redirect, session, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash

import os
import secrets
import psycopg2
from psycopg2.extras import RealDictCursor
from functools import wraps
from datetime import datetime, timedelta


# =========================================================
# FLASK
# =========================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-key"
)


# =========================================================
# SETTINGS
# =========================================================

MIN_DEPOSIT = 45
MIN_WITHDRAWAL = 30
WITHDRAWAL_FEE = 0.16


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_connection():

    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not configured."
        )

    return psycopg2.connect(
        database_url,
        cursor_factory=RealDictCursor
    )


# =========================================================
# DATABASE CREATION
# =========================================================

def create_tables():

    conn = get_connection()
    cursor = conn.cursor()

    try:

        # -------------------------------------------------
        # USERS
        # -------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (

                id SERIAL PRIMARY KEY,

                fullname VARCHAR(100) NOT NULL,

                username VARCHAR(50)
                    UNIQUE NOT NULL,

                phone VARCHAR(20)
                    UNIQUE NOT NULL,

                login_password TEXT NOT NULL,

                withdrawal_password TEXT NOT NULL,

                referral_code VARCHAR(20)
                    UNIQUE NOT NULL,

                referred_by VARCHAR(20),

                created_at
                    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


        # -------------------------------------------------
        # ACCOUNTS
        # -------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accounts (

                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE
                    UNIQUE,

                deposit_account
                    NUMERIC(12,2)
                    DEFAULT 0,

                income_account
                    NUMERIC(12,2)
                    DEFAULT 0,

                referral_account
                    NUMERIC(12,2)
                    DEFAULT 0,

                withdraw_account
                    NUMERIC(12,2)
                    DEFAULT 0
            )
        """)


        # -------------------------------------------------
        # ADD withdraw_account TO OLD DATABASES
        # -------------------------------------------------

        cursor.execute("""
            ALTER TABLE accounts
            ADD COLUMN IF NOT EXISTS
            withdraw_account
            NUMERIC(12,2)
            DEFAULT 0
        """)


        # -------------------------------------------------
        # PLANS
        # -------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS plans (

                id SERIAL PRIMARY KEY,

                plan_name VARCHAR(100)
                    NOT NULL,

                investment_amount
                    NUMERIC(12,2)
                    NOT NULL,

                daily_income
                    NUMERIC(12,2)
                    NOT NULL,

                duration INTEGER
                    NOT NULL,

                status VARCHAR(20)
                    DEFAULT 'Active'
            )
        """)


        # -------------------------------------------------
        # USER PLANS
        # -------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_plans (

                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                plan_id INTEGER
                    REFERENCES plans(id)
                    ON DELETE CASCADE,

                status VARCHAR(20)
                    DEFAULT 'Active',

                purchased_at
                    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                last_claim_time
                    TIMESTAMP
            )
        """)


        # -------------------------------------------------
        # TRANSACTIONS
        # -------------------------------------------------

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

                created_at
                    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


        # -------------------------------------------------
        # BIND ACCOUNTS
        # -------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bind_accounts (

                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                account_name VARCHAR(100)
                    NOT NULL,

                phone_number VARCHAR(20)
                    NOT NULL,

                network VARCHAR(50)
                    NOT NULL,

                created_at
                    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


        # -------------------------------------------------
        # REFERRALS
        # -------------------------------------------------

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

                created_at
                    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


        # -------------------------------------------------
        # DEPOSITS
        # -------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS deposits (

                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                amount NUMERIC(12,2),

                phone VARCHAR(20),

                payment_reference TEXT,

                payment_method VARCHAR(50),

                status VARCHAR(30)
                    DEFAULT 'Pending',

                created_at
                    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


        # -------------------------------------------------
        # WITHDRAWALS
        # -------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (

                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                amount NUMERIC(12,2),

                account_id INTEGER,

                withdrawal_fee
                    NUMERIC(12,2)
                    DEFAULT 0,

                status VARCHAR(30)
                    DEFAULT 'Pending',

                created_at
                    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


        # -------------------------------------------------
        # CLAIM HISTORY
        # -------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS claim_history (

                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                plan_id INTEGER,

                amount NUMERIC(12,2),

                created_at
                    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


        # -------------------------------------------------
        # SUPPORT
        # -------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS support_messages (

                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                message TEXT NOT NULL,

                created_at
                    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


        # -------------------------------------------------
        # ADMINS
        # -------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (

                id SERIAL PRIMARY KEY,

                username VARCHAR(50)
                    UNIQUE NOT NULL,

                password TEXT NOT NULL
            )
        """)


        # -------------------------------------------------
        # DEFAULT PLANS
        # -------------------------------------------------

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


# =========================================================
# START DATABASE
# =========================================================

create_tables()


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    if "user_id" in session:

        return redirect(
            url_for("dashboard")
        )

    return redirect(
        url_for("login")
    )


# =========================================================
# REGISTER
# =========================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
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
            request.form.get(
                "withdraw_password",
                ""
            )
        )

        referred_by = request.form.get(
            "referred_by",
            ""
        ).strip().upper()


        # -------------------------------------------------
        # VALIDATION
        # -------------------------------------------------

        if not fullname:

            flash(
                "Please enter your full name.",
                "error"
            )

            return render_template(
                "register.html",
                invite_code=invite_code
            )


        if not username:

            flash(
                "Please enter your username.",
                "error"
            )

            return render_template(
                "register.html",
                invite_code=invite_code
            )


        if not phone:

            flash(
                "Please enter your phone number.",
                "error"
            )

            return render_template(
                "register.html",
                invite_code=invite_code
            )


        if not password:

            flash(
                "Please enter your login password.",
                "error"
            )

            return render_template(
                "register.html",
                invite_code=invite_code
            )


        if not withdrawal_password:

            flash(
                "Please enter your withdrawal password.",
                "error"
            )

            return render_template(
                "register.html",
                invite_code=invite_code
            )


        if len(password) < 6:

            flash(
                "Login password must be at least 6 characters.",
                "error"
            )

            return render_template(
                "register.html",
                invite_code=invite_code
            )


        if len(withdrawal_password) < 4:

            flash(
                "Withdrawal password must be at least 4 characters.",
                "error"
            )

            return render_template(
                "register.html",
                invite_code=invite_code
            )


        conn = get_connection()
        cursor = conn.cursor()


        try:

            # -------------------------------------------------
            # USERNAME CHECK
            # -------------------------------------------------

            cursor.execute("""
                SELECT id
                FROM users
                WHERE username = %s
            """, (username,))

            if cursor.fetchone():

                flash(
                    "Username already exists.",
                    "error"
                )

                return render_template(
                    "register.html",
                    invite_code=invite_code
                )


            # -------------------------------------------------
            # PHONE CHECK
            # -------------------------------------------------

            cursor.execute("""
                SELECT id
                FROM users
                WHERE phone = %s
            """, (phone,))

            if cursor.fetchone():

                flash(
                    "Phone number already exists.",
                    "error"
                )

                return render_template(
                    "register.html",
                    invite_code=invite_code
                )


            # -------------------------------------------------
            # REFERRAL CODE
            # -------------------------------------------------

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


            # -------------------------------------------------
            # REFERRER
            # -------------------------------------------------

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

                    valid_referral = inviter[
                        "referral_code"
                    ]

                    inviter_id = inviter["id"]


            # -------------------------------------------------
            # PASSWORD HASH
            # -------------------------------------------------

            login_hash = generate_password_hash(
                password
            )

            withdrawal_hash = generate_password_hash(
                withdrawal_password
            )


            # -------------------------------------------------
            # USER
            # -------------------------------------------------

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
                    %s,%s,%s,%s,%s,%s,%s
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


            # -------------------------------------------------
            # ACCOUNT
            # -------------------------------------------------

            cursor.execute("""
                INSERT INTO accounts
                (
                    user_id,
                    deposit_account,
                    income_account,
                    referral_account,
                    withdraw_account
                )
                VALUES
                (
                    %s,0,0,0,0
                )
            """, (user_id,))


            # -------------------------------------------------
            # REFERRAL
            # -------------------------------------------------

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
                        %s,%s,1
                    )
                """, (
                    inviter_id,
                    user_id
                ))


            conn.commit()


            flash(
                "Account created successfully. Please log in.",
                "success"
            )

            return redirect(
                url_for("login")
            )


        except psycopg2.Error:

            conn.rollback()

            flash(
                "Registration could not be completed.",
                "error"
            )

            return render_template(
                "register.html",
                invite_code=invite_code
            )

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

@app.route(
    "/login",
    methods=["GET", "POST"]
)
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

            flash(
                "Please enter your phone number and password.",
                "error"
            )

            return render_template(
                "login.html"
            )


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

                flash(
                    "Invalid phone number or password.",
                    "error"
                )

                return render_template(
                    "login.html"
                )


            if not check_password_hash(
                user["login_password"],
                password
            ):

                flash(
                    "Invalid phone number or password.",
                    "error"
                )

                return render_template(
                    "login.html"
                )


            session.clear()

            session["user_id"] = user["id"]


            return redirect(
                url_for("dashboard")
            )


        finally:

            cursor.close()
            conn.close()


    return render_template(
        "login.html"
    )


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    user_id = session["user_id"]

    conn = get_connection()
    cursor = conn.cursor()


    try:

        # -------------------------------------------------
        # USER
        # -------------------------------------------------

        cursor.execute("""
            SELECT *
            FROM users
            WHERE id = %s
        """, (user_id,))

        user = cursor.fetchone()


        if not user:

            session.clear()

            return redirect(
                url_for("login")
            )


        # -------------------------------------------------
        # ACCOUNT
        # -------------------------------------------------

        cursor.execute("""
            SELECT *
            FROM accounts
            WHERE user_id = %s
        """, (user_id,))

        account = cursor.fetchone()


        # -------------------------------------------------
        # PLANS
        # -------------------------------------------------

        cursor.execute("""
            SELECT *
            FROM plans
            WHERE status = 'Active'
            ORDER BY id ASC
        """)

        plans = cursor.fetchall()


        # -------------------------------------------------
        # REFERRALS
        # -------------------------------------------------

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
            referral_count=referral_count,
            min_deposit=MIN_DEPOSIT,
            min_withdrawal=MIN_WITHDRAWAL
        )


    finally:

        cursor.close()
        conn.close()


# =========================================================
# BUY / INVEST
# STEP 1 — CHECK BALANCE
# =========================================================

@app.route(
    "/buy_plan/<int:plan_id>",
    methods=["GET"]
)
def buy_plan(plan_id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    conn = get_connection()
    cursor = conn.cursor()


    try:

        # -------------------------------------------------
        # PLAN
        # -------------------------------------------------

        cursor.execute("""
            SELECT *
            FROM plans
            WHERE id = %s
            AND status = 'Active'
        """, (plan_id,))

        plan = cursor.fetchone()


        if not plan:

            flash(
                "This plan is not available.",
                "error"
            )

            return redirect(
                url_for("dashboard")
            )


        # -------------------------------------------------
        # ACCOUNT
        # -------------------------------------------------

        cursor.execute("""
            SELECT *
            FROM accounts
            WHERE user_id = %s
        """, (
            session["user_id"],
        ))

        account = cursor.fetchone()


        if not account:

            flash(
                "Account not found.",
                "error"
            )

            return redirect(
                url_for("dashboard")
            )


        # -------------------------------------------------
        # BALANCE CHECK
        # -------------------------------------------------

        if float(account["deposit_account"]) < float(
            plan["investment_amount"]
        ):

            return render_template(
                "insufficient_balance.html",
                plan=plan,
                account=account
            )


        # -------------------------------------------------
        # BALANCE IS ENOUGH
        # SHOW CONFIRMATION
        # -------------------------------------------------

        return render_template(
            "confirm_plan.html",
            plan=plan,
            account=account
        )


    finally:

        cursor.close()
        conn.close()


# =========================================================
# CONFIRM INVESTMENT
# STEP 2 — CHECK AGAIN + DEDUCT
# =========================================================

@app.route(
    "/confirm_buy_plan/<int:plan_id>",
    methods=["POST"]
)
def confirm_buy_plan(plan_id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    conn = get_connection()
    cursor = conn.cursor()


    try:

        # -------------------------------------------------
        # GET PLAN
        # -------------------------------------------------

        cursor.execute("""
            SELECT *
            FROM plans
            WHERE id = %s
            AND status = 'Active'
        """, (plan_id,))

        plan = cursor.fetchone()


        if not plan:

            conn.rollback()

            flash(
                "This plan is no longer available.",
                "error"
            )

            return redirect(
                url_for("dashboard")
            )


        # -------------------------------------------------
        # LOCK ACCOUNT
        # -------------------------------------------------

        cursor.execute("""
            SELECT *
            FROM accounts
            WHERE user_id = %s
            FOR UPDATE
        """, (
            session["user_id"],
        ))

        account = cursor.fetchone()


        if not account:

            conn.rollback()

            flash(
                "Account not found.",
                "error"
            )

            return redirect(
                url_for("dashboard")
            )


        balance = float(
            account["deposit_account"]
        )

        price = float(
            plan["investment_amount"]
        )


        # -------------------------------------------------
        # SECOND BALANCE CHECK
        # -------------------------------------------------

        if balance < price:

            conn.rollback()

            return render_template(
                "insufficient_balance.html",
                plan=plan,
                account=account
            )


        # -------------------------------------------------
        # DEDUCT
        # -------------------------------------------------

        cursor.execute("""
            UPDATE accounts
            SET deposit_account =
                deposit_account - %s
            WHERE user_id = %s
        """, (
            plan["investment_amount"],
            session["user_id"]
        ))


        # -------------------------------------------------
        # USER PLAN
        # -------------------------------------------------

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
            session["user_id"],
            plan_id
        ))


        # -------------------------------------------------
        # TRANSACTION
        # -------------------------------------------------

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
            session["user_id"],
            "Plan Purchase",
            plan["investment_amount"],
            "Purchased " + plan["plan_name"],
            "Successful"
        ))


        conn.commit()


        flash(
            "Plan purchased successfully.",
            "success"
        )


        return redirect(
            url_for("my_plan")
        )


    except Exception:

        conn.rollback()

        flash(
            "The investment could not be completed.",
            "error"
        )

        return redirect(
            url_for("dashboard")
        )


    finally:

        cursor.close()
        conn.close()


# =========================================================
# MY PLAN
# =========================================================

@app.route("/my_plan")
def my_plan():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    conn = get_connection()
    cursor = conn.cursor()


    try:

        cursor.execute("""
            SELECT

                user_plans.id,
                user_plans.status,
                user_plans.purchased_at,
                user_plans.last_claim_time,

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

        return redirect(
            url_for("login")
        )


    conn = get_connection()
    cursor = conn.cursor()


    try:

        cursor.execute("""
            SELECT *
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
# BIND ACCOUNT
# =========================================================

@app.route(
    "/bind_account",
    methods=["GET", "POST"]
)
def bind_account():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


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

                flash(
                    "Please enter account name.",
                    "error"
                )

                return redirect(
                    url_for("bind_account")
                )


            if not phone_number:

                flash(
                    "Please enter phone number.",
                    "error"
                )

                return redirect(
                    url_for("bind_account")
                )


            if not network:

                flash(
                    "Please select a network.",
                    "error"
                )

                return redirect(
                    url_for("bind_account")
                )


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
                    %s,%s,%s,%s
                )
            """, (
                session["user_id"],
                account_name,
                phone_number,
                network
            ))


            conn.commit()


            flash(
                "Payment account saved.",
                "success"
            )


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
# DEPOSIT
# =========================================================

@app.route("/deposit")
def deposit():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    return render_template(
        "deposit.html",
        minimum_deposit=MIN_DEPOSIT
    )


# =========================================================
# DEPOSIT SUCCESS
# =========================================================

@app.route("/deposit_success")
def deposit_success():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    amount_raw = request.args.get(
        "amount",
        ""
    )

    phone = request.args.get(
        "phone",
        ""
    ).strip()

    reference = request.args.get(
        "reference",
        ""
    ).strip()


    try:

        amount = float(amount_raw)

    except (ValueError, TypeError):

        flash(
            "Invalid deposit amount.",
            "error"
        )

        return redirect(
            url_for("deposit")
        )


    if amount < MIN_DEPOSIT:

        flash(
            f"Minimum deposit is GHS {MIN_DEPOSIT}.",
            "error"
        )

        return redirect(
            url_for("deposit")
        )


    conn = get_connection()
    cursor = conn.cursor()


    try:

        cursor.execute("""
            INSERT INTO deposits
            (
                user_id,
                amount,
                phone,
                payment_reference,
                payment_method,
                status
            )
            VALUES
            (
                %s,%s,%s,%s,%s,%s
            )
        """, (
            session["user_id"],
            amount,
            phone,
            reference,
            "Paystack",
            "Pending"
        ))


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
                %s,%s,%s,%s,%s
            )
        """, (
            session["user_id"],
            "Deposit",
            amount,
            "Paystack deposit awaiting approval",
            "Pending"
        ))


        conn.commit()


        flash(
            "Deposit submitted and is awaiting confirmation.",
            "success"
        )


        return redirect(
            url_for("dashboard")
        )


    except Exception:

        conn.rollback()

        flash(
            "Deposit could not be recorded.",
            "error"
        )

        return redirect(
            url_for("deposit")
        )


    finally:

        cursor.close()
        conn.close()


# =========================================================
# WITHDRAW
# =========================================================

@app.route(
    "/withdraw",
    methods=["GET", "POST"]
)
def withdraw():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    conn = get_connection()
    cursor = conn.cursor()


    try:

        if request.method == "POST":

            try:

                amount = float(
                    request.form.get(
                        "amount",
                        "0"
                    )
                )

            except ValueError:

                flash(
                    "Enter a valid amount.",
                    "error"
                )

                return redirect(
                    url_for("withdraw")
                )


            withdrawal_password = request.form.get(
                "withdrawal_password",
                request.form.get(
                    "withdraw_password",
                    ""
                )
            )


            account_id = request.form.get(
                "account_id",
                ""
            )


            if amount < MIN_WITHDRAWAL:

                flash(
                    f"Minimum withdrawal is GHS {MIN_WITHDRAWAL}.",
                    "error"
                )

                return redirect(
                    url_for("withdraw")
                )


            cursor.execute("""
                SELECT *
                FROM users
                WHERE id = %s
            """, (
                session["user_id"],
            ))

            user = cursor.fetchone()


            if not check_password_hash(
                user["withdrawal_password"],
                withdrawal_password
            ):

                flash(
                    "Incorrect withdrawal password.",
                    "error"
                )

                return redirect(
                    url_for("withdraw")
                )


            cursor.execute("""
                SELECT *
                FROM accounts
                WHERE user_id = %s
                FOR UPDATE
            """, (
                session["user_id"],
            ))

            account = cursor.fetchone()


            balance = float(
                account["income_account"]
            )


            if balance < amount:

                flash(
                    "Insufficient income balance.",
                    "error"
                )

                return redirect(
                    url_for("withdraw")
                )


            fee = amount * WITHDRAWAL_FEE

            final_amount = amount - fee


            cursor.execute("""
                UPDATE accounts
                SET income_account =
                    income_account - %s
                WHERE user_id = %s
            """, (
                amount,
                session["user_id"]
            ))


            cursor.execute("""
                INSERT INTO withdrawals
                (
                    user_id,
                    amount,
                    account_id,
                    withdrawal_fee,
                    status
                )
                VALUES
                (
                    %s,%s,%s,%s,%s
                )
            """, (
                session["user_id"],
                final_amount,
                account_id,
                fee,
                "Pending"
            ))


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
                    %s,%s,%s,%s,%s
                )
            """, (
                session["user_id"],
                "Withdrawal",
                final_amount,
                f"Withdrawal request. Fee: GHS {fee:.2f}",
                "Pending"
            ))


            conn.commit()


            flash(
                f"Withdrawal submitted. Fee: GHS {fee:.2f}.",
                "success"
            )


            return redirect(
                url_for("transaction_history")
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
            "withdraw.html",
            accounts=accounts,
            minimum_withdrawal=MIN_WITHDRAWAL,
            withdrawal_fee=WITHDRAWAL_FEE * 100
        )


    finally:

        cursor.close()
        conn.close()


# =========================================================
# TEAM
# =========================================================

@app.route("/team")
def team():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


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

            return redirect(
                url_for("login")
            )


        referral_code = user["referral_code"]


        # LEVEL 1

        cursor.execute("""
            SELECT *
            FROM users
            WHERE referred_by = %s
            ORDER BY id DESC
        """, (
            referral_code,
        ))

        level1 = cursor.fetchall()


        # LEVEL 2

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


        # LEVEL 3

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
# SUPPORT
# =========================================================

@app.route(
    "/support",
    methods=["GET", "POST"]
)
def support():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    conn = get_connection()
    cursor = conn.cursor()


    try:

        if request.method == "POST":

            message = request.form.get(
                "message",
                ""
            ).strip()


            if message:

                cursor.execute("""
                    INSERT INTO support_messages
                    (
                        user_id,
                        message
                    )
                    VALUES
                    (
                        %s,%s
                    )
                """, (
                    session["user_id"],
                    message
                ))


                conn.commit()


            return redirect(
                url_for("support")
            )


        cursor.execute("""
            SELECT *
            FROM support_messages
            WHERE user_id = %s
            ORDER BY id DESC
        """, (
            session["user_id"],
        ))


        messages = cursor.fetchall()


        return render_template(
            "service.html",
            messages=messages
        )


    finally:

        cursor.close()
        conn.close()


# =========================================================
# TRANSACTION HISTORY
# =========================================================

@app.route("/transaction_history")
def transaction_history():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    conn = get_connection()
    cursor = conn.cursor()


    try:

        cursor.execute("""
            SELECT *
            FROM transactions
            WHERE user_id = %s
            ORDER BY id DESC
        """, (
            session["user_id"],
        ))


        transactions = cursor.fetchall()


        return render_template(
            "transaction_history.html",
            transactions=transactions
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
