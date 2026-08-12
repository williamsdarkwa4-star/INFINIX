import os
import uuid
from io import BytesIO
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    send_file,
    abort,
)

from werkzeug.security import generate_password_hash, check_password_hash

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except Exception:
    psycopg2 = None
    RealDictCursor = None


# ============================================================
# CONFIGURATION
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-key"
)

DATABASE_URL = os.environ.get("DATABASE_URL")

ADMIN_USERNAME = os.environ.get(
    "ADMIN_USERNAME",
    "Williams"
)

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "Williams12"
)

app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024


# ============================================================
# PLATFORM SETTINGS
# ============================================================

MIN_DEPOSIT = Decimal("45.00")
MIN_WITHDRAWAL = Decimal("30.00")

STARTING_DEPOSIT_BALANCE = Decimal("5.00")

CLAIM_INTERVAL_HOURS = 24


# ============================================================
# REFERRAL COMMISSION
#
# Level 1 = 20%
# Level 2 = 3%
# Level 3 = 1%
# ============================================================

REFERRAL_PERCENTS = [
    Decimal("0.20"),
    Decimal("0.03"),
    Decimal("0.01"),
]


# ============================================================
# ZENITH PLANS
# ============================================================

PLANS = {
    1: {
        "name": "Zenith 1",
        "investment": Decimal("50.00"),
        "daily": Decimal("5.00"),
        "duration": 180,
    },

    2: {
        "name": "Zenith 2",
        "investment": Decimal("100.00"),
        "daily": Decimal("20.00"),
        "duration": 180,
    },

    3: {
        "name": "Zenith 3",
        "investment": Decimal("200.00"),
        "daily": Decimal("40.00"),
        "duration": 180,
    },

    4: {
        "name": "Zenith 4",
        "investment": Decimal("300.00"),
        "daily": Decimal("65.00"),
        "duration": 180,
    },

    5: {
        "name": "Zenith 5",
        "investment": Decimal("500.00"),
        "daily": Decimal("100.00"),
        "duration": 180,
    },

    6: {
        "name": "Zenith 6",
        "investment": Decimal("600.00"),
        "daily": Decimal("200.00"),
        "duration": 180,
    },

    7: {
        "name": "Zenith 7",
        "investment": Decimal("1000.00"),
        "daily": Decimal("360.00"),
        "duration": 180,
    },
}


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def utcnow():
    """
    Return current UTC time.
    """
    return datetime.now(timezone.utc)


def money(value):
    """
    Safely convert a value to Decimal with 2 decimal places.
    """
    if value is None:
        return Decimal("0.00")

    try:
        return Decimal(str(value)).quantize(
            Decimal("0.01")
        )
    except Exception:
        return Decimal("0.00")


def parse_amount(value):
    """
    Safely parse a positive monetary amount.
    """
    if value is None:
        return None

    try:
        amount = Decimal(str(value).strip())
    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ):
        return None

    if not amount.is_finite() or amount <= 0:
        return None

    return amount.quantize(Decimal("0.01"))


def generate_referral_code():
    """
    Generate a unique referral code.
    """
    return (
        "ZEN"
        + uuid.uuid4().hex[:12].upper()
    )


def generate_reference(prefix):
    """
    Generate a unique transaction/reference number.
    """
    return (
        f"{prefix}-"
        f"{uuid.uuid4().hex[:12].upper()}"
    )


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_conn():
    """
    Create a PostgreSQL database connection.
    """

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not configured."
        )

    if psycopg2 is None:
        raise RuntimeError(
            "psycopg2 is required."
        )

    return psycopg2.connect(
        DATABASE_URL,
        sslmode="require"
    )


# ============================================================
# DATABASE HELPERS
# ============================================================

def query_one(sql, params=()):
    """
    Execute a SELECT query and return one row.
    """

    conn = get_conn()

    try:
        cur = conn.cursor(
            cursor_factory=RealDictCursor
        )

        try:
            cur.execute(sql, params)
            return cur.fetchone()

        finally:
            cur.close()

    finally:
        conn.close()


def query_all(sql, params=()):
    """
    Execute a SELECT query and return all rows.
    """

    conn = get_conn()

    try:
        cur = conn.cursor(
            cursor_factory=RealDictCursor
        )

        try:
            cur.execute(sql, params)
            return cur.fetchall()

        finally:
            cur.close()

    finally:
        conn.close()


def execute(sql, params=()):
    """
    Execute INSERT/UPDATE/DELETE query.
    """

    conn = get_conn()

    try:
        cur = conn.cursor()

        try:
            cur.execute(sql, params)
            conn.commit()
            return True

        except Exception:
            conn.rollback()
            raise

        finally:
            cur.close()

    finally:
        conn.close()


# ============================================================
# ACCOUNT HELPER
# ============================================================

