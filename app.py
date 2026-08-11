import os
import uuid
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
    send_file,
    abort,
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash,
)

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None
    RealDictCursor = None


# ============================================================
# APP CONFIGURATION
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-key",
)

DATABASE_URL = os.environ.get("DATABASE_URL")

ADMIN_USERNAME = os.environ.get(
    "ADMIN_USERNAME",
    "Williams",
)

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "Williams12",
)

# Demo platform settings.
MIN_DEPOSIT = Decimal("45")
MIN_WITHDRAWAL = Decimal("30")

# Demo starting balance for newly registered users.
STARTING_DEPOSIT_BALANCE = Decimal("5.00")


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
# HELPERS
# ============================================================

def utcnow():
    """
    Return a naive UTC datetime.

    PostgreSQL TIMESTAMP columns in this application use UTC.
    """
    return datetime.utcnow()


def money(value):
    """
    Safely convert a PostgreSQL numeric/string value to Decimal.
    """
    if value is None:
        return Decimal("0")

    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def parse_amount(value):
    """
    Parse a positive monetary amount.
    """
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None

    if not amount.is_finite():
        return None

    return amount.quantize(Decimal("0.01"))


def generate_referral_code():
    return "ZEN" + uuid.uuid4().hex[:12].upper()


def generate_reference(prefix):
    return prefix + "-" + uuid.uuid4().hex[:12].upper()


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_conn():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not configured."
        )

    if psycopg2 is None:
        raise RuntimeError(
            "psycopg2 is not installed."
        )

    return psycopg2.connect(
        DATABASE_URL,
        sslmode="require",
    )


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
                username VARCHAR(120),
                fullname VARCHAR(200) DEFAULT '',
                phone VARCHAR(50),
                password_hash TEXT,
                withdraw_password_hash TEXT,
                referral_code VARCHAR(120),
                referred_by VARCHAR(120),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        user_columns = {
            "username": "VARCHAR(120)",
            "fullname": "VARCHAR(200) DEFAULT ''",
            "phone": "VARCHAR(50)",
            "password_hash": "TEXT",
            "withdraw_password_hash": "TEXT",
            "referral_code": "VARCHAR(120)",
            "referred_by": "VARCHAR(120)",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        }

        for column, definition in user_columns.items():
            cur.execute(
                f"""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS {column} {definition}
                """
            )

        # ----------------------------------------------------
        # LEGACY PASSWORD COMPATIBILITY
        # ----------------------------------------------------

        legacy_columns = [
            "login_password",
            "password",
            "withdraw_password",
            "withdrawal_password",
        ]

        for old_column in legacy_columns:

            cur.execute("""
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema='public'
                    AND table_name='users'
                    AND column_name=%s
                )
            """, (old_column,))

            exists = cur.fetchone()[0]

            if exists:

                try:
                    cur.execute(
                        f"""
                        ALTER TABLE users
                        ALTER COLUMN {old_column}
                        DROP NOT NULL
                        """
                    )
                except Exception:
                    conn.rollback()

        # Copy legacy password hash if necessary.

        cur.execute("""
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema='public'
                AND table_name='users'
                AND column_name='password'
            )
        """)

        has_old_password = cur.fetchone()[0]

        if has_old_password:

            cur.execute("""
                UPDATE users
                SET password_hash=password
                WHERE (password_hash IS NULL OR password_hash='')
                AND password IS NOT NULL
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
                    NOT NULL DEFAULT 5.00,

                income_account NUMERIC(14,2)
                    NOT NULL DEFAULT 0,

                referral_account NUMERIC(14,2)
                    NOT NULL DEFAULT 0,

                withdraw_account NUMERIC(14,2)
                    NOT NULL DEFAULT 0
            )
        """)

        account_columns = {
            "deposit_account": "NUMERIC(14,2) DEFAULT 5.00",
            "income_account": "NUMERIC(14,2) DEFAULT 0",
            "referral_account": "NUMERIC(14,2) DEFAULT 0",
            "withdraw_account": "NUMERIC(14,2) DEFAULT 0",
        }

        for column, definition in account_columns.items():
            cur.execute(
                f"""
                ALTER TABLE accounts
                ADD COLUMN IF NOT EXISTS {column} {definition}
                """
            )

        # Existing databases might have accounts.user_id without
        # a primary/unique constraint. Ensure one exists.

        cur.execute("""
            SELECT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid='accounts'::regclass
                AND contype='p'
            )
        """)

        accounts_have_pk = cur.fetchone()[0]

        if not accounts_have_pk:

            cur.execute("""
                SELECT user_id, COUNT(*)
                FROM accounts
                GROUP BY user_id
                HAVING COUNT(*) > 1
            """)

            duplicate_accounts = cur.fetchall()

            if not duplicate_accounts:

                try:
                    cur.execute("""
                        ALTER TABLE accounts
                        ADD CONSTRAINT accounts_user_id_pk
                        PRIMARY KEY (user_id)
                    """)
                except Exception:
                    conn.rollback()

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

                plan_name VARCHAR(120) NOT NULL,

                investment_amount NUMERIC(14,2) NOT NULL,

                daily_income NUMERIC(14,2) NOT NULL,

                duration INTEGER NOT NULL,

                started_at TIMESTAMP
                    NOT NULL DEFAULT CURRENT_TIMESTAMP,

                last_claim_at TIMESTAMP,

                active BOOLEAN
                    NOT NULL DEFAULT TRUE
            )
        """)

        plan_columns = {
            "user_id": "INTEGER",
            "plan_id": "INTEGER",
            "plan_name": "VARCHAR(120)",
            "investment_amount": "NUMERIC(14,2)",
            "daily_income": "NUMERIC(14,2)",
            "duration": "INTEGER",
            "started_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "last_claim_at": "TIMESTAMP",
            "active": "BOOLEAN DEFAULT TRUE",
        }

        for column, definition in plan_columns.items():
            cur.execute(
                f"""
                ALTER TABLE plans
                ADD COLUMN IF NOT EXISTS {column} {definition}
                """
            )

        # ----------------------------------------------------
        # TRANSACTIONS
        # ----------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                transaction_type VARCHAR(60) NOT NULL,

                amount NUMERIC(14,2) NOT NULL,

                status VARCHAR(40) NOT NULL,

                reference VARCHAR(200),

                description TEXT,

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
            )
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

                account_name VARCHAR(150) NOT NULL,

                phone VARCHAR(50) NOT NULL,

                network VARCHAR(60) NOT NULL,

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ----------------------------------------------------
        # DEPOSIT REQUESTS
        #
        # IMPORTANT:
        # Screenshot is now stored in PostgreSQL BYTEA.
        # This prevents Render filesystem persistence problems.
        # ----------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS deposit_requests (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                amount NUMERIC(14,2) NOT NULL,

                payment_number VARCHAR(80),

                screenshot TEXT,

                screenshot_data BYTEA,

                screenshot_mime VARCHAR(100),

                reference VARCHAR(200),

                status VARCHAR(40)
                    NOT NULL DEFAULT 'pending',

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
            )
        """)

        deposit_columns = {
            "payment_number": "VARCHAR(80)",
            "screenshot": "TEXT",
            "screenshot_data": "BYTEA",
            "screenshot_mime": "VARCHAR(100)",
            "reference": "VARCHAR(200)",
            "status": "VARCHAR(40) DEFAULT 'pending'",
        }

        for column, definition in deposit_columns.items():
            cur.execute(
                f"""
                ALTER TABLE deposit_requests
                ADD COLUMN IF NOT EXISTS {column} {definition}
                """
            )

        # ----------------------------------------------------
        # WITHDRAWAL REQUESTS
        # ----------------------------------------------------

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

                status VARCHAR(40)
                    NOT NULL DEFAULT 'pending',

                created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ----------------------------------------------------
        # ADMINS
        # ----------------------------------------------------

        cur.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,

                username VARCHAR(120)
                    UNIQUE NOT NULL,

                password_hash TEXT NOT NULL
            )
        """)

        # ----------------------------------------------------
        # GENERATE MISSING REFERRAL CODES
        # ----------------------------------------------------

        cur.execute("""
            SELECT id
            FROM users
            WHERE referral_code IS NULL
               OR referral_code=''
        """)

        missing_codes = cur.fetchall()

        for row in missing_codes:

            code = generate_referral_code()

            cur.execute("""
                UPDATE users
                SET referral_code=%s
                WHERE id=%s
            """, (
                code,
                row[0],
            ))

        # ----------------------------------------------------
        # ENSURE ACCOUNT FOR EVERY USER
        #
        # We do NOT use ON CONFLICT here because older databases
        # may not have the expected unique constraint.
        # ----------------------------------------------------

        cur.execute("""
            SELECT u.id
            FROM users u
            LEFT JOIN accounts a
                ON a.user_id=u.id
            WHERE a.user_id IS NULL
        """)

        missing_accounts = cur.fetchall()

        for row in missing_accounts:

            cur.execute("""
                INSERT INTO accounts (
                    user_id,
                    deposit_account,
                    income_account,
                    referral_account,
                    withdraw_account
                )
                VALUES (%s,%s,0,0,0)
            """, (
                row[0],
                STARTING_DEPOSIT_BALANCE,
            ))

        # ----------------------------------------------------
        # ADMIN ACCOUNT
        # ----------------------------------------------------

        admin_hash = generate_password_hash(
            ADMIN_PASSWORD
        )

        cur.execute("""
            SELECT id
            FROM admins
            WHERE username=%s
        """, (
            ADMIN_USERNAME,
        ))

        existing_admin = cur.fetchone()

        if existing_admin:

            cur.execute("""
                UPDATE admins
                SET password_hash=%s
                WHERE username=%s
            """, (
                admin_hash,
                ADMIN_USERNAME,
            ))

        else:

            cur.execute("""
                INSERT INTO admins (
                    username,
                    password_hash
                )
                VALUES (%s,%s)
            """, (
                ADMIN_USERNAME,
                admin_hash,
            ))

        # ----------------------------------------------------
        # INDEXES
        # ----------------------------------------------------

        indexes = [
            """
            CREATE INDEX IF NOT EXISTS idx_users_phone
            ON users(phone)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_users_referral
            ON users(referral_code)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_plans_user
            ON plans(user_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_transactions_user
            ON transactions(user_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_deposit_requests_user
            ON deposit_requests(user_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_deposit_requests_status
            ON deposit_requests(status)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_withdrawals_user
            ON withdrawal_requests(user_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_withdrawals_status
            ON withdrawal_requests(status)
            """,
        ]

        for statement in indexes:
            cur.execute(statement)

        conn.commit()

        print("=" * 60)
        print("DATABASE INITIALIZATION SUCCESS")
        print("Admin username:", ADMIN_USERNAME)
        print("=" * 60)

    except Exception as exc:

        conn.rollback()

        print("=" * 60)
        print("DATABASE INITIALIZATION ERROR")
        print(exc)
        print("=" * 60)

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

    account = query_one("""
        SELECT *
        FROM accounts
        WHERE user_id=%s
    """, (
        user_id,
    ))

    if account:
        return account

    # Create without relying on ON CONFLICT.

    conn = get_conn()
    cur = conn.cursor(
        cursor_factory=RealDictCursor
    )

    try:

        cur.execute("""
            SELECT *
            FROM accounts
            WHERE user_id=%s
            FOR UPDATE
        """, (
            user_id,
        ))

        existing = cur.fetchone()

        if not existing:

            cur.execute("""
                INSERT INTO accounts (
                    user_id,
                    deposit_account,
                    income_account,
                    referral_account,
                    withdraw_account
                )
                VALUES (%s,%s,0,0,0)
                RETURNING *
            """, (
                user_id,
                STARTING_DEPOSIT_BALANCE,
            ))

            existing = cur.fetchone()

        conn.commit()

        return existing

    except Exception:

        conn.rollback()
        raise

    finally:

        cur.close()
        conn.close()


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

    if session.get("admin_logged_in") is True:
        return redirect(url_for("admin_dashboard"))

    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


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
        """, (
            invite_code,
        ))

    if request.method == "POST":

        fullname = request.form.get(
            "fullname",
            "",
        ).strip()

        username = request.form.get(
            "username",
            "",
        ).strip()

        phone = request.form.get(
            "phone",
            "",
        ).strip()

        password = request.form.get(
            "password",
            "",
        )

        withdraw_password = request.form.get(
            "withdraw_password",
            "",
        )

        if not fullname or not username or not phone:

            flash(
                "Please complete all required fields.",
                "error",
            )

            return render_template(
                "register.html",
                invite_code=invite_code,
            )

        if not password:

            flash(
                "Please enter a password.",
                "error",
            )

            return render_template(
                "register.html",
                invite_code=invite_code,
            )

        if not withdraw_password:

            flash(
                "Please enter your withdrawal password.",
                "error",
            )

            return render_template(
                "register.html",
                invite_code=invite_code,
            )

        existing = query_one("""
            SELECT id
            FROM users
            WHERE username=%s
               OR phone=%s
        """, (
            username,
            phone,
        ))

        if existing:

            flash(
                "Username or phone number already exists.",
                "error",
            )

            return render_template(
                "register.html",
                invite_code=invite_code,
            )

        if invite_code and not referred_user:

            flash(
                "Invalid referral code.",
                "error",
            )

            return render_template(
                "register.html",
                invite_code=invite_code,
            )

        referral_code = generate_referral_code()

        conn = get_conn()
        cur = conn.cursor(
            cursor_factory=RealDictCursor
        )

        try:

            cur.execute("""
                INSERT INTO users (
                    username,
                    fullname,
                    phone,
                    password_hash,
                    withdraw_password_hash,
                    referral_code,
                    referred_by
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
            """, (
                username,
                fullname,
                phone,
                generate_password_hash(password),
                generate_password_hash(withdraw_password),
                referral_code,
                referred_user["referral_code"]
                if referred_user else None,
            ))

            user = cur.fetchone()

            cur.execute("""
                INSERT INTO accounts (
                    user_id,
                    deposit_account,
                    income_account,
                    referral_account,
                    withdraw_account
                )
                VALUES (%s,%s,0,0,0)
            """, (
                user["id"],
                STARTING_DEPOSIT_BALANCE,
            ))

            conn.commit()

        except Exception:

            conn.rollback()
            raise

        finally:

            cur.close()
            conn.close()

        flash(
            "Registration successful. Please log in.",
            "success",
        )

        return redirect(url_for("login"))

    return render_template(
        "register.html",
        invite_code=invite_code,
    )


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        phone = request.form.get(
            "phone",
            "",
        ).strip()

        password = request.form.get(
            "password",
            "",
        )

        user = query_one("""
            SELECT *
            FROM users
            WHERE phone=%s
        """, (
            phone,
        ))

        valid = False

        if user and user["password_hash"]:

            try:
                valid = check_password_hash(
                    user["password_hash"],
                    password,
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
            "error",
        )

    return render_template("login.html")


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
def dashboard():

    user = current_user()

    if not user:
        return redirect(url_for("login"))

    account = current_account(
        user["id"]
    )

    return render_template(
        "dashboard.html",
        user=user,
        account=account,
        plans=PLANS,
    )


# ============================================================
# DEPOSIT
# ============================================================

@app.route("/deposit", methods=["GET", "POST"])
def deposit():

    user = current_user()

    if not user:
        return redirect(url_for("login"))

    if request.method == "POST":

        amount = parse_amount(
            request.form.get(
                "amount",
                "0",
            )
        )

        phone = request.form.get(
            "phone",
            "",
        ).strip()

        payment_number = request.form.get(
            "payment_number",
            "0257425844",
        ).strip()

        screenshot = request.files.get(
            "screenshot"
        )

        if amount is None:

            flash(
                "Please enter a valid deposit amount.",
                "error",
            )

            return render_template(
                "deposit.html"
            )

        if amount < MIN_DEPOSIT:

            flash(
                f"Minimum demo deposit is GHS {MIN_DEPOSIT:.2f}.",
                "error",
            )

            return render_template(
                "deposit.html"
            )

        if not phone:

            flash(
                "Please enter your phone number.",
                "error",
            )

            return render_template(
                "deposit.html"
            )

        if not screenshot or not screenshot.filename:

            flash(
                "Please upload your payment screenshot.",
                "error",
            )

            return render_template(
                "deposit.html"
            )

        filename = screenshot.filename.lower()

        allowed_extensions = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }

        extension = None
        mime_type = None

        for ext, mime in allowed_extensions.items():

            if filename.endswith(ext):
                extension = ext
                mime_type = mime
                break

        if not extension:

            flash(
                "Only PNG, JPG, JPEG and WEBP images are allowed.",
                "error",
            )

            return render_template(
                "deposit.html"
            )

        # Read screenshot directly into memory.
        # It is NOT stored on the Render filesystem.

        try:

            screenshot_data = screenshot.read()

        except Exception:

            flash(
                "Unable to read the uploaded screenshot.",
                "error",
            )

            return render_template(
                "deposit.html"
            )

        if not screenshot_data:

            flash(
                "The uploaded screenshot is empty.",
                "error",
            )

            return render_template(
                "deposit.html"
            )

        if len(screenshot_data) > 5 * 1024 * 1024:

            flash(
                "Screenshot is too large. Maximum size is 5 MB.",
                "error",
            )

            return render_template(
                "deposit.html"
            )

        reference = generate_reference("DEP")

        conn = get_conn()
        cur = conn.cursor()

        try:

            cur.execute("""
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
            """, (
                user["id"],
                amount,
                payment_number,
                screenshot.filename,
                psycopg2.Binary(screenshot_data),
                mime_type,
                reference,
            ))

            deposit_id = cur.fetchone()[0]

            cur.execute("""
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
            """, (
                user["id"],
                amount,
                reference,
                "Demo deposit request #" + str(deposit_id),
            ))

            conn.commit()

        except Exception:

            conn.rollback()
            raise

        finally:

            cur.close()
            conn.close()

        flash(
            "Deposit request submitted successfully. "
            "Please wait for admin review.",
            "success",
        )

        return redirect(
            url_for("transaction_history")
        )

    return render_template(
        "deposit.html"
    )


# ============================================================
# DEPOSIT SCREENSHOT
# ============================================================

@app.route(
    "/admin/deposit-image/<int:deposit_id>"
)
def admin_deposit_image(deposit_id):

    if not admin_required():
        return redirect(
            url_for("admin_login")
        )

    deposit = query_one("""
        SELECT
            screenshot_data,
            screenshot_mime
        FROM deposit_requests
        WHERE id=%s
    """, (
        deposit_id,
    ))

    if not deposit:
        abort(404)

    if not deposit["screenshot_data"]:
        abort(404)

    from io import BytesIO

    return send_file(
        BytesIO(bytes(deposit["screenshot_data"])),
        mimetype=deposit["screenshot_mime"] or "image/jpeg",
        as_attachment=False,
        download_name=f"deposit_{deposit_id}.jpg",
    )


# ------------------------------------------------------------
# OLD SCREENSHOT URL COMPATIBILITY
#
# Existing admin templates may still contain:
# /uploads/deposits/<filename>
#
# We search PostgreSQL for that filename and serve the stored
# BYTEA image.
# ------------------------------------------------------------

@app.route(
    "/uploads/deposits/<path:filename>"
)
def uploaded_deposit_image(filename):

    if not admin_required():
        return redirect(
            url_for("admin_login")
        )

    deposit = query_one("""
        SELECT
            screenshot_data,
            screenshot_mime
        FROM deposit_requests
        WHERE screenshot=%s
        ORDER BY id DESC
        LIMIT 1
    """, (
        filename,
    ))

    if not deposit or not deposit["screenshot_data"]:
        abort(404)

    from io import BytesIO

    return send_file(
        BytesIO(bytes(deposit["screenshot_data"])),
        mimetype=deposit["screenshot_mime"] or "image/jpeg",
        as_attachment=False,
        download_name=filename,
    )


# ============================================================
# DEPOSIT SUCCESS COMPATIBILITY
# ============================================================

@app.route("/deposit_success")
def deposit_success():

    return redirect(
        url_for("deposit")
    )


# ============================================================
# BUY PLAN
# ============================================================

@app.route("/buy_plan/<int:plan_id>")
def buy_plan(plan_id):

    user = current_user()

    if not user:
        return redirect(url_for("login"))

    if plan_id not in PLANS:

        flash(
            "Plan not found.",
            "error",
        )

        return redirect(
            url_for("dashboard")
        )

    plan = PLANS[plan_id]

    account = current_account(
        user["id"]
    )

    balance = money(
        account["deposit_account"]
    )

    if balance < plan["investment"]:

        return render_template(
            "insufficient_balance.html",
            account=account,
            plan={
                "investment_amount":
                    plan["investment"],
            },
        )

    return render_template(
        "confirm_plan.html",
        user=user,
        account=account,
        plan={
            "id": plan_id,
            "plan_name": plan["name"],
            "investment_amount": plan["investment"],
            "daily_income": plan["daily"],
            "duration": plan["duration"],
        },
    )


# ============================================================
# CONFIRM PLAN
# ============================================================

@app.route(
    "/confirm_buy_plan/<int:plan_id>",
    methods=["POST"],
)
def confirm_buy_plan(plan_id):

    user = current_user()

    if not user:
        return redirect(url_for("login"))

    if plan_id not in PLANS:

        flash(
            "Plan not found.",
            "error",
        )

        return redirect(
            url_for("dashboard")
        )

    plan = PLANS[plan_id]

    conn = get_conn()
    cur = conn.cursor()

    try:

        # Lock account row to prevent simultaneous purchases.

        cur.execute("""
            SELECT deposit_account
            FROM accounts
            WHERE user_id=%s
            FOR UPDATE
        """, (
            user["id"],
        ))

        account = cur.fetchone()

        if not account:

            cur.execute("""
                INSERT INTO accounts (
                    user_id,
                    deposit_account,
                    income_account,
                    referral_account,
                    withdraw_account
                )
                VALUES (%s,%s,0,0,0)
            """, (
                user["id"],
                STARTING_DEPOSIT_BALANCE,
            ))

            deposit_balance = STARTING_DEPOSIT_BALANCE

        else:

            deposit_balance = money(
                account[0]
            )

        if deposit_balance < plan["investment"]:

            conn.rollback()

            flash(
                "Insufficient balance.",
                "error",
            )

            return redirect(
                url_for("dashboard")
            )

        cur.execute("""
            UPDATE accounts
            SET deposit_account =
                deposit_account - %s
            WHERE user_id=%s
        """, (
            plan["investment"],
            user["id"],
        ))

        started_at = utcnow()

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
                %s,%s,%s,%s,%s,%s,%s,NULL,TRUE
            )
        """, (
            user["id"],
            plan_id,
            plan["name"],
            plan["investment"],
            plan["daily"],
            plan["duration"],
            started_at,
        ))

        cur.execute("""
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
                'plan_purchase',
                %s,
                'successful',
                %s,
                %s
            )
        """, (
            user["id"],
            plan["investment"],
            generate_reference("PLAN"),
            "Demo plan purchase",
        ))

        conn.commit()

    except Exception:

        conn.rollback()
        raise

    finally:

        cur.close()
        conn.close()

    flash(
        "Demo plan activated successfully.",
        "success",
    )

    return redirect(
        url_for("my_plan")
    )


# ============================================================
# MY PLAN
# ============================================================

@app.route(
    "/my_plan",
    methods=["GET", "POST"],
)
def my_plan():

    user = current_user()

    if not user:
        return redirect(url_for("login"))

    # --------------------------------------------------------
    # POST CLAIM
    # --------------------------------------------------------

    if request.method == "POST":

        conn = get_conn()
        cur = conn.cursor(
            cursor_factory=RealDictCursor
        )

        try:

            cur.execute("""
                SELECT *
                FROM plans
                WHERE user_id=%s
                AND active=TRUE
                ORDER BY id DESC
                LIMIT 1
                FOR UPDATE
            """, (
                user["id"],
            ))

            plan = cur.fetchone()

            if not plan:

                conn.rollback()

                flash(
                    "No active demo plan found.",
                    "error",
                )

                return redirect(
                    url_for("my_plan")
                )

            now = utcnow()

            started_at = plan["started_at"]

            end_time = (
                started_at
                + timedelta(
                    days=int(plan["duration"])
                )
            )

            if now >= end_time:

                cur.execute("""
                    UPDATE plans
                    SET active=FALSE
                    WHERE id=%s
                """, (
                    plan["id"],
                ))

                conn.commit()

                flash(
                    "Your demo plan has ended.",
                    "error",
                )

                return redirect(
                    url_for("my_plan")
                )

            last_claim_at = plan["last_claim_at"]

            if last_claim_at is None:

                allowed_time = (
                    started_at
                    + timedelta(hours=24)
                )

            else:

                allowed_time = (
                    last_claim_at
                    + timedelta(hours=24)
                )

            if now < allowed_time:

                conn.rollback()

                remaining = int(
                    (
                        allowed_time - now
                    ).total_seconds()
                )

                hours = remaining // 3600
                minutes = (
                    remaining % 3600
                ) // 60

                flash(
                    f"Next claim is available in "
                    f"{hours}h {minutes}m.",
                    "error",
                )

                return redirect(
                    url_for("my_plan")
                )

            daily_income = money(
                plan["daily_income"]
            )

            # Lock account.

            cur.execute("""
                SELECT user_id
                FROM accounts
                WHERE user_id=%s
                FOR UPDATE
            """, (
                user["id"],
            ))

            account = cur.fetchone()

            if not account:

                cur.execute("""
                    INSERT INTO accounts (
                        user_id,
                        deposit_account,
                        income_account,
                        referral_account,
                        withdraw_account
                    )
                    VALUES (%s,%s,0,0,0)
                """, (
                    user["id"],
                    STARTING_DEPOSIT_BALANCE,
                ))

            cur.execute("""
                UPDATE accounts
                SET income_account =
                        COALESCE(income_account,0)
                        + %s,
                    withdraw_account =
                        COALESCE(withdraw_account,0)
                        + %s
                WHERE user_id=%s
            """, (
                daily_income,
                daily_income,
                user["id"],
            ))

            cur.execute("""
                UPDATE plans
                SET last_claim_at=%s
                WHERE id=%s
            """, (
                now,
                plan["id"],
            ))

            cur.execute("""
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
                    'income_claim',
                    %s,
                    'successful',
                    %s,
                    'Demo daily income claim'
                )
            """, (
                user["id"],
                daily_income,
                generate_reference("INC"),
            ))

            conn.commit()

            flash(
                "Demo daily income claimed successfully.",
                "success",
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

    # --------------------------------------------------------
    # GET
    # --------------------------------------------------------

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
    seconds_remaining = 0
    cycle_ended = False

    if plan:

        now = utcnow()

        started_at = plan["started_at"]

        end_time = (
            started_at
            + timedelta(
                days=int(plan["duration"])
            )
        )

        if now >= end_time:

            execute("""
                UPDATE plans
                SET active=FALSE
                WHERE id=%s
            """, (
                plan["id"],
            ))

            plan = None
            cycle_ended = True

        else:

            last_claim_at = plan["last_claim_at"]

            if last_claim_at is None:

                next_claim_time = (
                    started_at
                    + timedelta(hours=24)
                )

            else:

                next_claim_time = (
                    last_claim_at
                    + timedelta(hours=24)
                )

            if now >= next_claim_time:

                can_claim = True

            else:

                seconds_remaining = max(
                    0,
                    int(
                        (
                            next_claim_time - now
                        ).total_seconds()
                    ),
                )

    return render_template(
        "my_plan.html",
        user_plan=plan,
        can_claim=can_claim,
        seconds_remaining=seconds_remaining,
        cycle_ended=cycle_ended,
    )


# ============================================================
# WITHDRAW
# ============================================================

@app.route(
    "/withdraw",
    methods=["GET"],
)
def withdraw():

    user = current_user()

    if not user:
        return redirect(url_for("login"))

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
        accounts=accounts,
    )


# ============================================================
# BIND ACCOUNT
# ============================================================

@app.route(
    "/bind_account",
    methods=["GET", "POST"],
)
def bind_account():

    user = current_user()

    if not user:
        return redirect(url_for("login"))

    if request.method == "POST":

        account_name = request.form.get(
            "account_name",
            "",
        ).strip()

        phone = request.form.get(
            "phone",
            "",
        ).strip()

        network = request.form.get(
            "network",
            "",
        ).strip()

        if (
            not account_name
            or not phone
            or not network
        ):

            flash(
                "Please complete all account details.",
                "error",
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
                network,
            ))

            flash(
                "Withdrawal account saved.",
                "success",
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
        accounts=accounts,
    )


# ============================================================
# REQUEST WITHDRAWAL
# ============================================================

@app.route(
    "/request_withdrawal",
    methods=["POST"],
)
def request_withdrawal():

    user = current_user()

    if not user:
        return redirect(url_for("login"))

    amount = parse_amount(
        request.form.get(
            "amount",
            "0",
        )
    )

    password = request.form.get(
        "password",
        "",
    )

    account_id = request.form.get(
        "account_id"
    )

    if amount is None or amount < MIN_WITHDRAWAL:

        flash(
            f"Minimum demo withdrawal is "
            f"GHS {MIN_WITHDRAWAL:.2f}.",
            "error",
        )

        return redirect(
            url_for("withdraw")
        )

    if not user["withdraw_password_hash"]:

        flash(
            "Withdrawal password is not configured.",
            "error",
        )

        return redirect(
            url_for("withdraw")
        )

    try:

        valid = check_password_hash(
            user["withdraw_password_hash"],
            password,
        )

    except Exception:

        valid = False

    if not valid:

        flash(
            "Invalid withdrawal password.",
            "error",
        )

        return redirect(
            url_for("withdraw")
        )

    selected_account_id = None

    if account_id:

        selected_account = query_one("""
            SELECT id
            FROM withdrawal_accounts
            WHERE id=%s
            AND user_id=%s
        """, (
            account_id,
            user["id"],
        ))

        if not selected_account:

            flash(
                "Invalid withdrawal account.",
                "error",
            )

            return redirect(
                url_for("withdraw")
            )

        selected_account_id = selected_account["id"]

    conn = get_conn()
    cur = conn.cursor()

    try:

        # Lock account before checking balance.

        cur.execute("""
            SELECT withdraw_account
            FROM accounts
            WHERE user_id=%s
            FOR UPDATE
        """, (
            user["id"],
        ))

        account = cur.fetchone()

        if not account:

            conn.rollback()

            flash(
                "Account balance not found.",
                "error",
            )

            return redirect(
                url_for("withdraw")
            )

        balance = money(account[0])

        if balance < amount:

            conn.rollback()

            flash(
                "Insufficient withdrawal balance.",
                "error",
            )

            return redirect(
                url_for("withdraw")
            )

        # Reserve the withdrawal amount.

        cur.execute("""
            UPDATE accounts
            SET withdraw_account =
                withdraw_account - %s
            WHERE user_id=%s
            AND withdraw_account >= %s
        """, (
            amount,
            user["id"],
            amount,
        ))

        if cur.rowcount != 1:

            conn.rollback()

            flash(
                "Insufficient withdrawal balance.",
                "error",
            )

            return redirect(
                url_for("withdraw")
            )

        withdrawal_reference = generate_reference(
            "WDR"
        )

        cur.execute("""
            INSERT INTO withdrawal_requests (
                user_id,
                amount,
                account_id,
                status
            )
            VALUES (
                %s,%s,%s,'pending'
            )
            RETURNING id
        """, (
            user["id"],
            amount,
            selected_account_id,
        ))

        withdrawal_id = cur.fetchone()[0]

        cur.execute("""
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
                'withdrawal',
                %s,
                'pending',
                %s,
                %s
            )
        """, (
            user["id"],
            amount,
            withdrawal_reference,
            "Demo withdrawal request #"
            + str(withdrawal_id),
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
        "success",
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
        return redirect(url_for("login"))

    transactions = query_all("""
        SELECT *
        FROM transactions
        WHERE user_id=%s
        ORDER BY created_at DESC, id DESC
    """, (
        user["id"],
    ))

    return render_template(
        "transaction_history.html",
        transactions=transactions,
    )


# ============================================================
# TEAM
# ============================================================

@app.route("/team")
def team():

    user = current_user()

    if not user:
        return redirect(url_for("login"))

    members = query_all("""
        SELECT
            id,
            username,
            fullname,
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
        money(account["referral_account"])
        if account
        else Decimal("0")
    )

    return render_template(
        "team.html",
        user=user,
        members=members,
        total_team=len(members),
        referral_income=referral_income,
    )


