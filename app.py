import os
import secrets
from datetime import datetime, timedelta
from functools import wraps
from decimal import Decimal, InvalidOperation

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import (
Flask,
render_template,
request,
redirect,
session,
flash
)
from werkzeug.security import (
generate_password_hash,
check_password_hash
)

============================================================

APP CONFIGURATION

============================================================

app = Flask(name)

app.secret_key = os.environ.get(
"SECRET_KEY",
"change-this-secret-key"
)

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
raise RuntimeError(
"DATABASE_URL is missing. Add your PostgreSQL DATABASE_URL "
"in Render Environment Variables."
)

============================================================

DATABASE CONNECTION

============================================================

def get_db():
return psycopg2.connect(
DATABASE_URL,
cursor_factory=RealDictCursor
)

============================================================

DATABASE TABLES

============================================================

def create_tables():

db = get_db()

try:

    with db.cursor() as cur:

        # ------------------------------------------------
        # USERS
        # ------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                fullname VARCHAR(100) NOT NULL,
                username VARCHAR(50) UNIQUE NOT NULL,
                phone VARCHAR(30) UNIQUE NOT NULL,
                login_password TEXT NOT NULL,
                withdrawal_password TEXT NOT NULL,
                referral_code VARCHAR(20) UNIQUE NOT NULL,
                referred_by VARCHAR(20),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


        # ------------------------------------------------
        # ACCOUNTS
        # ------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id SERIAL PRIMARY KEY,

                user_id INTEGER UNIQUE
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                deposit_account NUMERIC(14,2)
                    DEFAULT 0,

                income_account NUMERIC(14,2)
                    DEFAULT 0,

                referral_account NUMERIC(14,2)
                    DEFAULT 0
            )
        """)


        # ------------------------------------------------
        # PLANS
        # ------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS plans (
                id SERIAL PRIMARY KEY,

                plan_name VARCHAR(100) NOT NULL,

                investment_amount NUMERIC(14,2)
                    NOT NULL,

                daily_income NUMERIC(14,2)
                    NOT NULL,

                duration INTEGER NOT NULL,

                status VARCHAR(20)
                    DEFAULT 'Active'
            )
        """)


        # ------------------------------------------------
        # USER PLANS
        # ------------------------------------------------

        cur.execute("""
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

                last_claim_time TIMESTAMP,

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
            )
        """)


        # ------------------------------------------------
        # BIND ACCOUNTS
        # ------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS bind_accounts (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                account_name VARCHAR(100) NOT NULL,

                phone_number VARCHAR(30) NOT NULL,

                network VARCHAR(50) NOT NULL
            )
        """)


        # ------------------------------------------------
        # DEPOSITS
        # ------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS deposits (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                amount NUMERIC(14,2) NOT NULL,

                phone VARCHAR(30),

                payment_reference VARCHAR(100),

                payment_method VARCHAR(50),

                status VARCHAR(20)
                    DEFAULT 'Pending',

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
            )
        """)


        # ------------------------------------------------
        # WITHDRAWALS
        # ------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                amount NUMERIC(14,2) NOT NULL,

                account_id INTEGER
                    REFERENCES bind_accounts(id),

                withdrawal_fee NUMERIC(14,2)
                    DEFAULT 0,

                status VARCHAR(20)
                    DEFAULT 'Pending',

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
            )
        """)


        # ------------------------------------------------
        # TRANSACTIONS
        # ------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                transaction_type VARCHAR(50),

                amount NUMERIC(14,2),

                description TEXT,

                status VARCHAR(30),

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
            )
        """)


        # ------------------------------------------------
        # REFERRALS
        # ------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                referred_user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                level INTEGER DEFAULT 1
            )
        """)


        # ------------------------------------------------
        # CLAIM HISTORY
        # ------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS claim_history (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                plan_id INTEGER
                    REFERENCES plans(id)
                    ON DELETE CASCADE,

                amount NUMERIC(14,2),

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
            )
        """)


        # ------------------------------------------------
        # SUPPORT
        # ------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS support_messages (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                message TEXT NOT NULL,

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
            )
        """)


        # ------------------------------------------------
        # ADMINS
        # ------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,

                username VARCHAR(50)
                    UNIQUE NOT NULL,

                password TEXT NOT NULL
            )
        """)


        # ------------------------------------------------
        # DEMO PLANS
        # ------------------------------------------------

        cur.execute("""
            INSERT INTO plans
                (
                    plan_name,
                    investment_amount,
                    daily_income,
                    duration
                )
            SELECT *
            FROM (
                VALUES
                ('Demo Plan 1', 50, 8, 100),
                ('Demo Plan 2', 100, 20, 100),
                ('Demo Plan 3', 200, 40, 100)
            )
            AS new_plans(
                plan_name,
                investment_amount,
                daily_income,
                duration
            )
            WHERE NOT EXISTS (
                SELECT 1
                FROM plans
                WHERE plans.plan_name =
                      new_plans.plan_name
            )
        """)


    db.commit()