def ensure_account(
    cur,
    user_id,
    starting_balance=Decimal("0.00")
):
    """
    Ensure a user has an account row.

    This function expects an existing database cursor so
    that the operation remains inside the current transaction.
    """

    cur.execute(
        """
        SELECT user_id
        FROM accounts
        WHERE user_id=%s
        FOR UPDATE
        """,
        (user_id,)
    )

    if cur.fetchone():
        return

    cur.execute(
        """
        INSERT INTO accounts (
            user_id,
            deposit_account,
            income_account,
            referral_account,
            withdraw_account
        )
        VALUES (
            %s,
            %s,
            0,
            0,
            0
        )
        ON CONFLICT (user_id)
        DO NOTHING
        """,
        (
            user_id,
            starting_balance
        )
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

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,

                username VARCHAR(120),

                fullname VARCHAR(200)
                    DEFAULT '',

                phone VARCHAR(50),

                password_hash TEXT,

                withdraw_password_hash TEXT,

                password TEXT,

                withdraw_password TEXT,

                referral_code VARCHAR(120),

                referred_by VARCHAR(120),

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


        # ----------------------------------------------------
        # ACCOUNTS
        # ----------------------------------------------------

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                user_id INTEGER PRIMARY KEY
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                deposit_account NUMERIC(14,2)
                    NOT NULL
                    DEFAULT 5.00,

                income_account NUMERIC(14,2)
                    NOT NULL
                    DEFAULT 0,

                referral_account NUMERIC(14,2)
                    NOT NULL
                    DEFAULT 0,

                withdraw_account NUMERIC(14,2)
                    NOT NULL
                    DEFAULT 0
            )
            """
        )


        # ----------------------------------------------------
        # PLANS
        # ----------------------------------------------------

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS plans (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                plan_id INTEGER NOT NULL,

                plan_name VARCHAR(120)
                    NOT NULL,

                investment_amount NUMERIC(14,2)
                    NOT NULL,

                daily_income NUMERIC(14,2)
                    NOT NULL,

                duration INTEGER
                    NOT NULL,

                started_at TIMESTAMP
                    NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,

                last_claim_at TIMESTAMP,

                active BOOLEAN
                    NOT NULL
                    DEFAULT TRUE
            )
            """
        )


        # ----------------------------------------------------
        # TRANSACTIONS
        # ----------------------------------------------------

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                transaction_type VARCHAR(60)
                    NOT NULL,

                amount NUMERIC(14,2)
                    NOT NULL,

                status VARCHAR(40)
                    NOT NULL,

                reference VARCHAR(200),

                description TEXT,

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


        # ----------------------------------------------------
        # WITHDRAWAL ACCOUNTS
        # ----------------------------------------------------

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS withdrawal_accounts (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                account_name VARCHAR(150)
                    NOT NULL,

                phone VARCHAR(50)
                    NOT NULL,

                network VARCHAR(60)
                    NOT NULL,

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


        # ----------------------------------------------------
        # DEPOSIT REQUESTS
        # ----------------------------------------------------

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS deposit_requests (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                amount NUMERIC(14,2)
                    NOT NULL,

                payment_number VARCHAR(80),

                screenshot TEXT,

                screenshot_data BYTEA,

                screenshot_mime VARCHAR(100),

                reference VARCHAR(200),

                status VARCHAR(40)
                    NOT NULL
                    DEFAULT 'pending',

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


        # ----------------------------------------------------
        # WITHDRAWAL REQUESTS
        # ----------------------------------------------------

        cur.execute(
            """
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

                status VARCHAR(40)
                    NOT NULL
                    DEFAULT 'pending',

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


        # ----------------------------------------------------
        # ADMINS
        # ----------------------------------------------------

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,

                username VARCHAR(120)
                    UNIQUE
                    NOT NULL,

                password_hash TEXT
                    NOT NULL
            )
            """
        )


        # ----------------------------------------------------
        # INVITES
        # ----------------------------------------------------

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS invites (
                id SERIAL PRIMARY KEY,

                token VARCHAR(120)
                    UNIQUE
                    NOT NULL,

                owner_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                amount NUMERIC(14,2)
                    NOT NULL
                    DEFAULT 0,

                approved BOOLEAN
                    NOT NULL
                    DEFAULT FALSE,

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


        # ----------------------------------------------------
        # MAKE SURE OLD USERS HAVE REFERRAL CODES
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT id
            FROM users
            WHERE referral_code IS NULL
               OR referral_code=''
            """
        )

        rows = cur.fetchall()

        for row in rows:

            cur.execute(
                """
                UPDATE users
                SET referral_code=%s
                WHERE id=%s
                """,
                (
                    generate_referral_code(),
                    row[0]
                )
            )


        # ----------------------------------------------------
        # MAKE SURE EVERY USER HAS AN ACCOUNT
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT u.id
            FROM users u
            LEFT JOIN accounts a
                ON a.user_id=u.id
            WHERE a.user_id IS NULL
            """
        )

        rows = cur.fetchall()

        for row in rows:

            cur.execute(
                """
                INSERT INTO accounts (
                    user_id,
                    deposit_account,
                    income_account,
                    referral_account,
                    withdraw_account
                )
                VALUES (
                    %s,
                    %s,
                    0,
                    0,
                    0
                )
                ON CONFLICT (user_id)
                DO NOTHING
                """,
                (
                    row[0],
                    STARTING_DEPOSIT_BALANCE
                )
            )


        # ----------------------------------------------------
        # CREATE / UPDATE ADMIN
        # ----------------------------------------------------

        admin_hash = generate_password_hash(
            ADMIN_PASSWORD
        )

        cur.execute(
            """
            SELECT id
            FROM admins
            WHERE username=%s
            """,
            (ADMIN_USERNAME,)
        )

        row = cur.fetchone()

        if row:

            cur.execute(
                """
                UPDATE admins
                SET password_hash=%s
                WHERE username=%s
                """,
                (
                    admin_hash,
                    ADMIN_USERNAME
                )
            )

        else:

            cur.execute(
                """
                INSERT INTO admins (
                    username,
                    password_hash
                )
                VALUES (
                    %s,
                    %s
                )
                """,
                (
                    ADMIN_USERNAME,
                    admin_hash
                )
            )


        # ----------------------------------------------------
        # INDEXES
        # ----------------------------------------------------

        indices = [

            """
            CREATE INDEX IF NOT EXISTS
            idx_users_phone
            ON users(phone)
            """,

            """
            CREATE INDEX IF NOT EXISTS
            idx_users_referral
            ON users(referral_code)
            """,

            """
            CREATE INDEX IF NOT EXISTS
            idx_users_referred_by
            ON users(referred_by)
            """,

            """
            CREATE INDEX IF NOT EXISTS
            idx_plans_user_active
            ON plans(user_id,active)
            """,

            """
            CREATE INDEX IF NOT EXISTS
            idx_deposit_requests_status
            ON deposit_requests(status)
            """,

            """
            CREATE INDEX IF NOT EXISTS
            idx_withdrawals_status
            ON withdrawal_requests(status)
            """,

            """
            CREATE INDEX IF NOT EXISTS
            idx_invites_token
            ON invites(token)
            """,
        ]

        for statement in indices:
            cur.execute(statement)


        conn.commit()

    except Exception:

        conn.rollback()

        app.logger.exception(
            "DATABASE INITIALIZATION ERROR"
        )

        raise

    finally:

        cur.close()
        conn.close()


# ============================================================
# CURRENT USER
# ============================================================

def current_user():

    user_id = session.get("user_id")

    if not user_id:
        return None

    return query_one(
        """
        SELECT *
        FROM users
        WHERE id=%s
        """,
        (user_id,)
    )


# ============================================================
# CURRENT ACCOUNT
# ============================================================

def current_account(user_id):

    account = query_one(
        """
        SELECT *
        FROM accounts
        WHERE user_id=%s
        """,
        (user_id,)
    )

    if account:
        return account

    execute(
        """
        INSERT INTO accounts (
            user_id,
            deposit_account,
            income_account,
            referral_account,
            withdraw_account
        )
        VALUES (
            %s,
            %s,
            0,
            0,
            0
        )
        ON CONFLICT (user_id)
        DO NOTHING
        """,
        (
            user_id,
            STARTING_DEPOSIT_BALANCE
        )
    )

    return query_one(
        """
        SELECT *
        FROM accounts
        WHERE user_id=%s
        """,
        (user_id,)
    )


def withdrawable_balance(account):
    """Return the amount currently available for withdrawal, including referral balance."""
    if not account:
        return Decimal("0.00")
    return money(account.get("withdraw_account")) + money(account.get("referral_account"))


def account_for_display(account):
    """Copy an account row and expose referral funds as part of the withdrawal balance."""
    if not account:
        return account
    result = dict(account)
    result["withdraw_account"] = withdrawable_balance(account)
    result["withdrawable_balance"] = result["withdraw_account"]
    return result


# ============================================================
# GLOBAL TEMPLATE USER
# ============================================================

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

    if session.get("admin_logged_in"):
        return redirect(
            url_for("admin_dashboard")
        )

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
        or request.form.get("referral_code", "").strip()
    )

    referred_user = None
    if invite_code:
        referred_user = query_one(
            """
            SELECT id, username, referral_code
            FROM users
            WHERE referral_code=%s
            """,
            (invite_code,),
        )

    if request.method == "POST":
        fullname = request.form.get("fullname", "").strip()
        username = request.form.get("username", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        withdraw_password = request.form.get("withdraw_password", "")

        if not fullname or not username or not phone:
            flash("Please complete all required fields.", "error")
            return render_template("register.html", invite_code=invite_code)

        if len(password) < 6:
            flash("Password must contain at least 6 characters.", "error")
            return render_template("register.html", invite_code=invite_code)

        if len(withdraw_password) < 4:
            flash("Withdrawal password must contain at least 4 characters.", "error")
            return render_template("register.html", invite_code=invite_code)

        existing = query_one(
            "SELECT id FROM users WHERE username=%s OR phone=%s",
            (username, phone),
        )
        if existing:
            flash("Username or phone number already exists.", "error")
            return render_template("register.html", invite_code=invite_code)

        if invite_code and not referred_user:
            flash("Invalid referral code.", "error")
            return render_template("register.html", invite_code=invite_code)

        referral_code = generate_referral_code()
        conn = get_conn()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO users (
                    username, fullname, phone,
                    password_hash, withdraw_password_hash,
                    referral_code, referred_by
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,
                (
                    username,
                    fullname,
                    phone,
                    generate_password_hash(password),
                    generate_password_hash(withdraw_password),
                    referral_code,
                    referred_user["referral_code"] if referred_user else None,
                ),
            )
            new_user_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO accounts (
                    user_id, deposit_account, income_account,
                    referral_account, withdraw_account
                )
                VALUES (%s,%s,0,0,0)
                ON CONFLICT (user_id) DO NOTHING
                """,
                (new_user_id, STARTING_DEPOSIT_BALANCE),
            )

            conn.commit()
        except Exception:
            conn.rollback()
            app.logger.exception("REGISTRATION ERROR")
            flash("Unable to register at this time.", "error")
            return render_template("register.html", invite_code=invite_code)
        finally:
            cur.close()
            conn.close()

        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html", invite_code=invite_code)


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")

        if not phone or not password:
            flash("Please enter your phone number and password.", "error")
            return render_template("login.html")

        user = query_one("SELECT * FROM users WHERE phone=%s", (phone,))
        valid = False
        used_legacy_password = False

        if user:
            stored_hash = user.get("password_hash")
            if stored_hash:
                try:
                    valid = check_password_hash(stored_hash, password)
                except Exception:
                    valid = False
            elif user.get("password") is not None:
                valid = user.get("password") == password
                used_legacy_password = valid

        if valid:
            # Upgrade old plaintext-password records the first time they log in.
            if used_legacy_password:
                execute(
                    """
                    UPDATE users
                    SET password_hash=%s, password=NULL
                    WHERE id=%s
                    """,
                    (generate_password_hash(password), user["id"]),
                )

            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))

        flash("Invalid phone number or password.", "error")

    return render_template("login.html")


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

    account = account_for_display(current_account(user["id"]))

    return render_template(
        "dashboard.html",
        user=user,
        account=account,
        plans=PLANS
    )


# ============================================================
# BUY PLAN
# ============================================================

@app.route(
    "/buy_plan/<int:plan_id>"
)
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


    if money(
        account["deposit_account"]
    ) < plan["investment"]:

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
# CONFIRM BUY PLAN
# ============================================================

@app.route("/confirm_buy_plan/<int:plan_id>", methods=["POST"])
def confirm_buy_plan(plan_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    if plan_id not in PLANS:
        flash("Plan not found.", "error")
        return redirect(url_for("dashboard"))

    plan = PLANS[plan_id]
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        ensure_account(cur, user["id"], STARTING_DEPOSIT_BALANCE)
        cur.execute(
            """
            SELECT deposit_account
            FROM accounts
            WHERE user_id=%s
            FOR UPDATE
            """,
            (user["id"],),
        )
        row = cur.fetchone()
        balance = money(row["deposit_account"] if row else 0)

        if balance < plan["investment"]:
            conn.rollback()
            flash("Insufficient deposit balance.", "error")
            return redirect(url_for("dashboard"))

        cur.execute(
            """
            UPDATE accounts
            SET deposit_account = deposit_account - %s
            WHERE user_id=%s AND deposit_account >= %s
            """,
            (plan["investment"], user["id"], plan["investment"]),
        )
        if cur.rowcount != 1:
            conn.rollback()
            flash("Insufficient deposit balance.", "error")
            return redirect(url_for("dashboard"))

        started_at = utcnow()
        cur.execute(
            """
            INSERT INTO plans (
                user_id, plan_id, plan_name, investment_amount,
                daily_income, duration, started_at, last_claim_at, active
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,NULL,TRUE)
            RETURNING id
            """,
            (
                user["id"], plan_id, plan["name"], plan["investment"],
                plan["daily"], plan["duration"], started_at,
            ),
        )
        new_plan = cur.fetchone()
        purchase_ref = generate_reference("PLAN")

        cur.execute(
            """
            INSERT INTO transactions (
                user_id, transaction_type, amount, status, reference, description
            )
            VALUES (%s,'plan_purchase',%s,'successful',%s,%s)
            """,
            (
                user["id"], plan["investment"], purchase_ref,
                f"Plan purchase: {plan['name']} (plan record #{new_plan['id']})",
            ),
        )

        # Referral bonuses are awarded for every purchase, not only the first plan.
        purchaser_id = user["id"]
        current_ref_code = user.get("referred_by")
        for level_index, pct in enumerate(REFERRAL_PERCENTS, start=1):
            if not current_ref_code:
                break

            owner_row = None
            cur.execute(
                """
                SELECT id, referred_by, referral_code
                FROM users
                WHERE referral_code=%s
                """,
                (current_ref_code,),
            )
            owner_row = cur.fetchone()
            if not owner_row:
                break

            owner_id = owner_row["id"]
            if owner_id != purchaser_id:
                bonus_amount = money(plan["investment"] * pct)
                if bonus_amount > 0:
                    ensure_account(cur, owner_id, Decimal("0.00"))
                    cur.execute(
                        """
                        UPDATE accounts
                        SET referral_account = COALESCE(referral_account,0) + %s
                        WHERE user_id=%s
                        """,
                        (bonus_amount, owner_id),
                    )
                    cur.execute(
                        """
                        INSERT INTO transactions (
                            user_id, transaction_type, amount, status, reference, description
                        )
                        VALUES (%s,'referral_bonus_invest',%s,'successful',%s,%s)
                        """,
                        (
                            owner_id,
                            bonus_amount,
                            generate_reference("RINV"),
                            f"Referral bonus level {level_index} for plan purchase {purchase_ref}",
                        ),
                    )

            current_ref_code = owner_row.get("referred_by")

        conn.commit()
        flash(
            f"{plan['name']} activated successfully. You can buy additional plans anytime your deposit balance is sufficient.",
            "success",
        )
    except Exception:
        conn.rollback()
        app.logger.exception("PLAN PURCHASE ERROR")
        flash("Unable to activate the plan.", "error")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("my_plan"))


# ============================================================
# PLAN TIME CALCULATIONS
# ============================================================

def plan_times(plan, now=None):

    now = now or utcnow()

    started = (
        plan.get("started_at")
        or now
    )


    if getattr(
        started,
        "tzinfo",
        None
    ) is None:

        started = started.replace(
            tzinfo=timezone.utc
        )


    end_time = (
        started
        + timedelta(
            days=int(
                plan.get(
                    "duration",
                    0
                )
            )
        )
    )


    last_claim = plan.get(
        "last_claim_at"
    )


    if last_claim is None:

        next_claim = (
            started
            + timedelta(
                hours=CLAIM_INTERVAL_HOURS
            )
        )

    else:

        if getattr(
            last_claim,
            "tzinfo",
            None
        ) is None:

            last_claim = last_claim.replace(
                tzinfo=timezone.utc
            )


        next_claim = (
            last_claim
            + timedelta(
                hours=CLAIM_INTERVAL_HOURS
            )
        )


    return (
        end_time,
        next_claim
    )


# ============================================================
# DEACTIVATE EXPIRED PLANS
# ============================================================

def deactivate_expired_plans(user_id):

    execute(
        """
        UPDATE plans
        SET active=FALSE
        WHERE user_id=%s
          AND active=TRUE
          AND started_at
              + (
                  duration
                  * INTERVAL '1 day'
              )
              <= CURRENT_TIMESTAMP
        """,
        (user_id,)
    )


# ============================================================
# MY PLAN
# ============================================================

@app.route("/my_plan", methods=["GET", "POST"])
def my_plan():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    try:
        deactivate_expired_plans(user["id"])
    except Exception:
        app.logger.exception("PLAN EXPIRY CHECK ERROR")

    if request.method == "POST":
        conn = get_conn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        claimed_total = Decimal("0.00")
        claimed_count = 0
        try:
            cur.execute(
                """
                SELECT * FROM plans
                WHERE user_id=%s AND active=TRUE
                ORDER BY id ASC
                FOR UPDATE
                """,
                (user["id"],),
            )
            plans_to_claim = cur.fetchall()
            now = utcnow()
            ensure_account(cur, user["id"], STARTING_DEPOSIT_BALANCE)

            for plan in plans_to_claim:
                end_time, next_claim = plan_times(plan, now)
                if now >= end_time:
                    cur.execute("UPDATE plans SET active=FALSE WHERE id=%s", (plan["id"],))
                    continue
                if now < next_claim:
                    continue

                daily_income = money(plan["daily_income"])
                if daily_income <= 0:
                    continue

                cur.execute(
                    """
                    UPDATE accounts
                    SET income_account=COALESCE(income_account,0)+%s,
                        withdraw_account=COALESCE(withdraw_account,0)+%s
                    WHERE user_id=%s
                    """,
                    (daily_income, daily_income, user["id"]),
                )
                claim_time = now
                cur.execute(
                    "UPDATE plans SET last_claim_at=%s WHERE id=%s",
                    (claim_time, plan["id"]),
                )
                cur.execute(
                    """
                    INSERT INTO transactions (
                        user_id, transaction_type, amount, status, reference, description
                    )
                    VALUES (%s,'income_claim',%s,'successful',%s,%s)
                    """,
                    (
                        user["id"], daily_income, generate_reference("INC"),
                        f"Daily income claim: {plan['plan_name']} (plan #{plan['id']})",
                    ),
                )
                claimed_total += daily_income
                claimed_count += 1

            conn.commit()
            if claimed_count:
                flash(
                    f"GHS {claimed_total:.2f} income claimed from {claimed_count} plan(s).",
                    "success",
                )
            else:
                flash("No plan is ready for a 24-hour income claim yet.", "error")
        except Exception:
            conn.rollback()
            app.logger.exception("MY PLAN CLAIM ERROR")
            flash("Unable to process your income claim.", "error")
        finally:
            cur.close()
            conn.close()
        return redirect(url_for("my_plan"))

    all_plans = query_all(
        """
        SELECT * FROM plans
        WHERE user_id=%s
        ORDER BY id DESC
        """,
        (user["id"],),
    )
    active_plans = [p for p in all_plans if p.get("active")]
    plan = active_plans[0] if active_plans else (all_plans[0] if all_plans else None)

    can_claim = False
    seconds_remaining = 0
    cycle_seconds_remaining = 0
    next_claim_timestamp = 0
    next_claim = None
    cycle_ended = False

    if active_plans:
        now = utcnow()
        next_claims = []
        for active in active_plans:
            end_time, nextc = plan_times(active, now)
            if now >= end_time:
                continue
            if now >= nextc:
                can_claim = True
            else:
                next_claims.append(nextc)

        if next_claims:
            next_claim = min(next_claims)
            seconds_remaining = max(0, int((next_claim - now).total_seconds()))
            next_claim_timestamp = int(next_claim.timestamp())
        if plan:
            end_time, _ = plan_times(plan, now)
            cycle_seconds_remaining = max(0, int((end_time - now).total_seconds()))
    elif all_plans:
        cycle_ended = True

    available_plans = [
        {
            "id": plan_id,
            "plan_name": data["name"],
            "investment_amount": data["investment"],
            "daily_income": data["daily"],
            "duration": data["duration"],
        }
        for plan_id, data in PLANS.items()
    ]

    return render_template(
        "my_plan.html",
        user_plans=plans,
        plans=plans,
        active_plans=all_plans,  # Keep old template variable but include every historical purchase.
        all_plans=all_plans,
        plans=available_plans,
        available_plans=available_plans,
        can_claim=can_claim,
        seconds_remaining=seconds_remaining,
        cycle_seconds_remaining=cycle_seconds_remaining,
        next_claim_timestamp=next_claim_timestamp,
        next_income_at=next_claim,
        server_now=utcnow(),
        cycle_ended=cycle_ended,
    )


# ============================================================
# DEPOSIT
# ============================================================

@app.route(
    "/deposit",
    methods=["GET", "POST"]
)
def deposit():

    user = current_user()

    if not user:
        return redirect(
            url_for("login")
        )


    if request.method == "POST":

        amount = parse_amount(
            request.form.get(
                "amount",
                "0"
            )
        )

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        payment_number = request.form.get(
            "payment_number",
            "0257425844"
        ).strip()

        screenshot = request.files.get(
            "screenshot"
        )


        if amount is None:

            flash(
                "Please enter a valid deposit amount.",
                "error"
            )

            return render_template(
                "deposit.html"
            )


        if amount < MIN_DEPOSIT:

            flash(
                f"Minimum demo deposit is "
                f"GHS {MIN_DEPOSIT:.2f}.",
                "error"
            )

            return render_template(
                "deposit.html"
            )


        if not phone:

            flash(
                "Please enter your phone number.",
                "error"
            )

            return render_template(
                "deposit.html"
            )


        if (
            not screenshot
            or not screenshot.filename
        ):

            flash(
                "Please upload your payment screenshot.",
                "error"
            )

            return render_template(
                "deposit.html"
            )


        allowed = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }


        filename = screenshot.filename.lower()


        mime_type = next(
            (
                mime
                for extension, mime
                in allowed.items()
                if filename.endswith(
                    extension
                )
            ),
            None
        )


        if not mime_type:

            flash(
                "Only PNG/JPG/JPEG/WEBP allowed.",
                "error"
            )

            return render_template(
                "deposit.html"
            )


        data = screenshot.read()


        if not data:

            flash(
                "Uploaded screenshot is empty.",
                "error"
            )

            return render_template(
                "deposit.html"
            )


        if len(data) > app.config[
            "MAX_CONTENT_LENGTH"
        ]:

            flash(
                "Screenshot is too large. Maximum 5MB.",
                "error"
            )

            return render_template(
                "deposit.html"
            )


        reference = generate_reference(
            "DEP"
        )


        conn = get_conn()
        cur = conn.cursor()

        try:

            cur.execute(
                """
                INSERT INTO deposit_requests (
                    user_id,
                    amount,
                    payment_number,
                    screenshot,
                    screenshot_data,
                    screenshot_mime,
                    reference,
                    status
                )
                VALUES (
                    %s,%s,%s,%s,%s,%s,%s,'pending'
                )
                RETURNING id
                """,
                (
                    user["id"],
                    amount,
                    payment_number,
                    screenshot.filename,
                    psycopg2.Binary(data),
                    mime_type,
                    reference
                )
            )


            dep_id = cur.fetchone()[0]


            cur.execute(
                """
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
                    %s
                )
                """,
                (
                    user["id"],
                    amount,
                    reference,
                    f"Demo deposit request #{dep_id}"
                )
            )


            conn.commit()


        except Exception:

            conn.rollback()

            app.logger.exception(
                "DEPOSIT SUBMISSION ERROR"
            )

            flash(
                "Could not submit deposit request.",
                "error"
            )

            return render_template(
                "deposit.html"
            )

        finally:

            cur.close()
            conn.close()


        flash(
            "Deposit request submitted successfully. "
            "Please wait for admin review.",
            "success"
        )

        return redirect(
            url_for(
                "transaction_history"
            )
        )


    return render_template(
        "deposit.html"
    )


# ============================================================
# ADMIN DEPOSIT IMAGE
# ============================================================

@app.route(
    "/admin/deposit-image/<int:deposit_id>"
)
def admin_deposit_image(deposit_id):

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )


    deposit = query_one(
        """
        SELECT
            screenshot_data,
            screenshot_mime
        FROM deposit_requests
        WHERE id=%s
        """,
        (deposit_id,)
    )


    if (
        not deposit
        or not deposit.get(
            "screenshot_data"
        )
    ):

        abort(404)


    return send_file(
        BytesIO(
            bytes(
                deposit[
                    "screenshot_data"
                ]
            )
        ),
        mimetype=(
            deposit.get(
                "screenshot_mime"
            )
            or "image/jpeg"
        ),
        as_attachment=False,
        download_name=(
            f"deposit_{deposit_id}.jpg"
        )
    )


# ============================================================
# OLD UPLOAD PATH COMPATIBILITY
# ============================================================

@app.route(
    "/uploads/deposits/<path:filename>"
)
def uploaded_deposit_image(filename):

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )


    deposit = query_one(
        """
        SELECT
            screenshot_data,
            screenshot_mime
        FROM deposit_requests
        WHERE screenshot=%s
        ORDER BY id DESC
        LIMIT 1
        """,
        (filename,)
    )


    if (
        not deposit
        or not deposit.get(
            "screenshot_data"
        )
    ):

        abort(404)


    return send_file(
        BytesIO(
            bytes(
                deposit[
                    "screenshot_data"
                ]
            )
        ),
        mimetype=(
            deposit.get(
                "screenshot_mime"
            )
            or "image/jpeg"
        ),
        as_attachment=False,
        download_name=filename
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


    account = account_for_display(current_account(user["id"]))

    accounts = query_all(
        """
        SELECT *
        FROM withdrawal_accounts
        WHERE user_id=%s
        ORDER BY id DESC
        """,
        (user["id"],)
    )


    return render_template(
        "withdraw.html",
        account=account,
        accounts=accounts
    )


# ============================================================
# BIND WITHDRAWAL ACCOUNT
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
                "Please complete all account details.",
                "error"
            )

        else:

            execute(
                """
                INSERT INTO withdrawal_accounts (
                    user_id,
                    account_name,
                    phone,
                    network
                )
                VALUES (
                    %s,%s,%s,%s
                )
                """,
                (
                    user["id"],
                    account_name,
                    phone,
                    network
                )
            )


            flash(
                "Withdrawal account saved.",
                "success"
            )


    accounts = query_all(
        """
        SELECT *
        FROM withdrawal_accounts
        WHERE user_id=%s
        ORDER BY id DESC
        """,
        (user["id"],)
    )


    return render_template(
        "bind_account.html",
        accounts=accounts
    )


# ============================================================
# REQUEST WITHDRAWAL
# ============================================================

@app.route("/request_withdrawal", methods=["POST"])
def request_withdrawal():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    amount = parse_amount(request.form.get("amount", "0"))
    password = request.form.get("password", "")
    account_id = request.form.get("account_id")

    if amount is None or amount < MIN_WITHDRAWAL:
        flash(f"Minimum demo withdrawal is GHS {MIN_WITHDRAWAL:.2f}.", "error")
        return redirect(url_for("withdraw"))

    stored_hash = user.get("withdraw_password_hash")
    valid = False
    if stored_hash:
        try:
            valid = check_password_hash(stored_hash, password)
        except Exception:
            valid = False
    elif user.get("withdraw_password") is not None:
        valid = user.get("withdraw_password") == password

    if not valid:
        flash("Invalid withdrawal password.", "error")
        return redirect(url_for("withdraw"))

    if account_id:
        selected = query_one(
            "SELECT id FROM withdrawal_accounts WHERE id=%s AND user_id=%s",
            (account_id, user["id"]),
        )
    else:
        selected = query_one(
            """
            SELECT id FROM withdrawal_accounts
            WHERE user_id=%s ORDER BY id DESC LIMIT 1
            """,
            (user["id"],),
        )

    if not selected:
        flash("Please bind a withdrawal account first.", "error")
        return redirect(url_for("bind_account"))

    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        ensure_account(cur, user["id"], STARTING_DEPOSIT_BALANCE)
        cur.execute(
            """
            SELECT withdraw_account, referral_account
            FROM accounts
            WHERE user_id=%s
            FOR UPDATE
            """,
            (user["id"],),
        )
        row = cur.fetchone() or {}
        withdraw_balance = money(row.get("withdraw_account"))
        referral_balance = money(row.get("referral_account"))
        total_available = withdraw_balance + referral_balance

        if total_available < amount:
            conn.rollback()
            flash("Insufficient withdrawal/referral balance.", "error")
            return redirect(url_for("withdraw"))

        # Use normal withdrawal balance first, then referral balance.
        from_withdraw = min(withdraw_balance, amount)
        from_referral = amount - from_withdraw
        cur.execute(
            """
            UPDATE accounts
            SET withdraw_account=COALESCE(withdraw_account,0)-%s,
                referral_account=COALESCE(referral_account,0)-%s
            WHERE user_id=%s
            """,
            (from_withdraw, from_referral, user["id"]),
        )

        cur.execute(
            """
            INSERT INTO withdrawal_requests (user_id, amount, account_id, status)
            VALUES (%s,%s,%s,'pending')
            RETURNING id
            """,
            (user["id"], amount, selected["id"]),
        )
        withdrawal_id = cur.fetchone()["id"]
        reference = generate_reference("WDR")

        cur.execute(
            """
            INSERT INTO transactions (
                user_id, transaction_type, amount, status, reference, description
            )
            VALUES (%s,'withdrawal',%s,'pending',%s,%s)
            """,
            (
                user["id"], amount, reference,
                f"Demo withdrawal request #{withdrawal_id}",
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        app.logger.exception("WITHDRAWAL REQUEST ERROR")
        flash("Unable to submit the withdrawal.", "error")
        return redirect(url_for("withdraw"))
    finally:
        cur.close()
        conn.close()

    flash("Withdrawal request submitted successfully.", "success")
    return redirect(url_for("transaction_history"))


# ============================================================
# TRANSACTION HISTORY
# ============================================================

@app.route(
    "/transaction_history"
)
def transaction_history():

    user = current_user()

    if not user:
        return redirect(
            url_for("login")
        )


    transactions = query_all(
        """
        SELECT *
        FROM transactions
        WHERE user_id=%s
        ORDER BY created_at DESC, id DESC
        """,
        (user["id"],)
    )


    return render_template(
        "transaction_history.html",
        transactions=transactions
    )


# ============================================================
# TEAM
#
# THIS SECTION MATCHES YOUR TEAM.HTML
#
# Provides:
#
# user
# total_team
# referral_income
# level1_count
# level2_count
# level3_count
# members
#
# Each member provides:
#
# member.username
# member.phone
# member.referral_level
# member.invest_amount
# member.created_at
# ============================================================

@app.route("/team")
def team():

    user = current_user()

    if not user:

        return redirect(
            url_for("login")
        )


    # --------------------------------------------------------
    # USER ACCOUNT
    # --------------------------------------------------------

    account = current_account(
        user["id"]
    )


    referral_income = money(
        account["referral_account"]
        if account
        else Decimal("0.00")
    )


    # --------------------------------------------------------
    # LEVEL 1
    #
    # Direct referrals.
    #
    # Their referred_by value equals the current user's
    # referral_code.
    # --------------------------------------------------------

    level1_users = query_all(
        """
        SELECT
            id,
            username,
            fullname,
            phone,
            referral_code,
            referred_by,
            created_at
        FROM users
        WHERE referred_by=%s
        ORDER BY created_at DESC, id DESC
        """,
        (
            user["referral_code"],
        )
    )


    # --------------------------------------------------------
    # LEVEL 1 REFERRAL CODES
    # --------------------------------------------------------

    level1_codes = [
        member["referral_code"]
        for member in level1_users
        if member.get("referral_code")
    ]


    # --------------------------------------------------------
    # LEVEL 2
    #
    # Users referred by Level 1 members.
    # --------------------------------------------------------

    level2_users = []


    if level1_codes:

        level2_users = query_all(
            """
            SELECT
                id,
                username,
                fullname,
                phone,
                referral_code,
                referred_by,
                created_at
            FROM users
            WHERE referred_by = ANY(%s)
            ORDER BY created_at DESC, id DESC
            """,
            (
                level1_codes,
            )
        )


    # --------------------------------------------------------
    # LEVEL 2 REFERRAL CODES
    # --------------------------------------------------------

    level2_codes = [
        member["referral_code"]
        for member in level2_users
        if member.get("referral_code")
    ]


    # --------------------------------------------------------
    # LEVEL 3
    #
    # Users referred by Level 2 members.
    # --------------------------------------------------------

    level3_users = []


    if level2_codes:

        level3_users = query_all(
            """
            SELECT
                id,
                username,
                fullname,
                phone,
                referral_code,
                referred_by,
                created_at
            FROM users
            WHERE referred_by = ANY(%s)
            ORDER BY created_at DESC, id DESC
            """,
            (
                level2_codes,
            )
        )


    # --------------------------------------------------------
    # MARK REFERRAL LEVEL
    # --------------------------------------------------------

    members = []


    for member in level1_users:

        member["referral_level"] = 1

        members.append(member)


    for member in level2_users:

        member["referral_level"] = 2

        members.append(member)


    for member in level3_users:

        member["referral_level"] = 3

        members.append(member)


    # --------------------------------------------------------
    # GET INVESTMENT AMOUNT FOR EVERY TEAM MEMBER
    #
    # Investment comes from the plans table.
    #
    # Example:
    #
    # User buys Zenith 1 = GHS 50
    # User buys another plan = GHS 100
    #
    # Total investment shown = GHS 150
    # --------------------------------------------------------

    for member in members:

        investment = query_one(
            """
            SELECT
                COALESCE(
                    SUM(investment_amount),
                    0
                ) AS total_investment
            FROM plans
            WHERE user_id=%s
            """,
            (
                member["id"],
            )
        )


        member["invest_amount"] = money(
            investment[
                "total_investment"
            ]
            if investment
            else Decimal("0.00")
        )


    # --------------------------------------------------------
    # TEAM COUNTS
    # --------------------------------------------------------

    level1_count = len(
        level1_users
    )

    level2_count = len(
        level2_users
    )

    level3_count = len(
        level3_users
    )


    total_team = (
        level1_count
        + level2_count
        + level3_count
    )


    # --------------------------------------------------------
    # RENDER TEAM PAGE
    # --------------------------------------------------------

    return render_template(
        "team.html",

        user=user,

        members=members,

        total_team=total_team,

        referral_income=
            referral_income,

        level1_count=
            level1_count,

        level2_count=
            level2_count,

        level3_count=
            level3_count,
    )


# ============================================================
# SUPPORT / SERVICE
# ============================================================

@app.route("/support")
@app.route("/service")
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


    account = current_account(user["id"])

    return render_template(
        "profile.html",

        user=user,

        deposit_balance=
            account["deposit_account"],

        withdraw_balance=withdrawable_balance(account),

        income_balance=
            account["income_account"],

        referral_balance=
            account["referral_account"],
    )


# ============================================================
# CHANGE LOGIN PASSWORD
# ============================================================

@app.route("/admin_change_password", methods=["GET", "POST"])
@app.route("/change_login_password", methods=["GET", "POST"])
def admin_change_password():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        valid = False
        if user.get("password_hash"):
            try:
                valid = check_password_hash(user["password_hash"], current_password)
            except Exception:
                valid = False
        else:
            valid = user.get("password") == current_password

        if not valid:
            flash("Current password is incorrect.", "error")
            return render_template("change_login_password.html")
        if len(new_password) < 6:
            flash("New password must contain at least 6 characters.", "error")
            return render_template("change_login_password.html")
        if new_password != confirm_password:
            flash("New passwords do not match.", "error")
            return render_template("change_login_password.html")

        execute(
            "UPDATE users SET password_hash=%s, password=NULL WHERE id=%s",
            (generate_password_hash(new_password), user["id"]),
        )
        flash("Login password changed successfully.", "success")
        return redirect(url_for("profile"))

    return render_template("change_login_password.html")


# ============================================================
# CHANGE WITHDRAWAL PASSWORD
# ============================================================

@app.route("/admin_withdraw_password", methods=["GET", "POST"])
@app.route("/change_withdraw_password", methods=["GET", "POST"])
def admin_change_withdraw_password():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        valid = False
        if user.get("withdraw_password_hash"):
            try:
                valid = check_password_hash(user["withdraw_password_hash"], current_password)
            except Exception:
                valid = False
        else:
            valid = user.get("withdraw_password") == current_password

        if not valid:
            flash("Current withdrawal password is incorrect.", "error")
            return render_template("change_withdraw_password.html")
        if len(new_password) < 4:
            flash("New withdrawal password must contain at least 4 characters.", "error")
            return render_template("change_withdraw_password.html")
        if new_password != confirm_password:
            flash("New passwords do not match.", "error")
            return render_template("change_withdraw_password.html")

        execute(
            "UPDATE users SET withdraw_password_hash=%s, withdraw_password=NULL WHERE id=%s",
            (generate_password_hash(new_password), user["id"]),
        )
        flash("Withdrawal password changed successfully.", "success")
        return redirect(url_for("profile"))

    return render_template("change_withdraw_password.html")


# ============================================================
# ADMIN AUTHORIZATION
# ============================================================

def admin_required():

    return (
        session.get(
            "admin_logged_in"
        )
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


        admin = query_one(
            """
            SELECT *
            FROM admins
            WHERE username=%s
            """,
            (username,)
        )


        valid = False


        if admin:

            try:

                valid = check_password_hash(
                    admin["password_hash"],
                    password
                )

            except Exception:

                valid = False


        if valid:

            session.clear()

            session[
                "admin_logged_in"
            ] = True

            session[
                "admin_id"
            ] = admin["id"]


            return redirect(
                url_for(
                    "admin_dashboard"
                )
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

    session.clear()

    return redirect(
        url_for("admin_login")
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin/dashboard")
def admin_dashboard():

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )


    total_users = query_one(
        """
        SELECT COUNT(*) AS count
        FROM users
        """
    )["count"]


    pending_deposits = query_one(
        """
        SELECT COUNT(*) AS count
        FROM deposit_requests
        WHERE status='pending'
        """
    )["count"]


    pending_withdrawals = query_one(
        """
        SELECT COUNT(*) AS count
        FROM withdrawal_requests
        WHERE status='pending'
        """
    )["count"]


    invites = query_all(
        """
        SELECT
            i.*,
            u.username AS owner_username
        FROM invites i
        LEFT JOIN users u
            ON u.id=i.owner_id
        ORDER BY i.created_at DESC
        LIMIT 100
        """
    )


    return render_template(
        "admin_dashboard.html",

        total_users=
            total_users,

        pending_deposits=
            pending_deposits,

        pending_withdrawals=
            pending_withdrawals,

        invites=invites
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


    users = query_all(
        """
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
        """
    )


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


    user = query_one(
        """
        SELECT *
        FROM users
        WHERE id=%s
        """,
        (user_id,)
    )


    if not user:

        return "User not found", 404


    if request.method == "POST":

        action = request.form.get(
            "action",
            ""
        )


        balance_actions = {

            "add_deposit":
                "deposit_account",

            "deduct_deposit":
                "deposit_account",

            "add_withdraw":
                "withdraw_account",

            "deduct_withdraw":
                "withdraw_account",

            "add_income":
                "income_account",

            "deduct_income":
                "income_account",

            "add_referral":
                "referral_account",

            "deduct_referral":
                "referral_account",
        }


        # ----------------------------------------------------
        # BALANCE ACTION
        # ----------------------------------------------------

        if action in balance_actions:

            amount = parse_amount(
                request.form.get(
                    "amount",
                    "0"
                )
            )


            if amount is None:

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


            column = balance_actions[
                action
            ]

            is_add = action.startswith(
                "add_"
            )


            conn = get_conn()

            cur = conn.cursor(
                cursor_factory=RealDictCursor
            )


            try:

                ensure_account(
                    cur,
                    user_id,
                    STARTING_DEPOSIT_BALANCE
                )


                if is_add:

                    # Column comes only from the
                    # trusted balance_actions dictionary.
                    cur.execute(
                        f"""
                        UPDATE accounts
                        SET {column} =
                            COALESCE(
                                {column},
                                0
                            ) + %s
                        WHERE user_id=%s
                        """,
                        (
                            amount,
                            user_id
                        )
                    )

                else:

                    cur.execute(
                        f"""
                        UPDATE accounts
                        SET {column} =
                            GREATEST(
                                0,
                                COALESCE(
                                    {column},
                                    0
                                ) - %s
                            )
                        WHERE user_id=%s
                        """,
                        (
                            amount,
                            user_id
                        )
                    )


                cur.execute(
                    """
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
                        'admin_balance_adjustment',
                        %s,
                        'successful',
                        %s,
                        %s
                    )
                    """,
                    (
                        user_id,
                        amount,
                        generate_reference(
                            "ADM"
                        ),
                        (
                            "Admin adjustment: "
                            + action
                        )
                    )
                )


                conn.commit()


            except Exception:

                conn.rollback()

                app.logger.exception(
                    "ADMIN BALANCE ACTION FAILED"
                )

                flash(
                    "Unable to update balance.",
                    "error"
                )

            finally:

                cur.close()
                conn.close()


            flash(
                "User balance updated successfully.",
                "success"
            )


            return redirect(
                url_for(
                    "admin_manage_user",
                    user_id=user_id
                )
            )


        # ----------------------------------------------------
        # CHANGE LOGIN PASSWORD
        # ----------------------------------------------------

        if action == "change_login_password":

            new_password = request.form.get(
                "new_password",
                ""
            )


            if len(new_password) < 6:

                flash(
                    "Login password must contain at least 6 characters.",
                    "error"
                )

            else:

                new_hash = generate_password_hash(
                    new_password
                )


                execute(
                    """
                    UPDATE users
                    SET
                        password_hash=%s,
                        password=NULL
                    WHERE id=%s
                    """,
                    (
                        new_hash,
                        user_id
                    )
                )


                app.logger.info(
                    "Admin %s set login password "
                    "for user %s",
                    session.get(
                        "admin_id"
                    ),
                    user_id
                )


                flash(
                    "Login password updated successfully.",
                    "success"
                )


            return redirect(
                url_for(
                    "admin_manage_user",
                    user_id=user_id
                )
            )


        # ----------------------------------------------------
        # CHANGE WITHDRAWAL PASSWORD
        # ----------------------------------------------------

        if action == "change_withdraw_password":

            new_password = request.form.get(
                "new_password",
                ""
            )


            if len(new_password) < 4:

                flash(
                    "Withdrawal password must contain at least 4 characters.",
                    "error"
                )

            else:

                new_hash = generate_password_hash(
                    new_password
                )


                execute(
                    """
                    UPDATE users
                    SET
                        withdraw_password_hash=%s,
                        withdraw_password=NULL
                    WHERE id=%s
                    """,
                    (
                        new_hash,
                        user_id
                    )
                )


                app.logger.info(
                    "Admin %s set withdrawal password "
                    "for user %s",
                    session.get(
                        "admin_id"
                    ),
                    user_id
                )


                flash(
                    "Withdrawal password updated successfully.",
                    "success"
                )


            return redirect(
                url_for(
                    "admin_manage_user",
                    user_id=user_id
                )
            )


        # ----------------------------------------------------
        # UPDATE WITHDRAWAL ACCOUNT
        # ----------------------------------------------------

        if action == "update_account":

            account_id = request.form.get(
                "account_id"
            )

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
                not account_id
                or not account_name
                or not phone
                or not network
            ):

                flash(
                    "Please complete all withdrawal account details.",
                    "error"
                )

            else:

                execute(
                    """
                    UPDATE withdrawal_accounts
                    SET
                        account_name=%s,
                        phone=%s,
                        network=%s
                    WHERE id=%s
                      AND user_id=%s
                    """,
                    (
                        account_name,
                        phone,
                        network,
                        account_id,
                        user_id
                    )
                )


                flash(
                    "Withdrawal account updated successfully.",
                    "success"
                )


            return redirect(
                url_for(
                    "admin_manage_user",
                    user_id=user_id
                )
            )


        # ----------------------------------------------------
        # DELETE WITHDRAWAL ACCOUNT
        # ----------------------------------------------------

        if action == "delete_account":

            execute(
                """
                DELETE FROM withdrawal_accounts
                WHERE id=%s
                  AND user_id=%s
                """,
                (
                    request.form.get(
                        "account_id"
                    ),
                    user_id
                )
            )


            flash(
                "Withdrawal account removed.",
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


    withdrawal_accounts = query_all(
        """
        SELECT *
        FROM withdrawal_accounts
        WHERE user_id=%s
        ORDER BY id DESC
        """,
        (user_id,)
    )


    return render_template(
        "admin_manage_user.html",
        user=user,
        account=account,
        withdrawal_accounts=
            withdrawal_accounts
    )


# ============================================================
# ADMIN BIND ACCOUNTS
# ============================================================

@app.route(
    "/admin/bind_accounts"
)
@app.route(
    "/admin_bind_accounts"
)
def admin_bind_accounts():

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )


    accounts = query_all(
        """
        SELECT
            wa.*,
            u.username,
            u.phone AS user_phone
        FROM withdrawal_accounts wa
        JOIN users u
            ON u.id=wa.user_id
        ORDER BY
            wa.created_at DESC,
            wa.id DESC
        """
    )


    return render_template(
        "admin_bind_accounts.html",
        accounts=accounts
    )


# ============================================================
# ADMIN DEPOSITS
# ============================================================

@app.route(
    "/admin/deposits"
)
def admin_deposits():

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )


    deposits = query_all(
        """
        SELECT
            d.id,
            d.user_id,
            d.amount,
            d.payment_number,
            d.screenshot,
            d.screenshot_mime,
            d.reference,
            d.status,
            d.created_at,

            u.username,
            u.fullname,
            u.phone

        FROM deposit_requests d

        JOIN users u
            ON u.id=d.user_id

        ORDER BY
            d.created_at DESC,
            d.id DESC
        """
    )


    return render_template(
        "admin_deposit.html",
        deposits=deposits
    )


# ============================================================
# ADMIN DEPOSIT ACTION
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


    if action not in {
        "approve",
        "reject"
    }:

        flash(
            "Invalid deposit action.",
            "error"
        )

        return redirect(
            url_for("admin_deposits")
        )


    conn = get_conn()

    cur = conn.cursor(
        cursor_factory=RealDictCursor
    )


    try:

        cur.execute(
            """
            SELECT
                id,
                user_id,
                amount,
                reference,
                status
            FROM deposit_requests
            WHERE id=%s
            FOR UPDATE
            """,
            (deposit_id,)
        )


        deposit = cur.fetchone()


        if not deposit:

            conn.rollback()

            flash(
                "Deposit request not found.",
                "error"
            )

            return redirect(
                url_for("admin_deposits")
            )


        if deposit["status"] != "pending":

            conn.rollback()

            flash(
                "This deposit has already been reviewed.",
                "error"
            )

            return redirect(
                url_for("admin_deposits")
            )


        user_id = deposit["user_id"]

        amount = money(
            deposit["amount"]
        )

        reference = deposit.get(
            "reference"
        )


        if action == "approve":

            ensure_account(
                cur,
                user_id,
                Decimal("0.00")
            )


            cur.execute(
                """
                UPDATE accounts
                SET deposit_account =
                    COALESCE(
                        deposit_account,
                        0
                    ) + %s
                WHERE user_id=%s
                """,
                (
                    amount,
                    user_id
                )
            )


            cur.execute(
                """
                UPDATE deposit_requests
                SET status='approved'
                WHERE id=%s
                """,
                (deposit_id,)
            )


            cur.execute(
                """
                UPDATE transactions
                SET status='successful'
                WHERE user_id=%s
                  AND transaction_type='deposit'
                  AND reference=%s
                  AND status='pending'
                """,
                (
                    user_id,
                    reference
                )
            )


            message = (
                f"Demo deposit of "
                f"GHS {amount:.2f} "
                f"approved successfully."
            )


        else:

            cur.execute(
                """
                UPDATE deposit_requests
                SET status='rejected'
                WHERE id=%s
                """,
                (deposit_id,)
            )


            cur.execute(
                """
                UPDATE transactions
                SET status='failed'
                WHERE user_id=%s
                  AND transaction_type='deposit'
                  AND reference=%s
                  AND status='pending'
                """,
                (
                    user_id,
                    reference
                )
            )


            message = (
                f"Demo deposit of "
                f"GHS {amount:.2f} "
                f"rejected."
            )


        conn.commit()


        flash(
            message,
            "success"
        )


    except Exception:

        conn.rollback()

        app.logger.exception(
            "ADMIN DEPOSIT ACTION ERROR"
        )

        flash(
            "Unable to process the deposit.",
            "error"
        )


    finally:

        cur.close()
        conn.close()


    return redirect(
        url_for("admin_deposits")
    )


# ============================================================
# ADMIN WITHDRAWALS
# ============================================================

@app.route(
    "/admin/withdrawals"
)
def admin_withdrawals():

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )


    withdrawals = query_all(
        """
        SELECT
            w.*,

            u.username,
            u.fullname,
            u.phone,

            wa.account_name,

            wa.phone AS account_phone,

            wa.network

        FROM withdrawal_requests w

        JOIN users u
            ON u.id=w.user_id

        LEFT JOIN withdrawal_accounts wa
            ON wa.id=w.account_id

        ORDER BY
            w.created_at DESC,
            w.id DESC
        """
    )


    return render_template(
        "admin_withdraw.html",
        withdrawals=withdrawals
    )


# ============================================================
# ADMIN WITHDRAWAL ACTION
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


    if action not in {
        "approve",
        "reject"
    }:

        flash(
            "Invalid withdrawal action.",
            "error"
        )

        return redirect(
            url_for("admin_withdrawals")
        )


    conn = get_conn()

    cur = conn.cursor(
        cursor_factory=RealDictCursor
    )


    try:

        cur.execute(
            """
            SELECT *
            FROM withdrawal_requests
            WHERE id=%s
            FOR UPDATE
            """,
            (withdrawal_id,)
        )


        withdrawal = cur.fetchone()


        if not withdrawal:

            conn.rollback()

            flash(
                "Withdrawal request not found.",
                "error"
            )

            return redirect(
                url_for("admin_withdrawals")
            )


        if withdrawal["status"] != "pending":

            conn.rollback()

            flash(
                "Withdrawal request is no longer pending.",
                "error"
            )

            return redirect(
                url_for("admin_withdrawals")
            )


        user_id = withdrawal["user_id"]

        amount = money(
            withdrawal["amount"]
        )


        if action == "approve":

            cur.execute(
                """
                UPDATE withdrawal_requests
                SET status='approved'
                WHERE id=%s
                """,
                (withdrawal_id,)
            )


            # Match the transaction associated with this
            # withdrawal request using the newest pending
            # withdrawal transaction for the same user/amount.
            cur.execute(
                """
                UPDATE transactions
                SET status='successful'
                WHERE id = (
                    SELECT id
                    FROM transactions
                    WHERE user_id=%s
                      AND transaction_type='withdrawal'
                      AND amount=%s
                      AND status='pending'
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                )
                """,
                (
                    user_id,
                    amount
                )
            )


            message = (
                "Withdrawal approved successfully."
            )


        else:

            ensure_account(
                cur,
                user_id,
                Decimal("0.00")
            )


            # Restore rejected withdrawal
            cur.execute(
                """
                UPDATE accounts
                SET withdraw_account =
                    COALESCE(
                        withdraw_account,
                        0
                    ) + %s
                WHERE user_id=%s
                """,
                (
                    amount,
                    user_id
                )
            )


            cur.execute(
                """
                UPDATE withdrawal_requests
                SET status='rejected'
                WHERE id=%s
                """,
                (withdrawal_id,)
            )


            cur.execute(
                """
                UPDATE transactions
                SET status='failed'
                WHERE id = (
                    SELECT id
                    FROM transactions
                    WHERE user_id=%s
                      AND transaction_type='withdrawal'
                      AND amount=%s
                      AND status='pending'
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                )
                """,
                (
                    user_id,
                    amount
                )
            )


            message = (
                "Withdrawal rejected "
                "and balance restored."
            )


        conn.commit()


        flash(
            message,
            "success"
        )


    except Exception:

        conn.rollback()

        app.logger.exception(
            "ADMIN WITHDRAWAL ACTION ERROR"
        )

        flash(
            "Unable to process the withdrawal.",
            "error"
        )


    finally:

        cur.close()
        conn.close()


    return redirect(
        url_for("admin_withdrawals")
    )


# ============================================================
# ADMIN INVITE APPROVAL
# ============================================================

@app.route(
    "/admin/approve_invite/<token>",
    methods=["GET", "POST"]
)
def admin_approve_invite(token):

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )


    conn = get_conn()

    cur = conn.cursor(
        cursor_factory=RealDictCursor
    )


    try:

        cur.execute(
            """
            SELECT *
            FROM invites
            WHERE token=%s
            FOR UPDATE
            """,
            (token,)
        )


        invite = cur.fetchone()


        if not invite:

            flash(
                "Invite not found.",
                "error"
            )

            return redirect(
                url_for("admin_dashboard")
            )


        if invite.get("approved"):

            flash(
                "Invite already approved.",
                "info"
            )

            return redirect(
                url_for("admin_dashboard")
            )


        owner_id = invite["owner_id"]

        amount = money(
            invite.get("amount")
            or 0
        )


        ensure_account(
            cur,
            owner_id,
            STARTING_DEPOSIT_BALANCE
        )


        cur.execute(
            """
            UPDATE accounts
            SET referral_account =
                COALESCE(
                    referral_account,
                    0
                ) + %s
            WHERE user_id=%s
            """,
            (
                amount,
                owner_id
            )
        )


        cur.execute(
            """
            UPDATE invites
            SET approved=TRUE
            WHERE id=%s
            """,
            (invite["id"],)
        )


        cur.execute(
            """
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
                'invite_credit',
                %s,
                'successful',
                %s,
                %s
            )
            """,
            (
                owner_id,
                amount,
                generate_reference(
                    "INV"
                ),
                (
                    "Admin approved invite "
                    + token
                )
            )
        )


        conn.commit()


        flash(
            f"Invite approved and "
            f"GHS {amount:.2f} credited "
            f"to user id {owner_id}.",
            "success"
        )


    except Exception:

        conn.rollback()

        app.logger.exception(
            "APPROVE INVITE ERROR"
        )

        flash(
            "Unable to approve invite.",
            "error"
        )


    finally:

        cur.close()
        conn.close()


    return redirect(
        url_for("admin_dashboard")
    )


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(413)
def file_too_large(error):

    flash(
        "Screenshot is too large. Maximum size is 5 MB.",
        "error"
    )

    return redirect(
        url_for("deposit")
    )


@app.errorhandler(404)
def not_found(error):

    return (
        "Page not found",
        404
    )


@app.errorhandler(500)
def server_error(error):

    app.logger.exception(
        "INTERNAL SERVER ERROR"
    )

    return (
        "An internal server error occurred.",
        500
    )


# ============================================================
# START DATABASE
# ============================================================

with app.app_context():

    init_db()


# ============================================================
# START APPLICATION
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "5000"
        )
    )


    debug = (
        os.environ.get(
            "FLASK_DEBUG",
            "False"
        ).lower()
        in (
            "1",
            "true",
            "yes"
        )
    )


    app.run(
        host="0.0.0.0",
        port=port,
        debug=debug
    )