# ============================================================
# SUPPORT
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
        return redirect(url_for("login"))

    account = current_account(
        user["id"]
    )

    return render_template(
        "profile.html",
        user=user,
        deposit_balance=account["deposit_account"],
        withdraw_balance=account["withdraw_account"],
        income_balance=account["income_account"],
        referral_balance=account["referral_account"],
    )


# ============================================================
# CHANGE LOGIN PASSWORD
# ============================================================

@app.route(
    "/change_login_password",
    methods=["GET", "POST"],
)
def change_login_password():

    user = current_user()

    if not user:
        return redirect(url_for("login"))

    if request.method == "POST":

        current_password = request.form.get(
            "current_password",
            "",
        )

        new_password = request.form.get(
            "new_password",
            "",
        )

        confirm_password = request.form.get(
            "confirm_password",
            "",
        )

        valid = False

        try:

            valid = check_password_hash(
                user["password_hash"],
                current_password,
            )

        except Exception:

            valid = False

        if not valid:

            flash(
                "Current password is incorrect.",
                "error",
            )

            return render_template(
                "change_login_password.html"
            )

        if len(new_password) < 6:

            flash(
                "New password must contain at least 6 characters.",
                "error",
            )

            return render_template(
                "change_login_password.html"
            )

        if new_password != confirm_password:

            flash(
                "New passwords do not match.",
                "error",
            )

            return render_template(
                "change_login_password.html"
            )

        execute("""
            UPDATE users
            SET password_hash=%s
            WHERE id=%s
        """, (
            generate_password_hash(new_password),
            user["id"],
        ))

        flash(
            "Login password changed successfully.",
            "success",
        )

        return redirect(
            url_for("profile")
        )

    return render_template(
        "change_login_password.html"
    )


