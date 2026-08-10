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
    RealDictCursor = None


app = Flask(__name__)
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-key"
)

DATABASE_URL = os.environ.get("DATABASE_URL")

# ============================================================
# DEMO CONFIGURATION
# ============================================================

# This application is a simulated/demo dashboard.
# It does not process real-money investments or withdrawals.

DEMO_DEPOSIT_NUMBER = os.environ.get(
    "DEMO_DEPOSIT_NUMBER",
    "0000000000"
)

MIN_DEPOSIT = Decimal("45")
MIN_WITHDRAWAL = Decimal("30")

ADMIN_USERNAME = os.environ.get(
    "ADMIN_USERNAME",
    "Williams"
)

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "Williams12"
)


# ============================================================
# PLANS
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
        raise RuntimeError("psycopg2 is not installed.")

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

        # ------------------------------------------------------
        # USERS
        # ------------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(120) UNIQUE NOT NULL,
                fullname VARCHAR(200) DEFAULT '',
                phone VARCHAR(60) UNIQUE NOT NULL,
                password_hash TEXT,
                withdraw_password_hash TEXT,
                referral_code VARCHAR(150) UNIQUE,
                referred_by VARCHAR(150),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Fix old database installations where columns were too short.
        cur.execute("""
            ALTER TABLE users
            ALTER COLUMN username TYPE VARCHAR(120)
        """)

        cur.execute("""
            ALTER TABLE users
            ALTER COLUMN fullname TYPE VARCHAR(200)
        """)

        cur.execute("""
            ALTER TABLE users
            ALTER COLUMN phone TYPE VARCHAR(60)
        """)

        cur.execute("""
            ALTER TABLE users
            ALTER COLUMN referral_code TYPE VARCHAR(150)
        """)

        cur.execute("""
            ALTER TABLE users
            ALTER COLUMN referred_by TYPE VARCHAR(150)
        """)

        cur.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS password TEXT
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
            ADD COLUMN IF NOT EXISTS referral_code VARCHAR(150)
        """)

        cur.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS referred_by VARCHAR(150)
        """)

        cur.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS created_at
            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        """)

        # Migrate old plain password column if present.
        cur.execute("""
            UPDATE users
            SET password_hash = password
            WHERE password_hash IS NULL
              AND password IS NOT NULL
        """)


        # ------------------------------------------------------
        # ACCOUNTS
        # ------------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                user_id INTEGER PRIMARY KEY
                    REFERENCES users(id) ON DELETE CASCADE,

                deposit_account NUMERIC(14,2)
                    NOT NULL DEFAULT 5.00,

                income_account NUMERIC(14,2)
                    NOT NULL DEFAULT 0,

                referral_account NUMERIC(14,2)
                    NOT NULL DEFAULT 0,

                withdraw_account NUMERIC(14,2)
                    NOT NULL DEFAULT 0
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


        # ------------------------------------------------------
        # PLANS
        # ------------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS plans (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                plan_id INTEGER NOT NULL,

                plan_name VARCHAR(150) NOT NULL,

                investment_amount NUMERIC(14,2)
                    NOT NULL,

                daily_income NUMERIC(14,2)
                    NOT NULL,

                duration INTEGER NOT NULL,

                started_at TIMESTAMP
                    NOT NULL DEFAULT CURRENT_TIMESTAMP,

                last_claim_at TIMESTAMP
                    NOT NULL DEFAULT CURRENT_TIMESTAMP,

                active BOOLEAN
                    NOT NULL DEFAULT TRUE
            )
        """)

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
            ADD COLUMN IF NOT EXISTS plan_name VARCHAR(150)
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
            ADD COLUMN IF NOT EXISTS started_at
            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        """)

        cur.execute("""
            ALTER TABLE plans
            ADD COLUMN IF NOT EXISTS last_claim_at
            TIMESTAMP
        """)

        cur.execute("""
            ALTER TABLE plans
            ADD COLUMN IF NOT EXISTS active
            BOOLEAN DEFAULT TRUE
        """)

        # IMPORTANT:
        # Old plans with NULL last_claim_at get their purchase/start
        # time as the starting point instead of allowing immediate claim.
        cur.execute("""
            UPDATE plans
            SET last_claim_at = COALESCE(
                started_at,
                CURRENT_TIMESTAMP
            )
            WHERE last_claim_at IS NULL
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_plans_user_id
            ON plans(user_id)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_plans_active
            ON plans(user_id, active)
        """)


        # ------------------------------------------------------
        # TRANSACTIONS
        # ------------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                transaction_type VARCHAR(80) NOT NULL,

                amount NUMERIC(14,2) NOT NULL,

                status VARCHAR(50) NOT NULL,

                reference VARCHAR(200),

                description TEXT,

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            ALTER TABLE transactions
            ALTER COLUMN transaction_type TYPE VARCHAR(80)
        """)

        cur.execute("""
            ALTER TABLE transactions
            ALTER COLUMN status TYPE VARCHAR(50)
        """)

        cur.execute("""
            ALTER TABLE transactions
            ALTER COLUMN reference TYPE VARCHAR(200)
        """)


        # ------------------------------------------------------
        # WITHDRAWAL ACCOUNTS
        # ------------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS withdrawal_accounts (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                account_name VARCHAR(200) NOT NULL,

                phone VARCHAR(60) NOT NULL,

                network VARCHAR(80) NOT NULL,

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
            )
        """)


        # ------------------------------------------------------
        # DEPOSIT REQUESTS
        # ------------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS deposit_requests (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                amount NUMERIC(14,2) NOT NULL,

                payment_number VARCHAR(100),

                sender_phone VARCHAR(60),

                reference VARCHAR(200),

                screenshot TEXT,

                status VARCHAR(50)
                    NOT NULL DEFAULT 'pending',

                admin_note TEXT,

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP,

                processed_at TIMESTAMP
            )
        """)

        cur.execute("""
            ALTER TABLE deposit_requests
            ADD COLUMN IF NOT EXISTS payment_number VARCHAR(100)
        """)

        cur.execute("""
            ALTER TABLE deposit_requests
            ADD COLUMN IF NOT EXISTS sender_phone VARCHAR(60)
        """)

        cur.execute("""
            ALTER TABLE deposit_requests
            ADD COLUMN IF NOT EXISTS reference VARCHAR(200)
        """)

        cur.execute("""
            ALTER TABLE deposit_requests
            ADD COLUMN IF NOT EXISTS screenshot TEXT
        """)

        cur.execute("""
            ALTER TABLE deposit_requests
            ADD COLUMN IF NOT EXISTS admin_note TEXT
        """)

        cur.execute("""
            ALTER TABLE deposit_requests
            ADD COLUMN IF NOT EXISTS processed_at TIMESTAMP
        """)


        # ------------------------------------------------------
        # WITHDRAWAL REQUESTS
        # ------------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS withdrawal_requests (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                amount NUMERIC(14,2) NOT NULL,

                account_id INTEGER
                    REFERENCES withdrawal_accounts(id)
                    ON DELETE SET NULL,

                status VARCHAR(50)
                    NOT NULL DEFAULT 'pending',

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
            )
        """)


        # ------------------------------------------------------
        # ADMINS
        # ------------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,

                username VARCHAR(120)
                    UNIQUE NOT NULL,

                password_hash TEXT
            )
        """)

        cur.execute("""
            ALTER TABLE admins
            ALTER COLUMN username TYPE VARCHAR(120)
        """)

        cur.execute("""
            ALTER TABLE admins
            ADD COLUMN IF NOT EXISTS password TEXT
        """)

        cur.execute("""
            ALTER TABLE admins
            ADD COLUMN IF NOT EXISTS password_hash TEXT
        """)


        # ------------------------------------------------------
        # REFERRAL CODES
        # ------------------------------------------------------

        cur.execute("""
            SELECT id
            FROM users
            WHERE referral_code IS NULL
               OR referral_code=''
        """)

        missing_codes = cur.fetchall()

        for row in missing_codes:
            user_id = row[0]

            referral_code = (
                "ZEN"
                + datetime.utcnow().strftime("%y%m%d%H%M%S")
                + os.urandom(4).hex()
            )

            cur.execute("""
                UPDATE users
                SET referral_code=%s
                WHERE id=%s
            """, (
                referral_code,
                user_id
            ))


        # ------------------------------------------------------
        # ACCOUNT ROWS
        # ------------------------------------------------------

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
                ON a.user_id=u.id
            WHERE a.user_id IS NULL
        """)


        # ------------------------------------------------------
        # DEFAULT ADMIN
        # ------------------------------------------------------

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
                password_hash=EXCLUDED.password_hash
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
    """, (
        user_id,
    ))