except Exception:

    db.rollback()
    app.logger.exception(
        "Database table creation failed"
    )

    raise

finally:

    db.close()

Create tables when application starts

create_tables()

============================================================

HOME

============================================================

@app.route("/")
def home():

if "user_id" in session:
    return redirect("/dashboard")

return redirect("/login")

============================================================

REGISTER

============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

invite_code = request.args.get(
    "ref",
    ""
).strip()


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
    ).strip()

    # Accept referral from either the URL or form
    referred_by = request.form.get(
        "referred_by",
        invite_code
    ).strip()


    # Required fields
    if not all([
        fullname,
        username,
        phone,
        password,
        withdrawal_password
    ]):

        return render_template(
            "register.html",
            invite_code=invite_code,
            error="Please fill in all required fields."
        )


    login_hash = generate_password_hash(
        password
    )

    withdrawal_hash = generate_password_hash(
        withdrawal_password
    )

    referral_code = secrets.token_hex(
        4
    ).upper()


    db = get_db()


    try:

        with db.cursor() as cur:

            # --------------------------------------------
            # CREATE USER
            # --------------------------------------------

            cur.execute("""
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
                referred_by or None
            ))


            user_id = cur.fetchone()["id"]


            # --------------------------------------------
            # CREATE ACCOUNT
            # --------------------------------------------

            cur.execute("""
                INSERT INTO accounts
                (
                    user_id
                )
                VALUES (%s)
            """, (
                user_id,
            ))


            # --------------------------------------------
            # REFERRAL
            # --------------------------------------------

            if referred_by:

                cur.execute("""
                    SELECT id
                    FROM users
                    WHERE referral_code = %s
                """, (
                    referred_by,
                ))

                inviter = cur.fetchone()


                if inviter:

                    cur.execute("""
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
                            %s
                        )
                    """, (
                        inviter["id"],
                        user_id,
                        1
                    ))


        db.commit()


        return redirect("/login")


    except psycopg2.errors.UniqueViolation:

        db.rollback()

        return render_template(
            "register.html",
            invite_code=invite_code,
            error="Username or phone number already exists."
        )


    except Exception:

        db.rollback()

        app.logger.exception(
            "Registration error"
        )

        return render_template(
            "register.html",
            invite_code=invite_code,
            error="Registration could not be completed."
        )


    finally:

        db.close()


return render_template(
    "register.html",
    invite_code=invite_code
)

============================================================

LOGIN

============================================================

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

        return render_template(
            "login.html",
            error="Please enter your phone number and password."
        )


    db = get_db()


    try:

        with db.cursor() as cur:

            cur.execute("""
                SELECT *
                FROM users
                WHERE phone = %s
                LIMIT 1
            """, (
                phone,
            ))

            user = cur.fetchone()


    finally:

        db.close()


    if user:

        if check_password_hash(
            user["login_password"],
            password
        ):

            session.clear()

            session["user_id"] = user["id"]

            return redirect(
                "/dashboard"
            )


    return render_template(
        "login.html",
        error="Invalid phone number or password."
    )


return render_template(
    "login.html"
)

============================================================

DASHBOARD

============================================================

@app.route("/dashboard")
def dashboard():

if "user_id" not in session:
    return redirect("/login")


db = get_db()


try:

    with db.cursor() as cur:

        # User
        cur.execute("""
            SELECT *
            FROM users
            WHERE id = %s
        """, (
            session["user_id"],
        ))

        user = cur.fetchone()


        # Account
        cur.execute("""
            SELECT *
            FROM accounts
            WHERE user_id = %s
        """, (
            session["user_id"],
        ))

        account = cur.fetchone()


        # Active plans
        cur.execute("""
            SELECT *
            FROM plans
            WHERE status = 'Active'
            ORDER BY id ASC
        """)

        plans = cur.fetchall()


finally:

    db.close()


if not user:
    session.clear()
    return redirect("/login")


return render_template(
    "dashboard.html",
    user=user,
    account=account,
    plans=plans
)

============================================================

BUY DEMO PLAN

============================================================

@app.route(
"/buy_plan/"int:plan_id" (int:plan_id)",
methods=["POST"]
)
def buy_plan(plan_id):

if "user_id" not in session:
    return redirect("/login")


db = get_db()


try:

    with db.cursor() as cur:

        cur.execute("""
            SELECT *
            FROM plans
            WHERE id = %s
            AND status = 'Active'
        """, (
            plan_id,
        ))

        plan = cur.fetchone()


        if not plan:

            return redirect("/dashboard")


        cur.execute("""
            SELECT *
            FROM accounts
            WHERE user_id = %s
        """, (
            session["user_id"],
        ))

        account = cur.fetchone()


        if not account:

            return redirect("/dashboard")


        investment = Decimal(
            str(plan["investment_amount"])
        )

        balance = Decimal(
            str(
                account["deposit_account"]
                or 0
            )
        )


        if balance < investment:

            return redirect("/dashboard")


        # Demo balance operation only
        cur.execute("""
            UPDATE accounts
            SET deposit_account =
                deposit_account - %s
            WHERE user_id = %s
        """, (
            investment,
            session["user_id"]
        ))


        cur.execute("""
            INSERT INTO user_plans
            (
                user_id,
                plan_id,
                status,
                last_claim_time
            )
            VALUES
            (
                %s,
                %s,
                'Active',
                NULL
            )
        """, (
            session["user_id"],
            plan_id
        ))


        cur.execute("""
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
                'Demo Plan',
                %s,
                %s,
                'Successful'
            )
        """, (
            session["user_id"],
            investment,
            "Demo plan selected: "
            + plan["plan_name"]
        ))


    db.commit()

    return redirect("/my_plan")


except Exception:

    db.rollback()

    app.logger.exception(
        "Plan purchase error"
    )

    return redirect("/dashboard")


finally:

    db.close()

============================================================

PROFILE

============================================================

@app.route("/profile")
def profile():

if "user_id" not in session:
    return redirect("/login")


db = get_db()


try:

    with db.cursor() as cur:

        cur.execute("""
            SELECT *
            FROM users
            WHERE id = %s
        """, (
            session["user_id"],
        ))

        user = cur.fetchone()


        cur.execute("""
            SELECT *
            FROM accounts
            WHERE user_id = %s
        """, (
            session["user_id"],
        ))

        account = cur.fetchone()


finally:

    db.close()


return render_template(
    "profile.html",
    user=user,
    account=account
)

============================================================

BIND PAYMENT ACCOUNT

============================================================

@app.route(
"/bind_account",
methods=["GET", "POST"]
)
def bind_account():

if "user_id" not in session:
    return redirect("/login")


db = get_db()


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


    if not account_name or not phone_number or not network:

        return redirect(
            "/bind_account"
        )


    try:

        with db.cursor() as cur:

            cur.execute("""
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


        db.commit()


    except Exception:

        db.rollback()

        app.logger.exception(
            "Bind account error"
        )


    finally:

        db.close()


    return redirect(
        "/bind_account"
    )