# ============================================================
# CHANGE WITHDRAWAL PASSWORD
# ============================================================

@app.route(
    "/change_withdraw_password",
    methods=["GET", "POST"],
)
def change_withdraw_password():

    user = current_user()

    if not user:
        return redirect(url_for("login"))

    if request.method == "POST":

        current_password = request.form.get(
            "current_password",
            "",
        )

        new_password = request.form.get(
            "new_password",
            "",
        )

        confirm_password = request.form.get(
            "confirm_password",
            "",
        )

        valid = False

        try:

            valid = check_password_hash(
                user["withdraw_password_hash"],
                current_password,
            )

        except Exception:

            valid = False

        if not valid:

            flash(
                "Current withdrawal password is incorrect.",
                "error",
            )

            return render_template(
                "change_withdraw_password.html"
            )

        if len(new_password) < 4:

            flash(
                "New withdrawal password must contain at least 4 characters.",
                "error",
            )

            return render_template(
                "change_withdraw_password.html"
            )

        if new_password != confirm_password:

            flash(
                "New passwords do not match.",
                "error",
            )

            return render_template(
                "change_withdraw_password.html"
            )

        execute("""
            UPDATE users
            SET withdraw_password_hash=%s
            WHERE id=%s
        """, (
            generate_password_hash(new_password),
            user["id"],
        ))

        flash(
            "Withdrawal password changed successfully.",
            "success",
        )

        return redirect(
            url_for("profile")
        )

    return render_template(
        "change_withdraw_password.html"
    )