def current_account(user_id):

    return query_one("""
        SELECT *
        FROM accounts
        WHERE user_id=%s
    """, (
        user_id,
    ))


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

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    invite_code = (
        request.args.get(
            "ref",
            ""
        ).strip()
        or request.form.get(
            "referred_by",
            ""
        ).strip()
    )

    referred_user = None

    if invite_code:

        referred_user = query_one("""
            SELECT
                id,
                username,
                referral_code
            FROM users
            WHERE referral_code=%s
        """, (
            invite_code,
        ))

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

        existing_user = query_one("""
            SELECT id
            FROM users
            WHERE username=%s
               OR phone=%s
        """, (
            username,
            phone
        ))

        if existing_user:

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
            + datetime.utcnow().strftime(
                "%y%m%d%H%M%S"
            )
            + os.urandom(4).hex()
        )

        user = execute("""
            INSERT INTO users (
                username,
                fullname,
                phone,
                password_hash,
                withdraw_password_hash,
                referral_code,
                referred_by
            )
            VALUES (
                %s,%s,%s,%s,%s,%s,%s
            )
            RETURNING id
        """, (
            username,
            fullname,
            phone,
            generate_password_hash(password),
            generate_password_hash(
                withdraw_password
            ),
            referral_code,
            (
                referred_user["referral_code"]
                if referred_user
                else None
            )
        ), fetchone=True)

        execute("""
            INSERT INTO accounts (
                user_id,
                deposit_account,
                income_account,
                referral_account,
                withdraw_account
            )
            VALUES (
                %s,5.00,0,0,0
            )
        """, (
            user["id"],
        ))

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

        user = query_one("""
            SELECT *
            FROM users
            WHERE phone=%s
        """, (
            phone,
        ))

        if not user:

            flash(
                "Invalid phone number or password.",
                "error"
            )

            return render_template(
                "login.html"
            )

        stored_password = user.get(
            "password_hash"
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
# DEPOSIT
# ============================================================

@app.route("/deposit")
def deposit():

    user = current_user()

    if not user:
        return redirect(
            url_for("login")
        )

    return render_template(
        "deposit.html",
        minimum_deposit=MIN_DEPOSIT,
        payment_number=DEMO_DEPOSIT_NUMBER
    )


@app.route(
    "/deposit/details",
    methods=["POST"]
)
def deposit_details():

    user = current_user()

    if not user:
        return redirect(
            url_for("login")
        )

    raw_amount = request.form.get(
        "amount",
        "0"
    ).strip()

    try:

        amount = Decimal(raw_amount)

    except (InvalidOperation, ValueError):

        flash(
            "Please enter a valid amount.",
            "error"
        )

        return redirect(
            url_for("deposit")
        )

    if amount < MIN_DEPOSIT:

        flash(
            "Minimum demo deposit is GHS 45.",
            "error"
        )

        return redirect(
            url_for("deposit")
        )

    return render_template(
        "deposit_confirm.html",
        amount=amount,
        payment_number=DEMO_DEPOSIT_NUMBER
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

    raw_amount = request.form.get(
        "amount",
        "0"
    ).strip()

    sender_phone = request.form.get(
        "sender_phone",
        ""
    ).strip()

    reference = request.form.get(
        "reference",
        ""
    ).strip()

    screenshot = request.form.get(
        "screenshot",
        ""
    ).strip()

    try:

        amount = Decimal(raw_amount)

    except (InvalidOperation, ValueError):

        flash(
            "Invalid deposit amount.",
            "error"
        )

        return redirect(
            url_for("deposit")
        )

    if amount < MIN_DEPOSIT:

        flash(
            "Minimum demo deposit is GHS 45.",
            "error"
        )

        return redirect(
            url_for("deposit")
        )

    if not sender_phone:

        flash(
            "Please enter the sender phone number.",
            "error"
        )

        return redirect(
            url_for("deposit")
        )

    if not reference:

        flash(
            "Please enter the transaction reference.",
            "error"
        )

        return redirect(
            url_for("deposit")
        )

    # Screenshot field is stored as text for now.
    # If your HTML uses an actual file upload, this can later
    # be changed to secure file storage.

    execute("""
        INSERT INTO deposit_requests (
            user_id,
            amount,
            payment_number,
            sender_phone,
            reference,
            screenshot,
            status
        )
        VALUES (
            %s,%s,%s,%s,%s,%s,'pending'
        )
    """, (
        user["id"],
        amount,
        DEMO_DEPOSIT_NUMBER,
        sender_phone,
        reference,
        screenshot
    ))

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
            'Demo manual deposit request'
        )
    """, (
        user["id"],
        amount,
        reference
    ))

    flash(
        "Deposit request submitted. Please wait for admin review.",
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

    db_plan = {
        "id": plan_id,
        "plan_name": plan["name"],
        "investment_amount":
            plan["investment"],
        "daily_income":
            plan["daily"],
        "duration":
            plan["duration"],
    }

    return render_template(
        "confirm_plan.html",
        user=user,
        account=account,
        plan=db_plan
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

        # Lock/check the balance during purchase.
        cur.execute("""
            UPDATE accounts
            SET deposit_account =
                deposit_account - %s
            WHERE user_id=%s
              AND deposit_account >= %s
        """, (
            plan["investment"],
            user["id"],
            plan["investment"]
        ))

        if cur.rowcount != 1:

            conn.rollback()

            flash(
                "Insufficient balance.",
                "error"
            )

            return redirect(
                url_for("dashboard")
            )

        purchase_time = datetime.utcnow()

        # IMPORTANT:
        # last_claim_at is set immediately to purchase_time.
        #
        # Therefore:
        # purchase at 15:00
        # first claim available at 15:00 next day
        #
        # Visiting /my_plan does NOT modify this value.

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
                active
            )
            VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,TRUE
            )
        """, (
            user["id"],
            plan_id,
            plan["name"],
            plan["investment"],
            plan["daily"],
            plan["duration"],
            purchase_time,
            purchase_time
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
            "Demo plan purchase: "
            + plan["name"]
        ))

        conn.commit()

    except Exception:

        conn.rollback()
        raise

    finally:

        cur.close()
        conn.close()

    flash(
        "Plan purchased successfully. "
        "Your first claim will be available after 24 hours.",
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
    """, (
        user["id"],
    ))

    can_claim = False
    next_claim_at = None
    seconds_remaining = 0

    if plan:

        # ------------------------------------------------------
        # NEVER CHANGE last_claim_at when page is visited.
        # ------------------------------------------------------

        last_claim = plan["last_claim_at"]

        if last_claim is None:

            # Safety migration for an old record.
            last_claim = (
                plan["started_at"]
                or datetime.utcnow()
            )

        next_claim_at = (
            last_claim
            + timedelta(hours=24)
        )

        now = datetime.utcnow()

        if now >= next_claim_at:

            can_claim = True
            seconds_remaining = 0

        else:

            can_claim = False

            seconds_remaining = int(
                (
                    next_claim_at - now
                ).total_seconds()
            )

        # ------------------------------------------------------
        # CLAIM
        # ------------------------------------------------------

        if request.method == "POST":

            if not can_claim:

                flash(
                    "Your next claim is not available yet.",
                    "error"
                )

                return redirect(
                    url_for("my_plan")
                )

            conn = get_conn()
            cur = conn.cursor()

            try:

                # Re-check the timer inside the transaction.
                cur.execute("""
                    SELECT
                        id,
                        daily_income,
                        last_claim_at,
                        active
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
                        "Plan not found.",
                        "error"
                    )

                    return redirect(
                        url_for("my_plan")
                    )

                locked_last_claim = (
                    locked_plan[2]
                )

                if locked_last_claim is None:

                    locked_last_claim = (
                        plan["started_at"]
                        or datetime.utcnow()
                    )

                locked_next_claim = (
                    locked_last_claim
                    + timedelta(hours=24)
                )

                now = datetime.utcnow()

                if now < locked_next_claim:

                    conn.rollback()

                    flash(
                        "Your 24-hour claim timer is still running.",
                        "error"
                    )

                    return redirect(
                        url_for("my_plan")
                    )

                daily_income = Decimal(
                    locked_plan[1]
                )

                # Credit income.
                cur.execute("""
                    UPDATE accounts
                    SET income_account =
                            income_account + %s,
                        withdraw_account =
                            withdraw_account + %s
                    WHERE user_id=%s
                """, (
                    daily_income,
                    daily_income,
                    user["id"]
                ))

                # Reset the timer ONLY after a successful claim.
                claim_time = datetime.utcnow()

                cur.execute("""
                    UPDATE plans
                    SET last_claim_at=%s
                    WHERE id=%s
                """, (
                    claim_time,
                    plan["id"]
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
                        'income_claim',
                        %s,
                        'successful',
                        'Demo daily income claim'
                    )
                """, (
                    user["id"],
                    daily_income
                ))

                conn.commit()

            except Exception:

                conn.rollback()
                raise

            finally:

                cur.close()
                conn.close()

            flash(
                "Daily demo income claimed successfully. "
                "Your next claim will be available after 24 hours.",
                "success"
            )

            return redirect(
                url_for("my_plan")
            )

    return render_template(
        "my_plan.html",
        plan=plan,
        can_claim=can_claim,
        next_claim_at=next_claim_at,
        seconds_remaining=seconds_remaining
    )


# ============================================================
# WITHDRAW
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
    """, (
        user["id"],
    ))

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

        if (
            not account_name
            or not phone
            or not network
        ):

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
                "Withdrawal account saved.",
                "success"
            )

    accounts = query_all("""
        SELECT *
        FROM withdrawal_accounts
        WHERE user_id=%s
        ORDER BY id DESC
    """, (
        user["id"],
    ))

    return render_template(
        "bind_account.html",
        accounts=accounts
    )