try:

    with db.cursor() as cur:

        cur.execute("""
            SELECT *
            FROM bind_accounts
            WHERE user_id = %s
            ORDER BY id DESC
        """, (
            session["user_id"],
        ))

        accounts = cur.fetchall()


finally:

    db.close()


return render_template(
    "bind_account.html",
    accounts=accounts
)

============================================================

WITHDRAWAL REQUEST — DEMO ONLY

============================================================

@app.route(
"/withdraw",
methods=["GET", "POST"]
)
def withdraw():

if "user_id" not in session:
    return redirect("/login")


db = get_db()


if request.method == "POST":

    amount_text = request.form.get(
        "amount",
        ""
    ).strip()

    withdrawal_password = request.form.get(
        "withdrawal_password",
        ""
    )

    account_id = request.form.get(
        "account_id",
        ""
    )


    try:

        amount = Decimal(
            amount_text
        )

    except (InvalidOperation, ValueError):

        return redirect("/withdraw")


    if amount <= 0:
        return redirect("/withdraw")


    try:

        with db.cursor() as cur:

            cur.execute("""
                SELECT *
                FROM users
                WHERE id = %s
            """, (
                session["user_id"],
            ))

            user = cur.fetchone()


            if not user:

                return redirect("/login")


            if not check_password_hash(
                user["withdrawal_password"],
                withdrawal_password
            ):

                return redirect(
                    "/withdraw"
                )


            cur.execute("""
                SELECT *
                FROM accounts
                WHERE user_id = %s
            """, (
                session["user_id"],
            ))

            account = cur.fetchone()


            balance = Decimal(
                str(
                    account["income_account"]
                    or 0
                )
            )


            if balance < amount:

                return redirect(
                    "/withdraw"
                )


            cur.execute("""
                SELECT id
                FROM bind_accounts
                WHERE id = %s
                AND user_id = %s
            """, (
                account_id,
                session["user_id"]
            ))

            bound_account = cur.fetchone()


            if not bound_account:

                return redirect(
                    "/withdraw"
                )


            # Demo-only: reserve the requested
            # amount from the simulated balance.
            cur.execute("""
                UPDATE accounts
                SET income_account =
                    income_account - %s
                WHERE user_id = %s
            """, (
                amount,
                session["user_id"]
            ))


            cur.execute("""
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
                    %s,
                    %s,
                    %s,
                    0,
                    'Pending'
                )
            """, (
                session["user_id"],
                amount,
                account_id
            ))


            cur.execute("""
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
                    'Demo Withdrawal',
                    %s,
                    'Demo withdrawal request',
                    'Pending'
                )
            """, (
                session["user_id"],
                amount
            ))


        db.commit()


    except Exception:

        db.rollback()

        app.logger.exception(
            "Withdrawal error"
        )


    finally:

        db.close()


    return redirect(
        "/transaction_history"
    )