# ============================================================
# ADMIN AUTHORIZATION
# ============================================================

def admin_required():
    return session.get(
        "admin_logged_in"
    ) is True


# ============================================================
# ADMIN LOGIN
# ============================================================

@app.route(
    "/admin/login",
    methods=["GET", "POST"],
)
def admin_login():

    if request.method == "POST":

        username = request.form.get(
            "username",
            "",
        ).strip()

        password = request.form.get(
            "password",
            "",
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

            try:

                valid = check_password_hash(
                    admin["password_hash"],
                    password,
                )

            except Exception:

                valid = False

        if valid:

            session.clear()

            session["admin_logged_in"] = True

            flash(
                "Administrator login successful.",
                "success",
            )

            return redirect(
                url_for("admin_dashboard")
            )

        flash(
            "Invalid administrator credentials.",
            "error",
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
        None,
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
        pending_withdrawals=pending_withdrawals,
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
        users=users,
    )


# ============================================================
# ADMIN MANAGE USER
# ============================================================

@app.route(
    "/admin/user/<int:user_id>",
    methods=["GET", "POST"],
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
            "",
        )

        # ----------------------------------------------------
        # BALANCE ACTIONS
        # ----------------------------------------------------

        balance_actions = {
            "add_deposit": (
                "deposit_account",
                1,
            ),
            "deduct_deposit": (
                "deposit_account",
                -1,
            ),
            "add_withdraw": (
                "withdraw_account",
                1,
            ),
            "deduct_withdraw": (
                "withdraw_account",
                -1,
            ),
            "add_income": (
                "income_account",
                1,
            ),
            "deduct_income": (
                "income_account",
                -1,
            ),
            "add_referral": (
                "referral_account",
                1,
            ),
            "deduct_referral": (
                "referral_account",
                -1,
            ),
        }

        if action in balance_actions:

            amount = parse_amount(
                request.form.get(
                    "amount",
                    "0",
                )
            )

            if amount is None or amount <= 0:

                flash(
                    "Amount must be greater than zero.",
                    "error",
                )

                return redirect(
                    url_for(
                        "admin_manage_user",
                        user_id=user_id,
                    )
                )

            column, multiplier = balance_actions[
                action
            ]

            conn = get_conn()
            cur = conn.cursor()

            try:

                # Lock account.

                cur.execute("""
                    SELECT user_id
                    FROM accounts
                    WHERE user_id=%s
                    FOR UPDATE
                """, (
                    user_id,
                ))

                account_exists = cur.fetchone()

                if not account_exists:

                    cur.execute("""
                        INSERT INTO accounts (
                            user_id,
                            deposit_account,
                            income_account,
                            referral_account,
                            withdraw_account
                        )
                        VALUES (%s,%s,0,0,0)
                    """, (
                        user_id,
                        STARTING_DEPOSIT_BALANCE,
                    ))

                if multiplier == 1:

                    cur.execute(
                        f"""
                        UPDATE accounts
                        SET {column} =
                            COALESCE({column},0) + %s
                        WHERE user_id=%s
                        """,
                        (
                            amount,
                            user_id,
                        ),
                    )

                else:

                    cur.execute(
                        f"""
                        UPDATE accounts
                        SET {column} =
                            GREATEST(
                                0,
                                COALESCE({column},0) - %s
                            )
                        WHERE user_id=%s
                        """,
                        (
                            amount,
                            user_id,
                        ),
                    )

                # Audit transaction.

                transaction_type = (
                    "admin_balance_adjustment"
                )

                description = (
                    "Admin adjustment: "
                    + action
                )

                cur.execute("""
                    INSERT INTO transactions (
                        user_id,
                        transaction_type,
                        amount,
                        status,
                        reference,
                        description
                    )
                    VALUES (
                        %s,%s,%s,'successful',%s,%s
                    )
                """, (
                    user_id,
                    transaction_type,
                    amount,
                    generate_reference("ADM"),
                    description,
                ))

                conn.commit()

            except Exception:

                conn.rollback()
                raise

            finally:

                cur.close()
                conn.close()

            flash(
                "User balance updated successfully.",
                "success",
            )

            return redirect(
                url_for(
                    "admin_manage_user",
                    user_id=user_id,
                )
            )

        # ----------------------------------------------------
        # CHANGE LOGIN PASSWORD
        # ----------------------------------------------------

        if action == "change_login_password":

            new_password = request.form.get(
                "new_password",
                "",
            )

            if len(new_password) < 6:

                flash(
                    "Login password must contain at least 6 characters.",
                    "error",
                )

                return redirect(
                    url_for(
                        "admin_manage_user",
                        user_id=user_id,
                    )
                )

            execute("""
                UPDATE users
                SET password_hash=%s
                WHERE id=%s
            """, (
                generate_password_hash(new_password),
                user_id,
            ))

            flash(
                "Login password updated successfully.",
                "success",
            )

            return redirect(
                url_for(
                    "admin_manage_user",
                    user_id=user_id,
                )
            )

        # ----------------------------------------------------
        # CHANGE WITHDRAWAL PASSWORD
        # ----------------------------------------------------

        if action == "change_withdraw_password":

            new_password = request.form.get(
                "new_password",
                "",
            )

            if len(new_password) < 4:

                flash(
                    "Withdrawal password must contain at least 4 characters.",
                    "error",
                )

                return redirect(
                    url_for(
                        "admin_manage_user",
                        user_id=user_id,
                    )
                )

            execute("""
                UPDATE users
                SET withdraw_password_hash=%s
                WHERE id=%s
            """, (
                generate_password_hash(new_password),
                user_id,
            ))

            flash(
                "Withdrawal password updated successfully.",
                "success",
            )

            return redirect(
                url_for(
                    "admin_manage_user",
                    user_id=user_id,
                )
            )

        flash(
            "Unknown admin action.",
            "error",
        )

        return redirect(
            url_for(
                "admin_manage_user",
                user_id=user_id,
            )
        )

    account = current_account(
        user_id
    )

    return render_template(
        "admin_manage_user.html",
        user=user,
        account=account,
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
        ORDER BY d.created_at DESC, d.id DESC
    """)

    return render_template(
        "admin_deposit.html",
        deposits=deposits,
    )


# ============================================================
# ADMIN DEPOSIT ACTION
# ============================================================

@app.route(
    "/admin/deposit/<int:deposit_id>/<action>",
    methods=["POST"],
)
def admin_deposit_action(
    deposit_id,
    action,
):

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    if action not in (
        "approve",
        "reject",
    ):

        flash(
            "Invalid deposit action.",
            "error",
        )

        return redirect(
            url_for("admin_deposits")
        )

    conn = get_conn()
    cur = conn.cursor(
        cursor_factory=RealDictCursor
    )

    try:

        # Lock deposit request.

        cur.execute("""
            SELECT
                id,
                user_id,
                amount,
                reference,
                status
            FROM deposit_requests
            WHERE id=%s
            FOR UPDATE
        """, (
            deposit_id,
        ))

        deposit = cur.fetchone()

        if not deposit:

            conn.rollback()

            flash(
                "Deposit request not found.",
                "error",
            )

            return redirect(
                url_for("admin_deposits")
            )

        if deposit["status"] != "pending":

            conn.rollback()

            flash(
                "This deposit has already been reviewed.",
                "error",
            )

            return redirect(
                url_for("admin_deposits")
            )

        user_id = deposit["user_id"]
        amount = money(deposit["amount"])
        reference = deposit["reference"]

        # ----------------------------------------------------
        # APPROVE
        # ----------------------------------------------------

        if action == "approve":

            # Find and lock account.

            cur.execute("""
                SELECT *
                FROM accounts
                WHERE user_id=%s
                FOR UPDATE
            """, (
                user_id,
            ))

            account = cur.fetchone()

            if account:

                cur.execute("""
                    UPDATE accounts
                    SET deposit_account =
                        COALESCE(deposit_account,0)
                        + %s
                    WHERE user_id=%s
                """, (
                    amount,
                    user_id,
                ))

            else:

                # Account does not exist.
                # Insert directly because user_id is primary key.

                cur.execute("""
                    INSERT INTO accounts (
                        user_id,
                        deposit_account,
                        income_account,
                        referral_account,
                        withdraw_account
                    )
                    VALUES (%s,%s,0,0,0)
                """, (
                    user_id,
                    amount,
                ))

            cur.execute("""
                UPDATE deposit_requests
                SET status='approved'
                WHERE id=%s
            """, (
                deposit_id,
            ))

            if reference:

                cur.execute("""
                    UPDATE transactions
                    SET status='successful'
                    WHERE user_id=%s
                    AND transaction_type='deposit'
                    AND reference=%s
                    AND status='pending'
                """, (
                    user_id,
                    reference,
                ))

            else:

                cur.execute("""
                    UPDATE transactions
                    SET status='successful'
                    WHERE id = (
                        SELECT id
                        FROM transactions
                        WHERE user_id=%s
                        AND transaction_type='deposit'
                        AND status='pending'
                        ORDER BY created_at DESC, id DESC
                        LIMIT 1
                    )
                """, (
                    user_id,
                ))

            flash(
                f"Demo deposit of GHS {amount:.2f} "
                "approved successfully.",
                "success",
            )

        # ----------------------------------------------------
        # REJECT
        # ----------------------------------------------------

        else:

            cur.execute("""
                UPDATE deposit_requests
                SET status='rejected'
                WHERE id=%s
            """, (
                deposit_id,
            ))

            if reference:

                cur.execute("""
                    UPDATE transactions
                    SET status='failed'
                    WHERE user_id=%s
                    AND transaction_type='deposit'
                    AND reference=%s
                    AND status='pending'
                """, (
                    user_id,
                    reference,
                ))

            else:

                cur.execute("""
                    UPDATE transactions
                    SET status='failed'
                    WHERE id = (
                        SELECT id
                        FROM transactions
                        WHERE user_id=%s
                        AND transaction_type='deposit'
                        AND status='pending'
                        ORDER BY created_at DESC, id DESC
                        LIMIT 1
                    )
                """, (
                    user_id,
                ))

            flash(
                f"Demo deposit of GHS {amount:.2f} "
                "rejected.",
                "success",
            )

        conn.commit()

    except Exception:

        conn.rollback()

        app.logger.exception(
            "ADMIN DEPOSIT ACTION ERROR"
        )

        flash(
            "Unable to process the deposit. Please try again.",
            "error",
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
        ORDER BY w.created_at DESC, w.id DESC
    """)

    return render_template(
        "admin_withdraw.html",
        withdrawals=withdrawals,
    )


# ============================================================
# ADMIN WITHDRAWAL ACTION
# ============================================================

@app.route(
    "/admin/withdraw/<int:withdrawal_id>/<action>",
    methods=["POST"],
)
def admin_withdraw_action(
    withdrawal_id,
    action,
):

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    if action not in {
        "approve",
        "reject",
    }:

        flash(
            "Invalid withdrawal action.",
            "error",
        )

        return redirect(
            url_for("admin_withdrawals")
        )

    conn = get_conn()
    cur = conn.cursor(
        cursor_factory=RealDictCursor
    )

    try:

        cur.execute("""
            SELECT *
            FROM withdrawal_requests
            WHERE id=%s
            FOR UPDATE
        """, (
            withdrawal_id,
        ))

        withdrawal = cur.fetchone()

        if not withdrawal:

            conn.rollback()

            flash(
                "Withdrawal request not found.",
                "error",
            )

            return redirect(
                url_for("admin_withdrawals")
            )

        if withdrawal["status"] != "pending":

            conn.rollback()

            flash(
                "Withdrawal request is no longer pending.",
                "error",
            )

            return redirect(
                url_for("admin_withdrawals")
            )

        user_id = withdrawal["user_id"]
        amount = money(withdrawal["amount"])

        if action == "approve":

            cur.execute("""
                UPDATE withdrawal_requests
                SET status='approved'
                WHERE id=%s
            """, (
                withdrawal_id,
            ))

            # Find the transaction associated with this request
            # using the closest pending withdrawal transaction.

            cur.execute("""
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
            """, (
                user_id,
                amount,
            ))

            flash(
                "Withdrawal approved successfully.",
                "success",
            )

        else:

            # Return the reserved amount to the user.

            cur.execute("""
                SELECT user_id
                FROM accounts
                WHERE user_id=%s
                FOR UPDATE
            """, (
                user_id,
            ))

            account = cur.fetchone()

            if account:

                cur.execute("""
                    UPDATE accounts
                    SET withdraw_account =
                        COALESCE(withdraw_account,0)
                        + %s
                    WHERE user_id=%s
                """, (
                    amount,
                    user_id,
                ))

            else:

                cur.execute("""
                    INSERT INTO accounts (
                        user_id,
                        deposit_account,
                        income_account,
                        referral_account,
                        withdraw_account
                    )
                    VALUES (%s,0,0,0,%s)
                """, (
                    user_id,
                    amount,
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
            """, (
                user_id,
                amount,
            ))

            flash(
                "Withdrawal rejected and balance restored.",
                "success",
            )

        conn.commit()

    except Exception:

        conn.rollback()

        app.logger.exception(
            "ADMIN WITHDRAWAL ACTION ERROR"
        )

        flash(
            "Unable to process the withdrawal.",
            "error",
        )

    finally:

        cur.close()
        conn.close()

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
        ORDER BY wa.created_at DESC, wa.id DESC
    """)

    return render_template(
        "admin_bind_accounts.html",
        accounts=accounts,
    )


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(413)
def file_too_large(error):

    flash(
        "Screenshot is too large. Maximum size is 5 MB.",
        "error",
    )

    return redirect(
        url_for("deposit")
    )


@app.errorhandler(404)
def not_found(error):

    return "Page not found", 404


@app.errorhandler(500)
def server_error(error):

    app.logger.exception(
        "INTERNAL SERVER ERROR"
    )

    return (
        "An internal server error occurred.",
        500,
    )


# ============================================================
# MAX UPLOAD SIZE
# ============================================================

app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

# Render/Gunicorn imports app.py, so this initializes the
# PostgreSQL schema before serving requests.

with app.app_context():
    init_db()


# ============================================================
# LOCAL DEVELOPMENT
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "5000",
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
    )
