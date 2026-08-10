import os
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
)
from werkzeug.security import generate_password_hash, check_password_hash

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None


# ============================================================
# APP CONFIGURATION
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-key"
)

DATABASE_URL = os.environ.get("DATABASE_URL")

# Demo-only payment number.
# This is NOT a real payment processor.
DEMO_PAYMENT_NUMBER = os.environ.get(
    "DEMO_PAYMENT_NUMBER",
    "0000000000"
)

ADMIN_USERNAME = os.environ.get(
    "ADMIN_USERNAME",
    "Williams"
)

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "Williams12"
)


# ============================================================
# DEMO PLANS
# ============================================================

PLANS = {
    1: {
        "name": "Zenith 1",
        "investment": Decimal("50"),
        "daily": Decimal("8"),
        "duration": 30,
    },
    2: {
        "name": "Zenith 2",
        "investment": Decimal("100"),
        "daily": Decimal("20"),
        "duration": 30,
    },
    3: {
        "name": "Zenith 3",
        "investment": Decimal("200"),
        "daily": Decimal("40"),
        "duration": 30,
    },
    4: {
        "name": "Zenith 4",
        "investment": Decimal("300"),
        "daily": Decimal("65"),
        "duration": 30,
    },
    5: {
        "name": "Zenith 5",
        "investment": Decimal("500"),
        "daily": Decimal("100"),
        "duration": 30,
    },
    6: {
        "name": "Zenith 6",
        "investment": Decimal("600"),
        "daily": Decimal("200"),
        "duration": 30,
    },
    7: {
        "name": "Zenith 7",
        "investment": Decimal("1000"),
        "daily": Decimal("360"),
        "duration": 30,
    },
}


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is missing.")

    if psycopg2 is None:
        raise RuntimeError(
            "psycopg2 is not installed. Add psycopg2-binary to requirements.txt."
        )

    return psycopg2.connect(
        DATABASE_URL,
        sslmode="require"
    )


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db():

    conn = get_conn()
    cur = conn.cursor()

    try:

        # ----------------------------------------------------
        # USERS
        # ----------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE,
                fullname TEXT DEFAULT '',
                phone TEXT UNIQUE,
                password_hash TEXT,
                withdraw_password_hash TEXT,
                referral_code TEXT UNIQUE,
                referred_by TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ----------------------------------------------------
        # LEGACY USER COLUMNS
        # ----------------------------------------------------

        cur.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS username TEXT
        """)

        cur.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS fullname TEXT DEFAULT ''
        """)

        cur.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS phone TEXT
        """)

        cur.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS password_hash TEXT
        """)

        cur.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS withdraw_password_hash TEXT
        """)

        cur.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS referral_code TEXT
        """)

        cur.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS referred_by TEXT
        """)

        cur.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        """)

        # Legacy columns that appeared in older versions.
        cur.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS login_password TEXT
        """)

        cur.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS password TEXT
        """)

        cur.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS withdrawal_password TEXT
        """)

        cur.execute("""
            ALTER TABLE users
            ALTER COLUMN username TYPE TEXT
        """)

        cur.execute("""
            ALTER TABLE users
            ALTER COLUMN fullname TYPE TEXT
        """)

        cur.execute("""
            ALTER TABLE users
            ALTER COLUMN phone TYPE TEXT
        """)

        cur.execute("""
            ALTER TABLE users
            ALTER COLUMN referral_code TYPE TEXT
        """)

        cur.execute("""
            ALTER TABLE users
            ALTER COLUMN referred_by TYPE TEXT
        """)

        # Older databases may have NOT NULL constraints
        # on legacy password columns.
        cur.execute("""
            ALTER TABLE users
            ALTER COLUMN login_password DROP NOT NULL
        """)

        cur.execute("""
            ALTER TABLE users
            ALTER COLUMN password DROP NOT NULL
        """)

        cur.execute("""
            ALTER TABLE users
            ALTER COLUMN withdrawal_password DROP NOT NULL
        """)

        # ----------------------------------------------------
        # MIGRATE OLD PASSWORD DATA
        # ----------------------------------------------------

        cur.execute("""
            UPDATE users
            SET password_hash = login_password
            WHERE
                (password_hash IS NULL OR password_hash = '')
                AND login_password IS NOT NULL
                AND login_password <> ''
        """)

        cur.execute("""
            UPDATE users
            SET password_hash = password
            WHERE
                (password_hash IS NULL OR password_hash = '')
                AND password IS NOT NULL
                AND password <> ''
        """)

        cur.execute("""
            UPDATE users
            SET withdraw_password_hash = withdrawal_password
            WHERE
                (withdraw_password_hash IS NULL
                 OR withdraw_password_hash = '')
                AND withdrawal_password IS NOT NULL
                AND withdrawal_password <> ''
        """)

        # ----------------------------------------------------
        # ACCOUNTS
        # ----------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                user_id INTEGER PRIMARY KEY
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                deposit_account NUMERIC(14,2)
                    DEFAULT 5.00,

                income_account NUMERIC(14,2)
                    DEFAULT 0,

                referral_account NUMERIC(14,2)
                    DEFAULT 0,

                withdraw_account NUMERIC(14,2)
                    DEFAULT 0
            )
        """)

        cur.execute("""
            ALTER TABLE accounts
            ADD COLUMN IF NOT EXISTS deposit_account
            NUMERIC(14,2) DEFAULT 5.00
        """)

        cur.execute("""
            ALTER TABLE accounts
            ADD COLUMN IF NOT EXISTS income_account
            NUMERIC(14,2) DEFAULT 0
        """)

        cur.execute("""
            ALTER TABLE accounts
            ADD COLUMN IF NOT EXISTS referral_account
            NUMERIC(14,2) DEFAULT 0
        """)

        cur.execute("""
            ALTER TABLE accounts
            ADD COLUMN IF NOT EXISTS withdraw_account
            NUMERIC(14,2) DEFAULT 0
        """)

        # ----------------------------------------------------
        # PLANS
        # ----------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS plans (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                plan_id INTEGER NOT NULL,

                plan_name TEXT NOT NULL,

                investment_amount NUMERIC(14,2)
                    NOT NULL,

                daily_income NUMERIC(14,2)
                    NOT NULL,

                duration INTEGER NOT NULL,

                started_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP,

                last_claim_at TIMESTAMP,

                next_claim_at TIMESTAMP,

                days_claimed INTEGER
                    DEFAULT 0,

                active BOOLEAN
                    DEFAULT TRUE
            )
        """)

        # IMPORTANT:
        # Existing old "plans" table may not contain user_id.
        # Add every required column BEFORE creating indexes.

        cur.execute("""
            ALTER TABLE plans
            ADD COLUMN IF NOT EXISTS user_id INTEGER
        """)

        cur.execute("""
            ALTER TABLE plans
            ADD COLUMN IF NOT EXISTS plan_id INTEGER
        """)

        cur.execute("""
            ALTER TABLE plans
            ADD COLUMN IF NOT EXISTS plan_name TEXT
        """)

        cur.execute("""
            ALTER TABLE plans
            ADD COLUMN IF NOT EXISTS investment_amount
            NUMERIC(14,2)
        """)

        cur.execute("""
            ALTER TABLE plans
            ADD COLUMN IF NOT EXISTS daily_income
            NUMERIC(14,2)
        """)

        cur.execute("""
            ALTER TABLE plans
            ADD COLUMN IF NOT EXISTS duration INTEGER
        """)

        cur.execute("""
            ALTER TABLE plans
            ADD COLUMN IF NOT EXISTS started_at TIMESTAMP
        """)

        cur.execute("""
            ALTER TABLE plans
            ADD COLUMN IF NOT EXISTS last_claim_at TIMESTAMP
        """)

        cur.execute("""
            ALTER TABLE plans
            ADD COLUMN IF NOT EXISTS next_claim_at TIMESTAMP
        """)

        cur.execute("""
            ALTER TABLE plans
            ADD COLUMN IF NOT EXISTS days_claimed INTEGER DEFAULT 0
        """)

        cur.execute("""
            ALTER TABLE plans
            ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT TRUE
        """)

        # ----------------------------------------------------
        # FIX OLD PLAN NULLS
        # ----------------------------------------------------

        cur.execute("""
            UPDATE plans
            SET started_at = CURRENT_TIMESTAMP
            WHERE started_at IS NULL
        """)

        cur.execute("""
            UPDATE plans
            SET days_claimed = 0
            WHERE days_claimed IS NULL
        """)

        cur.execute("""
            UPDATE plans
            SET active = TRUE
            WHERE active IS NULL
        """)

        # Existing plans that never had next_claim_at:
        # start their 24-hour timer from started_at.
        cur.execute("""
            UPDATE plans
            SET next_claim_at = started_at + INTERVAL '24 hours'
            WHERE
                next_claim_at IS NULL
                AND started_at IS NOT NULL
                AND active = TRUE
        """)

        # ----------------------------------------------------
        # PLAN INDEX
        # ----------------------------------------------------

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_plans_user_id
            ON plans(user_id)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_plans_active
            ON plans(active)
        """)

        # ----------------------------------------------------
        # TRANSACTIONS
        # ----------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                transaction_type TEXT NOT NULL,

                amount NUMERIC(14,2)
                    NOT NULL,

                status TEXT NOT NULL,

                reference TEXT,

                description TEXT,

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            ALTER TABLE transactions
            ADD COLUMN IF NOT EXISTS user_id INTEGER
        """)

        cur.execute("""
            ALTER TABLE transactions
            ADD COLUMN IF NOT EXISTS transaction_type TEXT
        """)

        cur.execute("""
            ALTER TABLE transactions
            ADD COLUMN IF NOT EXISTS amount NUMERIC(14,2)
        """)

        cur.execute("""
            ALTER TABLE transactions
            ADD COLUMN IF NOT EXISTS status TEXT
        """)

        cur.execute("""
            ALTER TABLE transactions
            ADD COLUMN IF NOT EXISTS reference TEXT
        """)

        cur.execute("""
            ALTER TABLE transactions
            ADD COLUMN IF NOT EXISTS description TEXT
        """)

        cur.execute("""
            ALTER TABLE transactions
            ADD COLUMN IF NOT EXISTS created_at TIMESTAMP
        """)

        # ----------------------------------------------------
        # WITHDRAWAL ACCOUNTS
        # ----------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS withdrawal_accounts (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                account_name TEXT NOT NULL,

                phone TEXT NOT NULL,

                network TEXT NOT NULL,

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            ALTER TABLE withdrawal_accounts
            ADD COLUMN IF NOT EXISTS user_id INTEGER
        """)

        cur.execute("""
            ALTER TABLE withdrawal_accounts
            ADD COLUMN IF NOT EXISTS account_name TEXT
        """)

        cur.execute("""
            ALTER TABLE withdrawal_accounts
            ADD COLUMN IF NOT EXISTS phone TEXT
        """)

        cur.execute("""
            ALTER TABLE withdrawal_accounts
            ADD COLUMN IF NOT EXISTS network TEXT
        """)

        cur.execute("""
            ALTER TABLE withdrawal_accounts
            ADD COLUMN IF NOT EXISTS created_at TIMESTAMP
        """)

        # ----------------------------------------------------
        # DEMO DEPOSIT REQUESTS
        # ----------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS deposit_requests (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                amount NUMERIC(14,2)
                    NOT NULL,

                payment_number TEXT,

                reference TEXT,

                screenshot BYTEA,

                screenshot_filename TEXT,

                status TEXT
                    NOT NULL DEFAULT 'pending',

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP,

                reviewed_at TIMESTAMP
            )
        """)

        cur.execute("""
            ALTER TABLE deposit_requests
            ADD COLUMN IF NOT EXISTS user_id INTEGER
        """)

        cur.execute("""
            ALTER TABLE deposit_requests
            ADD COLUMN IF NOT EXISTS amount NUMERIC(14,2)
        """)

        cur.execute("""
            ALTER TABLE deposit_requests
            ADD COLUMN IF NOT EXISTS payment_number TEXT
        """)

        cur.execute("""
            ALTER TABLE deposit_requests
            ADD COLUMN IF NOT EXISTS reference TEXT
        """)

        cur.execute("""
            ALTER TABLE deposit_requests
            ADD COLUMN IF NOT EXISTS screenshot BYTEA
        """)

        cur.execute("""
            ALTER TABLE deposit_requests
            ADD COLUMN IF NOT EXISTS screenshot_filename TEXT
        """)

        cur.execute("""
            ALTER TABLE deposit_requests
            ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending'
        """)

        cur.execute("""
            ALTER TABLE deposit_requests
            ADD COLUMN IF NOT EXISTS created_at TIMESTAMP
        """)

        cur.execute("""
            ALTER TABLE deposit_requests
            ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP
        """)

        # ----------------------------------------------------
        # WITHDRAWAL REQUESTS
        # ----------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS withdrawal_requests (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                amount NUMERIC(14,2)
                    NOT NULL,

                account_id INTEGER
                    REFERENCES withdrawal_accounts(id)
                    ON DELETE SET NULL,

                status TEXT
                    NOT NULL DEFAULT 'pending',

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            ALTER TABLE withdrawal_requests
            ADD COLUMN IF NOT EXISTS user_id INTEGER
        """)

        cur.execute("""
            ALTER TABLE withdrawal_requests
            ADD COLUMN IF NOT EXISTS amount NUMERIC(14,2)
        """)

        cur.execute("""
            ALTER TABLE withdrawal_requests
            ADD COLUMN IF NOT EXISTS account_id INTEGER
        """)

        cur.execute("""
            ALTER TABLE withdrawal_requests
            ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending'
        """)

        cur.execute("""
            ALTER TABLE withdrawal_requests
            ADD COLUMN IF NOT EXISTS created_at TIMESTAMP
        """)

        # ----------------------------------------------------
        # ADMINS
        # ----------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,

                username TEXT UNIQUE NOT NULL,

                password_hash TEXT
            )
        """)

        cur.execute("""
            ALTER TABLE admins
            ADD COLUMN IF NOT EXISTS password_hash TEXT
        """)

        cur.execute("""
            ALTER TABLE admins
            ADD COLUMN IF NOT EXISTS password TEXT
        """)

        cur.execute("""
            ALTER TABLE admins
            ALTER COLUMN username TYPE TEXT
        """)

        cur.execute("""
            ALTER TABLE admins
            ALTER COLUMN password DROP NOT NULL
        """)

        # ----------------------------------------------------
        # REFERRAL CODES
        # ----------------------------------------------------

        cur.execute("""
            SELECT id
            FROM users
            WHERE referral_code IS NULL
               OR referral_code = ''
        """)

        missing_referrals = cur.fetchall()

        for row in missing_referrals:

            user_id = row[0]

            code = (
                "ZEN"
                + str(user_id)
                + datetime.utcnow().strftime("%y%m%d%H%M%S")
                + os.urandom(3).hex()
            )

            cur.execute("""
                UPDATE users
                SET referral_code=%s
                WHERE id=%s
            """, (code, user_id))

        # ----------------------------------------------------
        # CREATE ACCOUNTS FOR EXISTING USERS
        # ----------------------------------------------------

        cur.execute("""
            INSERT INTO accounts (
                user_id,
                deposit_account,
                income_account,
                referral_account,
                withdraw_account
            )

            SELECT
                u.id,
                5.00,
                0,
                0,
                0

            FROM users u

            LEFT JOIN accounts a
                ON a.user_id = u.id

            WHERE a.user_id IS NULL
        """)

        # ----------------------------------------------------
        # ADMIN
        # ----------------------------------------------------

        admin_hash = generate_password_hash(
            ADMIN_PASSWORD
        )

        cur.execute("""
            INSERT INTO admins (
                username,
                password_hash
            )

            VALUES (%s,%s)

            ON CONFLICT (username)

            DO UPDATE SET
                password_hash = EXCLUDED.password_hash
        """, (
            ADMIN_USERNAME,
            admin_hash
        ))

        conn.commit()

        print("======================================")
        print("DATABASE INITIALIZATION SUCCESS")
        print("Admin username:", ADMIN_USERNAME)
        print("======================================")

    except Exception as exc:

        conn.rollback()

        print("======================================")
        print("DATABASE INITIALIZATION ERROR")
        print(exc)
        print("======================================")

        raise

    finally:

        cur.close()
        conn.close()


# ============================================================
# DATABASE HELPERS
# ============================================================

def query_one(sql, params=()):

    conn = get_conn()

    cur = conn.cursor(
        cursor_factory=RealDictCursor
    )

    try:

        cur.execute(sql, params)

        return cur.fetchone()

    finally:

        cur.close()
        conn.close()


def query_all(sql, params=()):

    conn = get_conn()

    cur = conn.cursor(
        cursor_factory=RealDictCursor
    )

    try:

        cur.execute(sql, params)

        return cur.fetchall()

    finally:

        cur.close()
        conn.close()


def execute(sql, params=(), fetchone=False):

    conn = get_conn()

    cur = conn.cursor(
        cursor_factory=RealDictCursor
    )

    try:

        cur.execute(sql, params)

        result = None

        if fetchone:
            result = cur.fetchone()

        conn.commit()

        return result

    except Exception:

        conn.rollback()

        raise

    finally:

        cur.close()
        conn.close()


# ============================================================
# USER HELPERS
# ============================================================

def current_user():

    user_id = session.get("user_id")

    if not user_id:
        return None

    return query_one("""
        SELECT *
        FROM users
        WHERE id=%s
    """, (user_id,))


def current_account(user_id):

    account = query_one("""
        SELECT *
        FROM accounts
        WHERE user_id=%s
    """, (user_id,))

    if account:
        return account

    execute("""
        INSERT INTO accounts (
            user_id,
            deposit_account,
            income_account,
            referral_account,
            withdraw_account
        )

        VALUES (%s,5.00,0,0,0)

        ON CONFLICT (user_id)
        DO NOTHING
    """, (user_id,))

    return query_one("""
        SELECT *
        FROM accounts
        WHERE user_id=%s
    """, (user_id,))


@app.context_processor
def inject_user():

    return {
        "logged_user": current_user()
    }


# ============================================================
# HOME
# ============================================================

@app.route("/")
def index():

    if session.get("user_id"):
        return redirect(
            url_for("dashboard")
        )

    return redirect(
        url_for("login")
    )


# ============================================================
# REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    invite_code = (
        request.args.get("ref", "").strip()
        or request.form.get("referred_by", "").strip()
    )

    referred_user = None

    if invite_code:

        referred_user = query_one("""
            SELECT id, username, referral_code
            FROM users
            WHERE referral_code=%s
        """, (invite_code,))

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

        withdraw_password = request.form.get(
            "withdraw_password",
            ""
        )

        if not fullname or not username or not phone:

            flash(
                "Please complete all required fields.",
                "error"
            )

            return render_template(
                "register.html",
                invite_code=invite_code
            )

        if not password or not withdraw_password:

            flash(
                "Please enter both passwords.",
                "error"
            )

            return render_template(
                "register.html",
                invite_code=invite_code
            )

        existing = query_one("""
            SELECT id
            FROM users
            WHERE username=%s
               OR phone=%s
        """, (
            username,
            phone
        ))

        if existing:

            flash(
                "Username or phone number already exists.",
                "error"
            )

            return render_template(
                "register.html",
                invite_code=invite_code
            )

        if invite_code and not referred_user:

            flash(
                "Invalid referral code.",
                "error"
            )

            return render_template(
                "register.html",
                invite_code=invite_code
            )

        referral_code = (
            "ZEN"
            + datetime.utcnow().strftime("%y%m%d%H%M%S")
            + os.urandom(3).hex()
        )

        login_hash = generate_password_hash(
            password
        )

        withdrawal_hash = generate_password_hash(
            withdraw_password
        )

        # IMPORTANT:
        # We write the new password fields AND the old
        # legacy fields so existing databases with old
        # NOT NULL columns do not reject registration.

        user = execute("""
            INSERT INTO users (
                username,
                fullname,
                phone,
                password_hash,
                withdraw_password_hash,
                referral_code,
                referred_by,
                login_password,
                password,
                withdrawal_password
            )

            VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )

            RETURNING id
        """, (
            username,
            fullname,
            phone,
            login_hash,
            withdrawal_hash,
            referral_code,
            (
                referred_user["referral_code"]
                if referred_user
                else None
            ),
            login_hash,
            login_hash,
            withdrawal_hash
        ), fetchone=True)

        execute("""
            INSERT INTO accounts (
                user_id,
                deposit_account,
                income_account,
                referral_account,
                withdraw_account
            )

            VALUES (%s,5.00,0,0,0)

            ON CONFLICT (user_id)
            DO NOTHING
        """, (user["id"],))

        flash(
            "Registration successful. Please log in.",
            "success"
        )

        return redirect(
            url_for("login")
        )

    return render_template(
        "register.html",
        invite_code=invite_code
    )


# ============================================================
# LOGIN
# ============================================================

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

        user = query_one("""
            SELECT *
            FROM users
            WHERE phone=%s
        """, (phone,))

        if not user:

            flash(
                "Invalid phone number or password.",
                "error"
            )

            return render_template(
                "login.html"
            )

        stored_password = (
            user.get("password_hash")
            or user.get("login_password")
            or user.get("password")
        )

        if not stored_password:

            flash(
                "This account has no valid password.",
                "error"
            )

            return render_template(
                "login.html"
            )

        try:

            valid = check_password_hash(
                stored_password,
                password
            )

        except Exception:

            valid = False

        if valid:

            session.clear()

            session["user_id"] = user["id"]

            return redirect(
                url_for("dashboard")
            )

        flash(
            "Invalid phone number or password.",
            "error"
        )

    return render_template(
        "login.html"
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
def dashboard():

    user = current_user()

    if not user:

        return redirect(
            url_for("login")
        )

    account = current_account(
        user["id"]
    )

    return render_template(
        "dashboard.html",
        user=user,
        account=account,
        plans=PLANS
    )


# ============================================================
# DEMO DEPOSIT
# ============================================================

@app.route("/deposit", methods=["GET", "POST"])
def deposit():

    user = current_user()

    if not user:

        return redirect(
            url_for("login")
        )

    if request.method == "POST":

        try:

            amount = Decimal(
                request.form.get(
                    "amount",
                    "0"
                )
            )

        except (InvalidOperation, ValueError):

            amount = Decimal("0")

        if amount < Decimal("45"):

            flash(
                "Minimum demo deposit is GHS 45.",
                "error"
            )

            return redirect(
                url_for("deposit")
            )

        return render_template(
            "deposit.html",
            amount=amount,
            payment_number=DEMO_PAYMENT_NUMBER,
            show_payment_card=True
        )

    return render_template(
        "deposit.html",
        amount=None,
        payment_number=DEMO_PAYMENT_NUMBER,
        show_payment_card=False
    )


@app.route(
    "/deposit/submit",
    methods=["POST"]
)
def submit_deposit():

    user = current_user()

    if not user:

        return redirect(
            url_for("login")
        )

    try:

        amount = Decimal(
            request.form.get(
                "amount",
                "0"
            )
        )

    except (InvalidOperation, ValueError):

        amount = Decimal("0")

    if amount < Decimal("45"):

        flash(
            "Minimum demo deposit is GHS 45.",
            "error"
        )

        return redirect(
            url_for("deposit")
        )

    reference = request.form.get(
        "reference",
        ""
    ).strip()

    screenshot = request.files.get(
        "screenshot"
    )

    screenshot_data = None
    screenshot_filename = None

    if screenshot and screenshot.filename:

        # Limit demo uploads to 5 MB.
        data = screenshot.read()

        if len(data) > 5 * 1024 * 1024:

            flash(
                "Screenshot is too large. Maximum size is 5 MB.",
                "error"
            )

            return redirect(
                url_for("deposit")
            )

        screenshot_data = data
        screenshot_filename = screenshot.filename

    request_row = execute("""
        INSERT INTO deposit_requests (
            user_id,
            amount,
            payment_number,
            reference,
            screenshot,
            screenshot_filename,
            status
        )

        VALUES (
            %s,%s,%s,%s,%s,%s,'pending'
        )

        RETURNING id
    """, (
        user["id"],
        amount,
        DEMO_PAYMENT_NUMBER,
        reference,
        screenshot_data,
        screenshot_filename
    ), fetchone=True)

    execute("""
        INSERT INTO transactions (
            user_id,
            transaction_type,
            amount,
            status,
            reference,
            description
        )

        VALUES (
            %s,
            'deposit',
            %s,
            'pending',
            %s,
            'Demo deposit request'
        )
    """, (
        user["id"],
        amount,
        reference
    ))

    flash(
        "Demo deposit submitted for admin review.",
        "success"
    )

    return redirect(
        url_for("transaction_history")
    )


# ============================================================
# BUY PLAN
# ============================================================

@app.route("/buy_plan/<int:plan_id>")
def buy_plan(plan_id):

    user = current_user()

    if not user:

        return redirect(
            url_for("login")
        )

    if plan_id not in PLANS:

        flash(
            "Plan not found.",
            "error"
        )

        return redirect(
            url_for("dashboard")
        )

    plan = PLANS[plan_id]

    account = current_account(
        user["id"]
    )

    balance = Decimal(
        account["deposit_account"] or 0
    )

    if balance < plan["investment"]:

        return render_template(
            "insufficient_balance.html",
            account=account,
            plan={
                "investment_amount":
                    plan["investment"]
            }
        )

    return render_template(
        "confirm_plan.html",
        user=user,
        account=account,
        plan={
            "id": plan_id,
            "plan_name": plan["name"],
            "investment_amount":
                plan["investment"],
            "daily_income":
                plan["daily"],
            "duration":
                plan["duration"]
        }
    )


# ============================================================
# CONFIRM PLAN
# ============================================================

@app.route(
    "/confirm_buy_plan/<int:plan_id>",
    methods=["POST"]
)
def confirm_buy_plan(plan_id):

    user = current_user()

    if not user:

        return redirect(
            url_for("login")
        )

    if plan_id not in PLANS:

        flash(
            "Plan not found.",
            "error"
        )

        return redirect(
            url_for("dashboard")
        )

    plan = PLANS[plan_id]

    conn = get_conn()
    cur = conn.cursor()

    try:

        # Lock the account row so two requests cannot
        # spend the same balance.

        cur.execute("""
            SELECT deposit_account
            FROM accounts
            WHERE user_id=%s
            FOR UPDATE
        """, (user["id"],))

        account = cur.fetchone()

        if not account:

            conn.rollback()

            flash(
                "Account balance record not found.",
                "error"
            )

            return redirect(
                url_for("dashboard")
            )

        balance = Decimal(
            account[0] or 0
        )

        if balance < plan["investment"]:

            conn.rollback()

            flash(
                "Insufficient balance.",
                "error"
            )

            return redirect(
                url_for("dashboard")
            )

        # Deduct purchase amount.

        cur.execute("""
            UPDATE accounts
            SET deposit_account =
                deposit_account - %s
            WHERE user_id=%s
        """, (
            plan["investment"],
            user["id"]
        ))

        now = datetime.utcnow()

        # IMPORTANT:
        # The timer starts when the plan is purchased.
        # User CANNOT claim immediately.
        #
        # It is stored in PostgreSQL.
        # Visiting the page does NOT restart it.

        next_claim = now + timedelta(
            hours=24
        )

        cur.execute("""
            INSERT INTO plans (
                user_id,
                plan_id,
                plan_name,
                investment_amount,
                daily_income,
                duration,
                started_at,
                last_claim_at,
                next_claim_at,
                days_claimed,
                active
            )

            VALUES (
                %s,%s,%s,%s,%s,%s,
                %s,NULL,%s,0,TRUE
            )
        """, (
            user["id"],
            plan_id,
            plan["name"],
            plan["investment"],
            plan["daily"],
            plan["duration"],
            now,
            next_claim
        ))

        cur.execute("""
            INSERT INTO transactions (
                user_id,
                transaction_type,
                amount,
                status,
                description
            )

            VALUES (
                %s,
                'plan_purchase',
                %s,
                'successful',
                %s
            )
        """, (
            user["id"],
            plan["investment"],
            "Demo plan purchase"
        ))

        conn.commit()

    except Exception:

        conn.rollback()

        raise

    finally:

        cur.close()
        conn.close()

    flash(
        "Plan purchased successfully. Your first claim becomes available after 24 hours.",
        "success"
    )

    return redirect(
        url_for("my_plan")
    )


# ============================================================
# MY PLAN
# ============================================================

@app.route(
    "/my_plan",
    methods=["GET", "POST"]
)
def my_plan():

    user = current_user()

    if not user:

        return redirect(
            url_for("login")
        )

    plan = query_one("""
        SELECT *
        FROM plans

        WHERE user_id=%s
          AND active=TRUE

        ORDER BY id DESC

        LIMIT 1
    """, (user["id"],))

    if not plan:

        return render_template(
            "my_plan.html",
            plan=None,
            can_claim=False,
            seconds_remaining=0
        )

    now = datetime.utcnow()

    next_claim = plan["next_claim_at"]

    if next_claim is None:

        # Repair old records safely.
        next_claim = (
            plan["started_at"]
            + timedelta(hours=24)
        )

        execute("""
            UPDATE plans
            SET next_claim_at=%s
            WHERE id=%s
        """, (
            next_claim,
            plan["id"]
        ))

    can_claim = (
        now >= next_claim
    )

    seconds_remaining = max(
        0,
        int(
            (
                next_claim - now
            ).total_seconds()
        )
    )

    # --------------------------------------------------------
    # CLAIM
    # --------------------------------------------------------

    if request.method == "POST":

        conn = get_conn()
        cur = conn.cursor()

        try:

            # Lock the plan row.
            cur.execute("""
                SELECT *
                FROM plans
                WHERE id=%s
                  AND user_id=%s
                  AND active=TRUE
                FOR UPDATE
            """, (
                plan["id"],
                user["id"]
            ))

            locked_plan = cur.fetchone()

            if not locked_plan:

                conn.rollback()

                flash(
                    "Plan is no longer active.",
                    "error"
                )

                return redirect(
                    url_for("my_plan")
                )

            columns = [
                "id",
                "user_id",
                "plan_id",
                "plan_name",
                "investment_amount",
                "daily_income",
                "duration",
                "started_at",
                "last_claim_at",
                "next_claim_at",
                "days_claimed",
                "active"
            ]

            p = dict(
                zip(
                    columns,
                    locked_plan
                )
            )

            now = datetime.utcnow()

            next_claim = p["next_claim_at"]

            if next_claim is None:

                next_claim = (
                    p["started_at"]
                    + timedelta(hours=24)
                )

            if now < next_claim:

                conn.rollback()

                flash(
                    "Your next claim is not available yet.",
                    "error"
                )

                return redirect(
                    url_for("my_plan")
                )

            days_claimed = int(
                p["days_claimed"] or 0
            )

            duration = int(
                p["duration"] or 30
            )

            if days_claimed >= duration:

                cur.execute("""
                    UPDATE plans
                    SET active=FALSE
                    WHERE id=%s
                """, (
                    p["id"],
                ))

                conn.commit()

                flash(
                    "This plan has completed its cycle.",
                    "success"
                )

                return redirect(
                    url_for("my_plan")
                )

            daily_income = Decimal(
                p["daily_income"] or 0
            )

            new_days_claimed = (
                days_claimed + 1
            )

            # The next claim is based on the previous
            # scheduled claim, NOT the page visit.
            #
            # This prevents visiting the page from
            # restarting the timer.

            new_next_claim = (
                next_claim
                + timedelta(hours=24)
            )

            new_last_claim = now

            new_active = (
                new_days_claimed < duration
            )

            # Credit income.

            cur.execute("""
                UPDATE accounts
                SET
                    income_account =
                        income_account + %s,

                    withdraw_account =
                        withdraw_account + %s

                WHERE user_id=%s
            """, (
                daily_income,
                daily_income,
                user["id"]
            ))

            # Update timer.

            cur.execute("""
                UPDATE plans
                SET
                    last_claim_at=%s,
                    next_claim_at=%s,
                    days_claimed=%s,
                    active=%s

                WHERE id=%s
            """, (
                new_last_claim,
                new_next_claim,
                new_days_claimed,
                new_active,
                p["id"]
            ))

            # Transaction.

            cur.execute("""
                INSERT INTO transactions (
                    user_id,
                    transaction_type,
                    amount,
                    status,
                    description
                )

                VALUES (
                    %s,
                    'income_claim',
                    %s,
                    'successful',
                    %s
                )
            """, (
                user["id"],
                daily_income,
                "Demo daily income claim"
            ))

            conn.commit()

            flash(
                f"GHS {daily_income} demo income claimed successfully.",
                "success"
            )

            return redirect(
                url_for("my_plan")
            )

        except Exception:

            conn.rollback()

            raise

        finally:

            cur.close()
            conn.close()

    return render_template(
        "my_plan.html",
        plan=plan,
        can_claim=can_claim,
        seconds_remaining=seconds_remaining
    )


# ============================================================
# WITHDRAWAL PAGE - DEMO ONLY
# ============================================================

@app.route("/withdraw")
def withdraw():

    user = current_user()

    if not user:

        return redirect(
            url_for("login")
        )

    account = current_account(
        user["id"]
    )

    accounts = query_all("""
        SELECT *
        FROM withdrawal_accounts

        WHERE user_id=%s

        ORDER BY id DESC
    """, (user["id"],))

    return render_template(
        "withdraw.html",
        account=account,
        accounts=accounts
    )


# ============================================================
# BIND ACCOUNT
# ============================================================

@app.route(
    "/bind_account",
    methods=["GET", "POST"]
)
def bind_account():

    user = current_user()

    if not user:

        return redirect(
            url_for("login")
        )

    if request.method == "POST":

        account_name = request.form.get(
            "account_name",
            ""
        ).strip()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        network = request.form.get(
            "network",
            ""
        ).strip()

        if not account_name or not phone or not network:

            flash(
                "Please complete the account details.",
                "error"
            )

        else:

            execute("""
                INSERT INTO withdrawal_accounts (
                    user_id,
                    account_name,
                    phone,
                    network
                )

                VALUES (%s,%s,%s,%s)
            """, (
                user["id"],
                account_name,
                phone,
                network
            ))

            flash(
                "Demo withdrawal account saved.",
                "success"
            )

    accounts = query_all("""
        SELECT *
        FROM withdrawal_accounts

        WHERE user_id=%s

        ORDER BY id DESC
    """, (user["id"],))

    return render_template(
        "bind_account.html",
        accounts=accounts
    )


# ============================================================
# DEMO WITHDRAWAL REQUEST
# ============================================================

@app.route(
    "/request_withdrawal",
    methods=["POST"]
)
def request_withdrawal():

    user = current_user()

    if not user:

        return redirect(
            url_for("login")
        )

    try:

        amount = Decimal(
            request.form.get(
                "amount",
                "0"
            )
        )

    except (InvalidOperation, ValueError):

        amount = Decimal("0")

    password = request.form.get(
        "password",
        ""
    )

    account_id = request.form.get(
        "account_id"
    )

    if amount < Decimal("30"):

        flash(
            "Minimum demo withdrawal is GHS 30.",
            "error"
        )

        return redirect(
            url_for("withdraw")
        )

    stored_withdrawal_password = (
        user.get("withdraw_password_hash")
        or user.get("withdrawal_password")
    )

    if not stored_withdrawal_password:

        flash(
            "Withdrawal password is not configured.",
            "error"
        )

        return redirect(
            url_for("withdraw")
        )

    try:

        valid_password = check_password_hash(
            stored_withdrawal_password,
            password
        )

    except Exception:

        valid_password = False

    if not valid_password:

        flash(
            "Invalid withdrawal password.",
            "error"
        )

        return redirect(
            url_for("withdraw")
        )

    account = current_account(
        user["id"]
    )

    balance = Decimal(
        account["withdraw_account"] or 0
    )

    if balance < amount:

        flash(
            "Insufficient demo withdrawal balance.",
            "error"
        )

        return redirect(
            url_for("withdraw")
        )

    if account_id:

        withdrawal_account = query_one("""
            SELECT id

            FROM withdrawal_accounts

            WHERE id=%s
              AND user_id=%s
        """, (
            account_id,
            user["id"]
        ))

        if not withdrawal_account:

            flash(
                "Invalid withdrawal account.",
                "error"
            )

            return redirect(
                url_for("withdraw")
            )

    conn = get_conn()
    cur = conn.cursor()

    try:

        cur.execute("""
            UPDATE accounts

            SET withdraw_account =
                withdraw_account - %s

            WHERE user_id=%s
              AND withdraw_account >= %s
        """, (
            amount,
            user["id"],
            amount
        ))

        if cur.rowcount != 1:

            conn.rollback()

            flash(
                "Insufficient balance.",
                "error"
            )

            return redirect(
                url_for("withdraw")
            )

        cur.execute("""
            INSERT INTO withdrawal_requests (
                user_id,
                amount,
                account_id,
                status
            )

            VALUES (%s,%s,%s,'pending')
        """, (
            user["id"],
            amount,
            account_id or None
        ))

        cur.execute("""
            INSERT INTO transactions (
                user_id,
                transaction_type,
                amount,
                status,
                description
            )

            VALUES (
                %s,
                'withdrawal',
                %s,
                'pending',
                'Demo withdrawal request'
            )
        """, (
            user["id"],
            amount
        ))

        conn.commit()

    except Exception:

        conn.rollback()

        raise

    finally:

        cur.close()
        conn.close()

    flash(
        "Demo withdrawal request submitted.",
        "success"
    )

    return redirect(
        url_for("transaction_history")
    )


# ============================================================
# TRANSACTION HISTORY
# ============================================================

@app.route("/transaction_history")
def transaction_history():

    user = current_user()

    if not user:

        return redirect(
            url_for("login")
        )

    transactions = query_all("""
        SELECT *
        FROM transactions

        WHERE user_id=%s

        ORDER BY created_at DESC
    """, (user["id"],))

    return render_template(
        "transaction_history.html",
        transactions=transactions
    )


# ============================================================
# TEAM
# ============================================================

@app.route("/team")
def team():

    user = current_user()

    if not user:

        return redirect(
            url_for("login")
        )

    members = query_all("""
        SELECT
            id,
            username,
            phone,
            created_at

        FROM users

        WHERE referred_by=%s

        ORDER BY created_at DESC
    """, (
        user["referral_code"],
    ))

    account = current_account(
        user["id"]
    )

    referral_income = (
        account["referral_account"]
        if account
        else Decimal("0")
    )

    return render_template(
        "team.html",
        user=user,
        members=members,
        total_team=len(members),
        referral_income=referral_income
    )


# ============================================================
# SUPPORT
# ============================================================

@app.route("/support")
def support():

    return render_template(
        "support.html"
    )


# ============================================================
# PROFILE
# ============================================================

@app.route("/profile")
def profile():

    user = current_user()

    if not user:

        return redirect(
            url_for("login")
        )

    account = current_account(
        user["id"]
    )

    return render_template(
        "profile.html",
        user=user,
        deposit_balance=
            account["deposit_account"],
        withdraw_balance=
            account["withdraw_account"],
        income_balance=
            account["income_account"],
        referral_balance=
            account["referral_account"]
    )


# ============================================================
# ADMIN HELPERS
# ============================================================

def admin_required():

    return (
        session.get("admin_logged_in")
        is True
    )


# ============================================================
# ADMIN LOGIN
# ============================================================

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

        admin = query_one("""
            SELECT *
            FROM admins

            WHERE username=%s
        """, (username,))

        valid = False

        if admin:

            stored_hash = admin.get(
                "password_hash"
            )

            if stored_hash:

                try:

                    valid = check_password_hash(
                        stored_hash,
                        password
                    )

                except Exception:

                    valid = False

        # Compatibility fallback.
        if not valid and (
            username == ADMIN_USERNAME
            and password == ADMIN_PASSWORD
        ):

            valid = True

        if valid:

            session["admin_logged_in"] = True

            flash(
                "Administrator login successful.",
                "success"
            )

            return redirect(
                url_for("admin_dashboard")
            )

        flash(
            "Invalid administrator credentials.",
            "error"
        )

    return render_template(
        "admin_login.html"
    )


# ============================================================
# ADMIN LOGOUT
# ============================================================

@app.route("/admin/logout")
def admin_logout():

    session.pop(
        "admin_logged_in",
        None
    )

    return redirect(
        url_for("admin_login")
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin_dashboard")
@app.route("/admin/dashboard")
def admin_dashboard():

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    total_users = query_one("""
        SELECT COUNT(*) AS count
        FROM users
    """)["count"]

    pending_deposits = query_one("""
        SELECT COUNT(*) AS count

        FROM deposit_requests

        WHERE status='pending'
    """)["count"]

    pending_withdrawals = query_one("""
        SELECT COUNT(*) AS count

        FROM withdrawal_requests

        WHERE status='pending'
    """)["count"]

    return render_template(
        "admin_dashboard.html",
        total_users=total_users,
        pending_deposits=pending_deposits,
        pending_withdrawals=pending_withdrawals
    )


# ============================================================
# ADMIN USERS
# ============================================================

@app.route("/admin_users")
@app.route("/admin/users")
def admin_users():

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    users = query_all("""
        SELECT
            u.*,
            a.deposit_account,
            a.income_account,
            a.withdraw_account,
            a.referral_account

        FROM users u

        LEFT JOIN accounts a
            ON a.user_id=u.id

        ORDER BY u.id DESC
    """)

    return render_template(
        "admin_users.html",
        users=users
    )


# ============================================================
# ADMIN MANAGE USER
# ============================================================

@app.route(
    "/admin/user/<int:user_id>",
    methods=["GET", "POST"]
)
def admin_manage_user(user_id):

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    user = query_one("""
        SELECT *
        FROM users
        WHERE id=%s
    """, (user_id,))

    if not user:

        return "User not found", 404

    if request.method == "POST":

        action = request.form.get(
            "action",
            ""
        )

        try:

            amount = Decimal(
                request.form.get(
                    "amount",
                    "0"
                )
                or "0"
            )

        except (InvalidOperation, ValueError):

            flash(
                "Invalid amount.",
                "error"
            )

            return redirect(
                url_for(
                    "admin_manage_user",
                    user_id=user_id
                )
            )

        actions = {
            "add_deposit":
                ("deposit_account", 1),

            "deduct_deposit":
                ("deposit_account", -1),

            "add_withdraw":
                ("withdraw_account", 1),

            "deduct_withdraw":
                ("withdraw_account", -1),
        }

        if action in actions:

            if amount <= 0:

                flash(
                    "Amount must be greater than zero.",
                    "error"
                )

                return redirect(
                    url_for(
                        "admin_manage_user",
                        user_id=user_id
                    )
                )

            column, multiplier = actions[action]

            if multiplier == 1:

                execute(
                    f"""
                    UPDATE accounts

                    SET {column} =
                        {column} + %s

                    WHERE user_id=%s
                    """,
                    (
                        amount,
                        user_id
                    )
                )

            else:

                execute(
                    f"""
                    UPDATE accounts

                    SET {column} =
                        GREATEST(
                            0,
                            {column} - %s
                        )

                    WHERE user_id=%s
                    """,
                    (
                        amount,
                        user_id
                    )
                )

            flash(
                "User balance updated.",
                "success"
            )

            return redirect(
                url_for(
                    "admin_manage_user",
                    user_id=user_id
                )
            )

        flash(
            "Unknown admin action.",
            "error"
        )

        return redirect(
            url_for(
                "admin_manage_user",
                user_id=user_id
            )
        )

    account = current_account(
        user_id
    )

    return render_template(
        "admin_manage_user.html",
        user=user,
        account=account
    )


# ============================================================
# ADMIN DEPOSITS
# ============================================================

@app.route("/admin_deposit")
@app.route("/admin/deposits")
def admin_deposits():

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    deposits = query_all("""
        SELECT
            d.*,

            u.username,
            u.fullname,
            u.phone

        FROM deposit_requests d

        JOIN users u
            ON u.id=d.user_id

        ORDER BY d.created_at DESC
    """)

    return render_template(
        "admin_deposit.html",
        deposits=deposits
    )


# ============================================================
# ADMIN DEPOSIT APPROVE / REJECT
# ============================================================

@app.route(
    "/admin/deposit/<int:deposit_id>/<action>",
    methods=["POST"]
)
def admin_deposit_action(
    deposit_id,
    action
):

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    if action not in (
        "approve",
        "reject"
    ):

        flash(
            "Invalid deposit action.",
            "error"
        )

        return redirect(
            url_for("admin_deposits")
        )

    conn = get_conn()
    cur = conn.cursor()

    try:

        cur.execute("""
            SELECT *
            FROM deposit_requests

            WHERE id=%s

            FOR UPDATE
        """, (deposit_id,))

        row = cur.fetchone()

        if not row:

            conn.rollback()

            flash(
                "Deposit request not found.",
                "error"
            )

            return redirect(
                url_for("admin_deposits")
            )

        columns = [
            "id",
            "user_id",
            "amount",
            "payment_number",
            "reference",
            "screenshot",
            "screenshot_filename",
            "status",
            "created_at",
            "reviewed_at"
        ]

        deposit = dict(
            zip(
                columns,
                row
            )
        )

        if deposit["status"] != "pending":

            conn.rollback()

            flash(
                "Deposit request is no longer pending.",
                "error"
            )

            return redirect(
                url_for("admin_deposits")
            )

        if action == "approve":

            cur.execute("""
                UPDATE accounts

                SET deposit_account =
                    deposit_account + %s

                WHERE user_id=%s
            """, (
                deposit["amount"],
                deposit["user_id"]
            ))

            cur.execute("""
                UPDATE deposit_requests

                SET
                    status='approved',
                    reviewed_at=CURRENT_TIMESTAMP

                WHERE id=%s
            """, (
                deposit_id,
            ))

            cur.execute("""
                UPDATE transactions

                SET status='successful'

                WHERE user_id=%s
                  AND transaction_type='deposit'
                  AND amount=%s
                  AND status='pending'
            """, (
                deposit["user_id"],
                deposit["amount"]
            ))

        else:

            cur.execute("""
                UPDATE deposit_requests

                SET
                    status='rejected',
                    reviewed_at=CURRENT_TIMESTAMP

                WHERE id=%s
            """, (
                deposit_id,
            ))

            cur.execute("""
                UPDATE transactions

                SET status='failed'

                WHERE user_id=%s
                  AND transaction_type='deposit'
                  AND amount=%s
                  AND status='pending'
            """, (
                deposit["user_id"],
                deposit["amount"]
            ))

        conn.commit()

    except Exception:

        conn.rollback()

        raise

    finally:

        cur.close()
        conn.close()

    flash(
        f"Deposit {action}d successfully.",
        "success"
    )

    return redirect(
        url_for("admin_deposits")
    )


# ============================================================
# ADMIN WITHDRAWALS
# ============================================================

@app.route("/admin_withdraw")
@app.route("/admin/withdrawals")
def admin_withdrawals():

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    withdrawals = query_all("""
        SELECT