try:

    with db.cursor() as cur:

        cur.execute("""
            SELECT *
            FROM bind_accounts
            WHERE user_id = %s
            ORDER BY id DESC
        """, (
            session["user_id"],
        ))

        accounts = cur.fetchall()


finally:

    db.close()


return render_template(
    "withdraw.html",
    accounts=accounts
)

============================================================

MY PLAN

============================================================

@app.route(
"/my_plan",
methods=["GET", "POST"]
)
def my_plan():

if "user_id" not in session:
    return redirect("/login")


db = get_db()


try:

    with db.cursor() as cur:

        cur.execute("""
            SELECT
                user_plans.*,
                plans.plan_name,
                plans.daily_income,
                plans.duration,
                plans.investment_amount

            FROM user_plans

            JOIN plans
                ON user_plans.plan_id = plans.id

            WHERE user_plans.user_id = %s

            AND user_plans.status = 'Active'

            ORDER BY user_plans.id DESC

            LIMIT 1
        """, (
            session["user_id"],
        ))

        plan = cur.fetchone()


        can_claim = False


        if plan:

            if plan["last_claim_time"]:

                last_claim = (
                    plan["last_claim_time"]
                )

                can_claim = (
                    datetime.now()
                    >=
                    last_claim
                    +
                    timedelta(hours=24)
                )

            else:

                can_claim = True


        if request.method == "POST":

            if not plan:

                return redirect(
                    "/my_plan"
                )


            if not can_claim:

                return redirect(
                    "/my_plan"
                )


            amount = Decimal(
                str(
                    plan["daily_income"]
                )
            )


            # Demo simulated income
            cur.execute("""
                UPDATE accounts
                SET income_account =
                    income_account + %s
                WHERE user_id = %s
            """, (
                amount,
                session["user_id"]
            ))


            now = datetime.now()


            cur.execute("""
                UPDATE user_plans

                SET last_claim_time = %s

                WHERE id = %s
            """, (
                now,
                plan["id"]
            ))


            cur.execute("""
                INSERT INTO claim_history
                (
                    user_id,
                    plan_id,
                    amount
                )
                VALUES
                (
                    %s,
                    %s,
                    %s
                )
            """, (
                session["user_id"],
                plan["plan_id"],
                amount
            ))


            cur.execute("""
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
                    'Demo Claim',
                    %s,
                    'Simulated plan claim',
                    'Successful'
                )
            """, (
                session["user_id"],
                amount
            ))


            db.commit()

            return redirect(
                "/my_plan"
            )