# ============================================================
# WITHDRAWAL REQUEST
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

    if amount < MIN_WITHDRAWAL:

        flash(
            "Minimum demo withdrawal is GHS 30.",
            "error"
        )

        return redirect(
            url_for("withdraw")
        )

    if not user["withdraw_password_hash"]:

        flash(
            "Withdrawal password is not configured.",
            "error"
        )

        return redirect(
            url_for("withdraw")
        )

    try:

        valid_password = check_password_hash(
            user["withdraw_password_hash"],
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
            "Insufficient withdrawal balance.",
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
                "Insufficient withdrawal balance.",
                "error"
            )

            return redirect(
                url_for("withdraw")
            )

        cur.execute("""
            INSERT INTO withdrawal_requests (
                user_id,
                amount,
                account_id
            )
            VALUES (%s,%s,%s)
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
        "Withdrawal request submitted for review.",
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
    """, (
        user["id"],
    ))

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
        else 0
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
# ADMIN AUTH
# ============================================================

def admin_required():

    return (
        session.get(
            "admin_logged_in"
        ) is True
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
        """, (
            username,
        ))

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
            a.referral_account,
            a.withdraw_account
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
    """, (
        user_id,
    ))

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

            column, multiplier = actions[
                action
            ]

            if multiplier == 1:

                execute(
                    f"""
                    UPDATE accounts
                    SET {column}={column}+%s
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
                    SET {column}=GREATEST(
                        0,
                        {column}-%s
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
            u.phone AS user_phone,

            d.sender_phone,
            d.payment_number,
            d.reference,
            d.screenshot,

            d.status,
            d.created_at

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

    deposit = query_one("""
        SELECT *
        FROM deposit_requests
        WHERE id=%s
    """, (
        deposit_id,
    ))

    if not deposit:

        flash(
            "Deposit request not found.",
            "error"
        )

        return redirect(
            url_for("admin_deposits")
        )

    if deposit["status"] != "pending":

        flash(
            "This deposit has already been processed.",
            "error"
        )

        return redirect(
            url_for("admin_deposits")
        )

    admin_note = request.form.get(
        "admin_note",
        ""
    ).strip()

    conn = get_conn()
    cur = conn.cursor()

    try:

        if action == "approve":

            # Credit the user's demo deposit balance.
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
                    admin_note=%s,
                    processed_at=CURRENT_TIMESTAMP
                WHERE id=%s
            """, (
                admin_note,
                deposit_id
            ))

            cur.execute("""
                UPDATE transactions
                SET status='successful'
                WHERE user_id=%s
                  AND reference=%s
                  AND transaction_type='deposit'
                  AND status='pending'
            """, (
                deposit["user_id"],
                deposit["reference"]
            ))

        else:

            cur.execute("""
                UPDATE deposit_requests
                SET
                    status='rejected',
                    admin_note=%s,
                    processed_at=CURRENT_TIMESTAMP
                WHERE id=%s
            """, (
                admin_note,
                deposit_id
            ))

            cur.execute("""
                UPDATE transactions
                SET status='failed'
                WHERE user_id=%s
                  AND reference=%s
                  AND transaction_type='deposit'
                  AND status='pending'
            """, (
                deposit["user_id"],
                deposit["reference"]
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
            w.*,
            u.username,
            u.phone,

            wa.account_name,
            wa.phone AS account_phone,
            wa.network

        FROM withdrawal_requests w

        JOIN users u
            ON u.id=w.user_id

        LEFT JOIN withdrawal_accounts wa
            ON wa.id=w.account_id

        ORDER BY w.created_at DESC
    """)

    return render_template(
        "admin_withdraw.html",
        withdrawals=withdrawals
    )


# ============================================================
# ADMIN WITHDRAW ACTION
# ============================================================

@app.route(
    "/admin/withdraw/<int:withdrawal_id>/<action>",
    methods=["POST"]
)
def admin_withdraw_action(
    withdrawal_id,
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
            "Invalid withdrawal action.",
            "error"
        )

        return redirect(
            url_for("admin_withdrawals")
        )

    withdrawal = query_one("""
        SELECT *
        FROM withdrawal_requests
        WHERE id=%s
    """, (
        withdrawal_id,
    ))

    if not withdrawal:

        flash(
            "Withdrawal not found.",
            "error"
        )

        return redirect(
            url_for("admin_withdrawals")
        )

    if withdrawal["status"] != "pending":

        flash(
            "Withdrawal is no longer pending.",
            "error"
        )

        return redirect(
            url_for("admin_withdrawals")
        )

    conn = get_conn()
    cur = conn.cursor()

    try:

        if action == "approve":

            cur.execute("""
                UPDATE withdrawal_requests
                SET status='approved'
                WHERE id=%s
            """, (
                withdrawal_id,
            ))

            cur.execute("""
                UPDATE transactions
                SET status='successful'
                WHERE user_id=%s
                  AND transaction_type='withdrawal'
                  AND amount=%s
                  AND status='pending'
            """, (
                withdrawal["user_id"],
                withdrawal["amount"]
            ))

        else:

            # Return the demo balance if rejected.
            cur.execute("""
                UPDATE accounts
                SET withdraw_account =
                    withdraw_account + %s
                WHERE user_id=%s
            """, (
                withdrawal["amount"],
                withdrawal["user_id"]
            ))

            cur.execute("""
                UPDATE withdrawal_requests
                SET status='rejected'
                WHERE id=%s
            """, (
                withdrawal_id,
            ))

            cur.execute("""
                UPDATE transactions
                SET status='failed'
                WHERE user_id=%s
                  AND transaction_type='withdrawal'
                  AND amount=%s
                  AND status='pending'
            """, (
                withdrawal["user_id"],
                withdrawal["amount"]
            ))

        conn.commit()

    except Exception:

        conn.rollback()
        raise

    finally:

        cur.close()
        conn.close()

    flash(
        f"Withdrawal {action}d successfully.",
        "success"
    )

    return redirect(
        url_for("admin_withdrawals")
    )


# ============================================================
# ADMIN BOUND ACCOUNTS
# ============================================================

@app.route("/admin_bind_accounts")
@app.route("/admin/bind_accounts")
def admin_bind_accounts():

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    accounts = query_all("""
        SELECT
            wa.*,
            u.username,
            u.phone AS user_phone
        FROM withdrawal_accounts wa
        JOIN users u
            ON u.id=wa.user_id
        ORDER BY wa.created_at DESC
    """)

    return render_template(
        "admin_bind_accounts.html",
        accounts=accounts
    )


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):

    return "Page not found", 404


@app.errorhandler(500)
def server_error(error):

    return "An internal server error occurred.", 500


# ============================================================
# DATABASE STARTUP
# ============================================================

with app.app_context():
    init_db()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "5000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