finally:

    db.close()


return render_template(
    "my_plan.html",
    plan=plan,
    can_claim=can_claim
)

============================================================

DEPOSIT PAGE — DEMO

============================================================

@app.route("/deposit")
def deposit():

if "user_id" not in session:
    return redirect("/login")


return render_template(
    "deposit.html"
)

============================================================

DEMO DEPOSIT SUBMISSION

============================================================

@app.route("/deposit_success")
def deposit_success():

if "user_id" not in session:
    return redirect("/login")


amount_text = request.args.get(
    "amount",
    ""
)

phone = request.args.get(
    "phone",
    ""
)

reference = request.args.get(
    "reference",
    ""
)


try:

    amount = Decimal(
        amount_text
    )

except (InvalidOperation, ValueError):

    return redirect(
        "/deposit"
    )


if amount <= 0:

    return redirect(
        "/deposit"
    )


db = get_db()


try:

    with db.cursor() as cur:

        cur.execute("""
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
                %s,
                %s,
                %s,
                %s,
                %s,
                'Pending'
            )
        """, (
            session["user_id"],
            amount,
            phone,
            reference,
            "Demo"
        ))


        cur.execute("""
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
                'Demo Deposit',
                %s,
                'Demo deposit submitted',
                'Pending'
            )
        """, (
            session["user_id"],
            amount
        ))


    db.commit()


except Exception:

    db.rollback()

    app.logger.exception(
        "Deposit submission error"
    )


finally:

    db.close()


return redirect(
    "/transaction_history"
)

============================================================

TEAM / REFERRALS

============================================================

@app.route("/team")
def team():

if "user_id" not in session:
    return redirect("/login")


db = get_db()


try:

    with db.cursor() as cur:

        cur.execute("""
            SELECT *
            FROM users
            WHERE id = %s
        """, (
            session["user_id"],
        ))

        user = cur.fetchone()


        if not user:

            return redirect(
                "/logout"
            )


        # Level 1
        cur.execute("""
            SELECT *
            FROM users
            WHERE referred_by = %s
            ORDER BY id DESC
        """, (
            user["referral_code"],
        ))

        level1 = cur.fetchall()


        # Level 2
        level2 = []


        for member in level1:

            cur.execute("""
                SELECT *
                FROM users
                WHERE referred_by = %s
                ORDER BY id DESC
            """, (
                member["referral_code"],
            ))

            level2.extend(
                cur.fetchall()
            )


        # Level 3
        level3 = []


        for member in level2:

            cur.execute("""
                SELECT *
                FROM users
                WHERE referred_by = %s
                ORDER BY id DESC
            """, (
                member["referral_code"],
            ))

            level3.extend(
                cur.fetchall()
            )


finally:

    db.close()


return render_template(
    "team.html",

    user=user,

    level1=level1,
    level2=level2,
    level3=level3,

    level1_count=len(level1),
    level2_count=len(level2),
    level3_count=len(level3)
)

============================================================

SUPPORT

============================================================

@app.route(
"/support",
methods=["GET", "POST"]
)
def support():

if "user_id" not in session:
    return redirect("/login")


db = get_db()


if request.method == "POST":

    message = request.form.get(
        "message",
        ""
    ).strip()


    if message:

        try:

            with db.cursor() as cur:

                cur.execute("""
                    INSERT INTO support_messages
                    (
                        user_id,
                        message
                    )
                    VALUES
                    (
                        %s,
                        %s
                    )
                """, (
                    session["user_id"],
                    message
                ))


            db.commit()


        except Exception:

            db.rollback()

            app.logger.exception(
                "Support message error"
            )


    db.close()

    return redirect(
        "/support"
    )


try:

    with db.cursor() as cur:

        cur.execute("""
            SELECT *
            FROM support_messages
            WHERE user_id = %s
            ORDER BY id DESC
        """, (
            session["user_id"],
        ))

        messages = cur.fetchall()


finally:

    db.close()


return render_template(
    "service.html",
    messages=messages
)

============================================================

TRANSACTION HISTORY

============================================================

@app.route("/transaction_history")
def transaction_history():

if "user_id" not in session:
    return redirect("/login")


db = get_db()


try:

    with db.cursor() as cur:

        cur.execute("""
            SELECT *
            FROM transactions
            WHERE user_id = %s
            ORDER BY id DESC
        """, (
            session["user_id"],
        ))

        transactions = cur.fetchall()


finally:

    db.close()


return render_template(
    "transaction_history.html",
    transactions=transactions
)

============================================================

LOGOUT

============================================================

@app.route("/logout")
def logout():

session.clear()

return redirect(
    "/login"
)

============================================================

ADMIN LOGIN

============================================================

@app.route(
"/admin/login",
methods=["GET", "POST"]
)
def admin_login():

if request.method == "POST":

    username = request.form.get(
        "username",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    )


    db = get_db()


    try:

        with db.cursor() as cur:

            cur.execute("""
                SELECT *
                FROM admins
                WHERE username = %s
            """, (
                username,
            ))

            admin = cur.fetchone()


    finally:

        db.close()


    if admin and check_password_hash(
        admin["password"],
        password
    ):

        session["admin_id"] = admin["id"]

        return redirect(
            "/admin/dashboard"
        )


    return render_template(
        "admin_login.html",
        error="Invalid admin details."
    )


return render_template(
    "admin_login.html"
)

============================================================

ADMIN PROTECTION

============================================================

def admin_required(function):

@wraps(function)
def wrapper(*args, **kwargs):

    if "admin_id" not in session:

        return redirect(
            "/admin/login"
        )

    return function(
        *args,
        **kwargs
    )

return wrapper

============================================================

ADMIN DASHBOARD

============================================================

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():

db = get_db()


try:

    with db.cursor() as cur:

        cur.execute("""
            SELECT COUNT(*) AS total
            FROM users
        """)

        users = cur.fetchone()["total"]


        cur.execute("""
            SELECT COUNT(*) AS total
            FROM deposits
            WHERE status = 'Pending'
        """)

        deposits = cur.fetchone()["total"]


        cur.execute("""
            SELECT COUNT(*) AS total
            FROM withdrawals
            WHERE status = 'Pending'
        """)

        withdrawals = cur.fetchone()["total"]


finally:

    db.close()


return render_template(
    "admin.html",
    users=users,
    deposits=deposits,
    withdrawals=withdrawals
)

============================================================

ADMIN DEPOSITS

============================================================

@app.route("/admin/deposits")
@admin_required
def admin_deposits():

db = get_db()


try:

    with db.cursor() as cur:

        cur.execute("""
            SELECT
                deposits.*,
                users.username,
                users.phone
            FROM deposits
            JOIN users
                ON deposits.user_id = users.id
            WHERE deposits.status = 'Pending'
            ORDER BY deposits.id DESC
        """)

        deposits = cur.fetchall()


finally:

    db.close()


return render_template(
    "admin_deposit.html",
    deposits=deposits
)

============================================================

ADMIN APPROVE DEMO DEPOSIT

============================================================

@app.route(
"/admin/deposit/approve/"int:id" (int:id)"
)
@admin_required
def approve_deposit(id):

db = get_db()


try:

    with db.cursor() as cur:

        cur.execute("""
            SELECT *
            FROM deposits
            WHERE id = %s
            AND status = 'Pending'
        """, (
            id,
        ))

        deposit = cur.fetchone()


        if deposit:

            cur.execute("""
                UPDATE deposits
                SET status = 'Approved'
                WHERE id = %s
            """, (
                id,
            ))


            # Demo balance only
            cur.execute("""
                UPDATE accounts
                SET deposit_account =
                    deposit_account + %s
                WHERE user_id = %s
            """, (
                deposit["amount"],
                deposit["user_id"]
            ))


    db.commit()


except Exception:

    db.rollback()

    app.logger.exception(
        "Deposit approval error"
    )


finally:

    db.close()


return redirect(
    "/admin/deposits"
)

============================================================

ADMIN REJECT DEPOSIT

============================================================

@app.route(
"/admin/deposit/reject/"int:id" (int:id)"
)
@admin_required
def reject_deposit(id):

db = get_db()


try:

    with db.cursor() as cur:

        cur.execute("""
            UPDATE deposits
            SET status = 'Rejected'
            WHERE id = %s
        """, (
            id,
        ))


    db.commit()


except Exception:

    db.rollback()

    app.logger.exception(
        "Deposit rejection error"
    )


finally:

    db.close()


return redirect(
    "/admin/deposits"
)

============================================================

ADMIN WITHDRAWALS

============================================================

@app.route("/admin/withdrawals")
@admin_required
def admin_withdrawals():

db = get_db()


try:

    with db.cursor() as cur:

        cur.execute("""
            SELECT
                withdrawals.*,
                users.username,
                users.phone
            FROM withdrawals
            JOIN users
                ON withdrawals.user_id = users.id
            WHERE withdrawals.status = 'Pending'
            ORDER BY withdrawals.id DESC
        """)

        withdrawals = cur.fetchall()


finally:

    db.close()


return render_template(
    "admin_withdraw.html",
    withdrawals=withdrawals
)

============================================================

ADMIN APPROVE DEMO WITHDRAWAL

============================================================

@app.route(
"/admin/withdraw/approve/"int:id" (int:id)"
)
@admin_required
def approve_withdraw(id):

db = get_db()


try:

    with db.cursor() as cur:

        cur.execute("""
            UPDATE withdrawals
            SET status = 'Approved'
            WHERE id = %s
            AND status = 'Pending'
        """, (
            id,
        ))


    db.commit()


except Exception:

    db.rollback()

    app.logger.exception(
        "Withdrawal approval error"
    )


finally:

    db.close()


return redirect(
    "/admin/withdrawals"
)

============================================================

ADMIN REJECT WITHDRAWAL

============================================================

@app.route(
"/admin/withdraw/reject/"int:id" (int:id)"
)
@admin_required
def reject_withdraw(id):

db = get_db()


try:

    with db.cursor() as cur:

        cur.execute("""
            SELECT *
            FROM withdrawals
            WHERE id = %s
            AND status = 'Pending'
        """, (
            id,
        ))

        withdrawal = cur.fetchone()


        if withdrawal:

            # Return the simulated balance
            cur.execute("""
                UPDATE accounts
                SET income_account =
                    income_account + %s
                WHERE user_id = %s
            """, (
                withdrawal["amount"],
                withdrawal["user_id"]
            ))


            cur.execute("""
                UPDATE withdrawals
                SET status = 'Rejected'
                WHERE id = %s
            """, (
                id,
            ))


    db.commit()


except Exception:

    db.rollback()

    app.logger.exception(
        "Withdrawal rejection error"
    )


finally:

    db.close()


return redirect(
    "/admin/withdrawals"
)

============================================================

ADMIN USERS

============================================================

@app.route("/admin/users")
@admin_required
def admin_users():

search = request.args.get(
    "search",
    ""
).strip()


db = get_db()


try:

    with db.cursor() as cur:

        cur.execute("""
            SELECT *
            FROM users
            WHERE username ILIKE %s
               OR phone ILIKE %s
            ORDER BY id DESC
        """, (
            "%" + search + "%",
            "%" + search + "%"
        ))

        users = cur.fetchall()


finally:

    db.close()


return render_template(
    "admin_users.html",
    users=users
)

============================================================

ADMIN BIND ACCOUNTS

============================================================

@app.route("/admin/bind_accounts")
@admin_required
def admin_bind_accounts():

db = get_db()


try:

    with db.cursor() as cur:

        cur.execute("""
            SELECT
                bind_accounts.*,
                users.username
            FROM bind_accounts
            JOIN users
                ON bind_accounts.user_id = users.id
            ORDER BY bind_accounts.id DESC
        """)

        accounts = cur.fetchall()


finally:

    db.close()


return render_template(
    "admin_bind_accounts.html",
    accounts=accounts
)

============================================================

DELETE BIND ACCOUNT

============================================================

@app.route(
"/admin/bind_account/delete/"int:id" (int:id)"
)
@admin_required
def delete_bind_account(id):

db = get_db()


try:

    with db.cursor() as cur:

        cur.execute("""
            DELETE FROM bind_accounts
            WHERE id = %s
        """, (
            id,
        ))


    db.commit()


except Exception:

    db.rollback()

    app.logger.exception(
        "Bind account deletion error"
    )


finally:

    db.close()


return redirect(
    "/admin/bind_accounts"
)

============================================================

ADMIN LOGOUT

============================================================

@app.route("/admin/logout")
def admin_logout():

session.pop(
    "admin_id",
    None
)

return redirect(
    "/admin/login"
)

============================================================

RUN

============================================================

if name == "main":

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
