import os
import uuid
from io import BytesIO
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

============================================================

APP CONFIGURATION

============================================================

app = Flask(name)

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

app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

============================================================

DEMO SETTINGS

============================================================

MIN_DEPOSIT = Decimal("45.00")
MIN_WITHDRAWAL = Decimal("30.00")

STARTING_DEPOSIT_BALANCE = Decimal("5.00")

============================================================

DEMO PLANS

============================================================

PLANS = {
1: {
"name": "Zenith 1",
"investment": Decimal("50.00"),
"daily": Decimal("8.00"),
"duration": 30,
},
2: {
"name": "Zenith 2",
"investment": Decimal("100.00"),
"daily": Decimal("20.00"),
"duration": 30,
},
3: {
"name": "Zenith 3",
"investment": Decimal("200.00"),
"daily": Decimal("40.00"),
"duration": 30,
},
4: {
"name": "Zenith 4",
"investment": Decimal("300.00"),
"daily": Decimal("65.00"),
"duration": 30,
},
5: {
"name": "Zenith 5",
"investment": Decimal("500.00"),
"daily": Decimal("100.00"),
"duration": 30,
},
6: {
"name": "Zenith 6",
"investment": Decimal("600.00"),
"daily": Decimal("200.00"),
"duration": 30,
},
7: {
"name": "Zenith 7",
"investment": Decimal("1000.00"),
"daily": Decimal("360.00"),
"duration": 30,
},
}

============================================================

GENERAL HELPERS

============================================================

def utcnow():
"""Return naive UTC datetime for PostgreSQL TIMESTAMP fields."""
return datetime.utcnow()

def money(value):
"""Safely convert database values to Decimal."""
if value is None:
return Decimal("0.00")

try:  
    return Decimal(str(value))  
except Exception:  
    return Decimal("0.00")

def parse_amount(value):
"""Parse and normalize a positive monetary amount."""
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
return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"

============================================================

DATABASE

============================================================

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
cur = conn.cursor(cursor_factory=RealDictCursor)

try:  
    cur.execute(sql, params)  
    return cur.fetchone()  
finally:  
    cur.close()  
    conn.close()

def query_all(sql, params=()):
conn = get_conn()
cur = conn.cursor(cursor_factory=RealDictCursor)

try:  
    cur.execute(sql, params)  
    return cur.fetchall()  
finally:  
    cur.close()  
    conn.close()

def execute(sql, params=(), fetchone=False):
conn = get_conn()
cur = conn.cursor(cursor_factory=RealDictCursor)

try:  
    cur.execute(sql, params)  

    result = cur.fetchone() if fetchone else None  

    conn.commit()  
    return result  

except Exception:  
    conn.rollback()  
    raise  

finally:  
    cur.close()  
    conn.close()

============================================================

DATABASE INITIALIZATION

============================================================

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

    # Legacy password columns.  
    for column in [  
        "login_password",  
        "password",  
        "withdraw_password",  
        "withdrawal_password",  
    ]:  
        cur.execute(  
            """  
            SELECT EXISTS (  
                SELECT 1  
                FROM information_schema.columns  
                WHERE table_schema = 'public'  
                AND table_name = 'users'  
                AND column_name = %s  
            )  
            """,  
            (column,),  
        )  

        exists = cur.fetchone()[0]  

        if exists:  
            try:  
                cur.execute(  
                    f"""  
                    ALTER TABLE users  
                    ALTER COLUMN {column}  
                    DROP NOT NULL  
                    """  
                )  
            except Exception:  
                conn.rollback()  

    # Copy old password column where needed.  
    cur.execute("""  
        SELECT EXISTS (  
            SELECT 1  
            FROM information_schema.columns  
            WHERE table_schema='public'  
            AND table_name='users'  
            AND column_name='password'  
        )  
    """)  

    if cur.fetchone()[0]:  
        cur.execute("""  
            UPDATE users  
            SET password_hash = password  
            WHERE (password_hash IS NULL OR password_hash = '')  
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

    for column, definition in {  
        "deposit_account": "NUMERIC(14,2) DEFAULT 5.00",  
        "income_account": "NUMERIC(14,2) DEFAULT 0",  
        "referral_account": "NUMERIC(14,2) DEFAULT 0",  
        "withdraw_account": "NUMERIC(14,2) DEFAULT 0",  
    }.items():  

        cur.execute(  
            f"""  
            ALTER TABLE accounts  
            ADD COLUMN IF NOT EXISTS {column} {definition}  
            """  
        )  

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

    for column, definition in {  
        "payment_number": "VARCHAR(80)",  
        "screenshot": "TEXT",  
        "screenshot_data": "BYTEA",  
        "screenshot_mime": "VARCHAR(100)",  
        "reference": "VARCHAR(200)",  
        "status": "VARCHAR(40) DEFAULT 'pending'",  
    }.items():  

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
    # REFERRAL CODES  
    # ----------------------------------------------------  

    cur.execute("""  
        SELECT id  
        FROM users  
        WHERE referral_code IS NULL  
           OR referral_code = ''  
    """)  

    for row in cur.fetchall():  
        cur.execute(  
            """  
            UPDATE users  
            SET referral_code=%s  
            WHERE id=%s  
            """,  
            (  
                generate_referral_code(),  
                row[0],  
            ),  
        )  

    # ----------------------------------------------------  
    # CREATE MISSING ACCOUNTS  
    # ----------------------------------------------------  

    cur.execute("""  
        SELECT u.id  
        FROM users u  
        LEFT JOIN accounts a  
            ON a.user_id = u.id  
        WHERE a.user_id IS NULL  
    """)  

    for row in cur.fetchall():  
        cur.execute(  
            """  
            INSERT INTO accounts (  
                user_id,  
                deposit_account,  
                income_account,  
                referral_account,  
                withdraw_account  
            )  
            VALUES (%s,%s,0,0,0)  
            """,  
            (  
                row[0],  
                STARTING_DEPOSIT_BALANCE,  
            ),  
        )  

    # ----------------------------------------------------  
    # ADMIN  
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
        (ADMIN_USERNAME,),  
    )  

    existing_admin = cur.fetchone()  

    if existing_admin:  
        cur.execute(  
            """  
            UPDATE admins  
            SET password_hash=%s  
            WHERE username=%s  
            """,  
            (  
                admin_hash,  
                ADMIN_USERNAME,  
            ),  
        )  
    else:  
        cur.execute(  
            """  
            INSERT INTO admins (  
                username,  
                password_hash  
            )  
            VALUES (%s,%s)  
            """,  
            (  
                ADMIN_USERNAME,  
                admin_hash,  
            ),  
        )  

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

============================================================

USER HELPERS

============================================================

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
    (user_id,),  
)

def current_account(user_id):
account = query_one(
"""
SELECT *
FROM accounts
WHERE user_id=%s
""",
(user_id,),
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
    VALUES (%s,%s,0,0,0)  
    ON CONFLICT (user_id) DO NOTHING  
    """,  
    (  
        user_id,  
        STARTING_DEPOSIT_BALANCE,  
    ),  
)  

return query_one(  
    """  
    SELECT *  
    FROM accounts  
    WHERE user_id=%s  
    """,  
    (user_id,),  
)

@app.context_processor
def inject_user():
return {
"logged_user": current_user()
}

============================================================

HOME

============================================================

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

============================================================

REGISTER

============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

invite_code = (  
    request.args.get("ref", "").strip()  
    or request.form.get("referred_by", "").strip()  
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

    fullname = request.form.get(  
        "fullname", ""  
    ).strip()  

    username = request.form.get(  
        "username", ""  
    ).strip()  

    phone = request.form.get(  
        "phone", ""  
    ).strip()  

    password = request.form.get(  
        "password", ""  
    )  

    withdraw_password = request.form.get(  
        "withdraw_password", ""  
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

    if len(password) < 6:  
        flash(  
            "Password must contain at least 6 characters.",  
            "error",  
        )  

        return render_template(  
            "register.html",  
            invite_code=invite_code,  
        )  

    if len(withdraw_password) < 4:  
        flash(  
            "Withdrawal password must contain at least 4 characters.",  
            "error",  
        )  

        return render_template(  
            "register.html",  
            invite_code=invite_code,  
        )  

    existing = query_one(  
        """  
        SELECT id  
        FROM users  
        WHERE username=%s  
           OR phone=%s  
        """,  
        (  
            username,  
            phone,  
        ),  
    )  

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

        cur.execute(  
            """  
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
            """,  
            (  
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
                ),  
            ),  
        )  

        user = cur.fetchone()  

        cur.execute(  
            """  
            INSERT INTO accounts (  
                user_id,  
                deposit_account,  
                income_account,  
                referral_account,  
                withdraw_account  
            )  
            VALUES (%s,%s,0,0,0)  
            """,  
            (  
                user["id"],  
                STARTING_DEPOSIT_BALANCE,  
            ),  
        )  

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

    return redirect(  
        url_for("login")  
    )  

return render_template(  
    "register.html",  
    invite_code=invite_code,  
)

============================================================

LOGIN

============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

if request.method == "POST":  

    phone = request.form.get(  
        "phone", ""  
    ).strip()  

    password = request.form.get(  
        "password", ""  
    )  

    user = query_one(  
        """  
        SELECT *  
        FROM users  
        WHERE phone=%s  
        """,  
        (phone,),  
    )  

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

============================================================

LOGOUT

============================================================

@app.route("/logout")
def logout():

session.clear()  

return redirect(  
    url_for("login")  
)

============================================================

DASHBOARD

============================================================

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
    plans=PLANS,  
)

============================================================

DEPOSIT

============================================================

@app.route("/deposit", methods=["GET", "POST"])
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

    allowed_extensions = {  
        ".png": "image/png",  
        ".jpg": "image/jpeg",  
        ".jpeg": "image/jpeg",  
        ".webp": "image/webp",  
    }  

    filename = screenshot.filename.lower()  

    mime_type = None  

    for extension, mime in allowed_extensions.items():  

        if filename.endswith(extension):  
            mime_type = mime  
            break  

    if not mime_type:  
        flash(  
            "Only PNG, JPG, JPEG and WEBP images are allowed.",  
            "error",  
        )  

        return render_template(  
            "deposit.html"  
        )  

    screenshot_data = screenshot.read()  

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
            VALUES (%s,%s,%s,%s,%s,%s,%s,'pending')  
            RETURNING id  
            """,  
            (  
                user["id"],  
                amount,  
                payment_number,  
                screenshot.filename,  
                psycopg2.Binary(  
                    screenshot_data  
                ),  
                mime_type,  
                reference,  
            ),  
        )  

        deposit_id = cur.fetchone()[0]  

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
                f"Demo deposit request #{deposit_id}",  
            ),  
        )  

        conn.commit()  

    except Exception:  
        conn.rollback()  
        raise  

    finally:  
        cur.close()  
        conn.close()  

    flash(  
        "Deposit request submitted successfully. Please wait for admin review.",  
        "success",  
    )  

    return redirect(  
        url_for("transaction_history")  
    )  

return render_template(  
    "deposit.html"  
)

============================================================

ADMIN DEPOSIT IMAGE

============================================================

@app.route(
"/admin/deposit-image/int:deposit_id"
)
def admin_deposit_image(deposit_id):

if not admin_required():  
    return redirect(  
        url_for("admin_login")  
    )  

deposit = query_one(  
    """  
    SELECT screenshot_data, screenshot_mime  
    FROM deposit_requests  
    WHERE id=%s  
    """,  
    (deposit_id,),  
)  

if not deposit:  
    abort(404)  

if not deposit["screenshot_data"]:  
    abort(404)  

return send_file(  
    BytesIO(  
        bytes(  
            deposit["screenshot_data"]  
        )  
    ),  
    mimetype=(  
        deposit["screenshot_mime"]  
        or "image/jpeg"  
    ),  
    as_attachment=False,  
    download_name=f"deposit_{deposit_id}.jpg",  
)

============================================================

OLD SCREENSHOT URL COMPATIBILITY

============================================================

@app.route(
"/uploads/deposits/path:filename"
)
def uploaded_deposit_image(filename):

if not admin_required():  
    return redirect(  
        url_for("admin_login")  
    )  

deposit = query_one(  
    """  
    SELECT screenshot_data, screenshot_mime  
    FROM deposit_requests  
    WHERE screenshot=%s  
    ORDER BY id DESC  
    LIMIT 1  
    """,  
    (filename,),  
)  

if not deposit or not deposit["screenshot_data"]:  
    abort(404)  

return send_file(  
    BytesIO(  
        bytes(  
            deposit["screenshot_data"]  
        )  
    ),  
    mimetype=(  
        deposit["screenshot_mime"]  
        or "image/jpeg"  
    ),  
    as_attachment=False,  
    download_name=filename,  
)

============================================================

DEPOSIT SUCCESS COMPATIBILITY

============================================================

@app.route("/deposit_success")
def deposit_success():

return redirect(  
    url_for("deposit")  
)

============================================================

BUY PLAN

============================================================

@app.route("/buy_plan/int:plan_id")
def buy_plan(plan_id):

user = current_user()  

if not user:  
    return redirect(  
        url_for("login")  
    )  

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

if money(  
    account["deposit_account"]  
) < plan["investment"]:  

    return render_template(  
        "insufficient_balance.html",  
        account=account,  
        plan={  
            "investment_amount":  
                plan["investment"]  
        },  
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
            plan["duration"],  
    },  
)

============================================================

CONFIRM PLAN

============================================================

@app.route(
"/confirm_buy_plan/int:plan_id",
methods=["POST"],
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
        "error",  
    )  

    return redirect(  
        url_for("dashboard")  
    )  

plan = PLANS[plan_id]  

conn = get_conn()  
cur = conn.cursor()  

try:  

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

    if not row:  
        conn.rollback()  

        flash(  
            "Account balance not found.",  
            "error",  
        )  

        return redirect(  
            url_for("dashboard")  
        )  

    balance = money(row[0])  

    if balance < plan["investment"]:  
        conn.rollback()  

        flash(  
            "Insufficient balance.",  
            "error",  
        )  

        return redirect(  
            url_for("dashboard")  
        )  

    cur.execute(  
        """  
        UPDATE accounts  
        SET deposit_account =  
            deposit_account - %s  
        WHERE user_id=%s  
        """,  
        (  
            plan["investment"],  
            user["id"],  
        ),  
    )  

    started_at = utcnow()  

    cur.execute(  
        """  
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
        """,  
        (  
            user["id"],  
            plan_id,  
            plan["name"],  
            plan["investment"],  
            plan["daily"],  
            plan["duration"],  
            started_at,  
        ),  
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
            'plan_purchase',  
            %s,  
            'successful',  
            %s,  
            %s  
        )  
        """,  
        (  
            user["id"],  
            plan["investment"],  
            generate_reference("PLAN"),  
            f"Demo plan purchase: {plan['name']}",  
        ),  
    )  

    conn.commit()  

except Exception:  
    conn.rollback()  
    app.logger.exception(  
        "PLAN PURCHASE ERROR"  
    )  
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

============================================================

MY PLAN

============================================================

@app.route(
"/my_plan",
methods=["GET", "POST"],
)
def my_plan():

user = current_user()  

if not user:  
    return redirect(  
        url_for("login")  
    )  

# --------------------------------------------------------  
# CLAIM DAILY INCOME  
# --------------------------------------------------------  

if request.method == "POST":  

    conn = get_conn()  
    cur = conn.cursor(  
        cursor_factory=RealDictCursor  
    )  

    try:  

        cur.execute(  
            """  
            SELECT *  
            FROM plans  
            WHERE user_id=%s  
            AND active=TRUE  
            ORDER BY id DESC  
            LIMIT 1  
            FOR UPDATE  
            """,  
            (user["id"],),  
        )  

        plan = cur.fetchone()  

        if not plan:  
            conn.rollback()  

            flash(  
                "You do not have an active plan.",  
                "error",  
            )  

            return redirect(  
                url_for("my_plan")  
            )  

        now = utcnow()  

        end_time = (  
            plan["started_at"]  
            + timedelta(  
                days=int(  
                    plan["duration"]  
                )  
            )  
        )  

        if now >= end_time:  

            cur.execute(  
                """  
                UPDATE plans  
                SET active=FALSE  
                WHERE id=%s  
                """,  
                (plan["id"],),  
            )  

            conn.commit()  

            flash(  
                "Your plan has completed its duration.",  
                "error",  
            )  

            return redirect(  
                url_for("my_plan")  
            )  

        if plan["last_claim_at"] is None:  

            next_claim_time = (  
                plan["started_at"]  
                + timedelta(hours=24)  
            )  

        else:  

            next_claim_time = (  
                plan["last_claim_at"]  
                + timedelta(hours=24)  
            )  

        if now < next_claim_time:  

            remaining = int(  
                (  
                    next_claim_time - now  
                ).total_seconds()  
            )  

            hours = remaining // 3600  
            minutes = (  
                remaining % 3600  
            ) // 60  

            conn.rollback()  

            flash(  
                f"Your next income can be claimed in "  
                f"{hours}h {minutes}m.",  
                "error",  
            )  

            return redirect(  
                url_for("my_plan")  
            )  

        daily_income = money(  
            plan["daily_income"]  
        )  

        if daily_income <= 0:  
            conn.rollback()  

            flash(  
                "This plan has no valid daily income.",  
                "error",  
            )  

            return redirect(  
                url_for("my_plan")  
            )  

        # Lock account.  
        cur.execute(  
            """  
            SELECT user_id  
            FROM accounts  
            WHERE user_id=%s  
            FOR UPDATE  
            """,  
            (user["id"],),  
        )  

        if not cur.fetchone():  

            cur.execute(  
                """  
                INSERT INTO accounts (  
                    user_id,  
                    deposit_account,  
                    income_account,  
                    referral_account,  
                    withdraw_account  
                )  
                VALUES (%s,%s,0,0,0)  
                """,  
                (  
                    user["id"],  
                    STARTING_DEPOSIT_BALANCE,  
                ),  
            )  

        # Credit demo income.  
        cur.execute(  
            """  
            UPDATE accounts  
            SET  
                income_account =  
                    COALESCE(income_account,0)  
                    + %s,  

                withdraw_account =  
                    COALESCE(withdraw_account,0)  
                    + %s  

            WHERE user_id=%s  
            """,  
            (  
                daily_income,  
                daily_income,  
                user["id"],  
            ),  
        )  

        cur.execute(  
            """  
            UPDATE plans  
            SET last_claim_at=%s  
            WHERE id=%s  
            """,  
            (  
                now,  
                plan["id"],  
            ),  
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
                'income_claim',  
                %s,  
                'successful',  
                %s,  
                %s  
            )  
            """,  
            (  
                user["id"],  
                daily_income,  
                generate_reference("INC"),  
                f"Daily demo income claim: {plan['plan_name']}",  
            ),  
        )  

        conn.commit()  

        flash(  
            f"GHS {daily_income:.2f} income claimed successfully.",  
            "success",  
        )  

    except Exception:  
        conn.rollback()  

        app.logger.exception(  
            "MY PLAN CLAIM ERROR"  
        )  

        flash(  
            "Unable to process your income claim.",  
            "error",  
        )  

    finally:  
        cur.close()  
        conn.close()  

    return redirect(  
        url_for("my_plan")  
    )  

# --------------------------------------------------------  
# GET ACTIVE PLAN  
# --------------------------------------------------------  

plan = query_one(  
    """  
    SELECT *  
    FROM plans  
    WHERE user_id=%s  
    AND active=TRUE  
    ORDER BY id DESC  
    LIMIT 1  
    """,  
    (user["id"],),  
)  

can_claim = False  
seconds_remaining = 0  
cycle_seconds_remaining = 0  
next_claim_timestamp = 0  
cycle_ended = False  

if plan:  

    now = utcnow()  

    end_time = (  
        plan["started_at"]  
        + timedelta(  
            days=int(  
                plan["duration"]  
            )  
        )  
    )  

    if now >= end_time:  

        execute(  
            """  
            UPDATE plans  
            SET active=FALSE  
            WHERE id=%s  
            """,  
            (plan["id"],),  
        )  

        plan = None  
        cycle_ended = True  

    else:  

        cycle_seconds_remaining = max(  
            0,  
            int(  
                (  
                    end_time - now  
                ).total_seconds()  
            ),  
        )  

        if plan["last_claim_at"] is None:  

            next_claim_time = (  
                plan["started_at"]  
                + timedelta(hours=24)  
            )  

        else:  

            next_claim_time = (  
                plan["last_claim_at"]  
                + timedelta(hours=24)  
            )  

        seconds_remaining = max(  
            0,  
            int(  
                (  
                    next_claim_time - now  
                ).total_seconds()  
            ),  
        )  

        if now >= next_claim_time:  
            can_claim = True  
            seconds_remaining = 0  

        else:  
            next_claim_timestamp = int(  
                next_claim_time.timestamp()  
            )  

available_plans = []  

for plan_id, data in PLANS.items():  

    available_plans.append(  
        {  
            "id": plan_id,  
            "plan_name": data["name"],  
            "investment_amount":  
                data["investment"],  
            "daily_income":  
                data["daily"],  
            "duration":  
                data["duration"],  
        }  
    )  

return render_template(  
    "my_plan.html",  
    user_plan=plan,  
    available_plans=available_plans,  
    can_claim=can_claim,  
    seconds_remaining=seconds_remaining,  
    cycle_seconds_remaining=cycle_seconds_remaining,  
    next_claim_timestamp=next_claim_timestamp,  
    cycle_ended=cycle_ended,  
)

============================================================

WITHDRAW

============================================================

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

accounts = query_all(  
    """  
    SELECT *  
    FROM withdrawal_accounts  
    WHERE user_id=%s  
    ORDER BY id DESC  
    """,  
    (user["id"],),  
)  

return render_template(  
    "withdraw.html",  
    account=account,  
    accounts=accounts,  
)

============================================================

BIND ACCOUNT

============================================================

@app.route(
"/bind_account",
methods=["GET", "POST"],
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

    if not account_name or not phone or not network:  

        flash(  
            "Please complete all account details.",  
            "error",  
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
            VALUES (%s,%s,%s,%s)  
            """,  
            (  
                user["id"],  
                account_name,  
                phone,  
                network,  
            ),  
        )  

        flash(  
            "Withdrawal account saved.",  
            "success",  
        )  

accounts = query_all(  
    """  
    SELECT *  
    FROM withdrawal_accounts  
    WHERE user_id=%s  
    ORDER BY id DESC  
    """,  
    (user["id"],),  
)  

return render_template(  
    "bind_account.html",  
    accounts=accounts,  
)

============================================================

REQUEST WITHDRAWAL

============================================================

@app.route(
"/request_withdrawal",
methods=["POST"],
)
def request_withdrawal():

user = current_user()  

if not user:  
    return redirect(  
        url_for("login")  
    )  

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
        f"Minimum demo withdrawal is GHS {MIN_WITHDRAWAL:.2f}.",  
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

    selected = query_one(  
        """  
        SELECT id  
        FROM withdrawal_accounts  
        WHERE id=%s  
        AND user_id=%s  
        """,  
        (  
            account_id,  
            user["id"],  
        ),  
    )  

    if not selected:  

        flash(  
            "Invalid withdrawal account.",  
            "error",  
        )  

        return redirect(  
            url_for("withdraw")  
        )  

    selected_account_id = selected["id"]  

else:  

    selected = query_one(  
        """  
        SELECT id  
        FROM withdrawal_accounts  
        WHERE user_id=%s  
        ORDER BY id DESC  
        LIMIT 1  
        """,  
        (user["id"],),  
    )  

    if selected:  
        selected_account_id = selected["id"]  

if not selected_account_id:  

    flash(  
        "Please bind a withdrawal account first.",  
        "error",  
    )  

    return redirect(  
        url_for("bind_account")  
    )  

conn = get_conn()  
cur = conn.cursor()  

try:  

    cur.execute(  
        """  
        SELECT withdraw_account  
        FROM accounts  
        WHERE user_id=%s  
        FOR UPDATE  
        """,  
        (user["id"],),  
    )  

    row = cur.fetchone()  

    if not row:  
        conn.rollback()  

        flash(  
            "Account balance not found.",  
            "error",  
        )  

        return redirect(  
            url_for("withdraw")  
        )  

    balance = money(row[0])  

    if balance < amount:  

        conn.rollback()  

        flash(  
            "Insufficient withdrawal balance.",  
            "error",  
        )  

        return redirect(  
            url_for("withdraw")  
        )  

    cur.execute(  
        """  
        UPDATE accounts  
        SET withdraw_account =  
            withdraw_account - %s  
        WHERE user_id=%s  
        AND withdraw_account >= %s  
        """,  
        (  
            amount,  
            user["id"],  
            amount,  
        ),  
    )  

    if cur.rowcount != 1:  

        conn.rollback()  

        flash(  
            "Insufficient withdrawal balance.",  
            "error",  
        )  

        return redirect(  
            url_for("withdraw")  
        )  

    reference = generate_reference(  
        "WDR"  
    )  

    cur.execute(  
        """  
        INSERT INTO withdrawal_requests (  
            user_id,  
            amount,  
            account_id,  
            status  
        )  
        VALUES (%s,%s,%s,'pending')  
        RETURNING id  
        """,  
        (  
            user["id"],  
            amount,  
            selected_account_id,  
        ),  
    )  

    withdrawal_id = cur.fetchone()[0]  

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
            'withdrawal',  
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
            f"Demo withdrawal request #{withdrawal_id}",  
        ),  
    )  

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

============================================================

TRANSACTION HISTORY

============================================================

@app.route("/transaction_history")
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
    (user["id"],),  
)  

return render_template(  
    "transaction_history.html",  
    transactions=transactions,  
)

============================================================

TEAM

============================================================

@app.route("/team")
def team():

user = current_user()  

if not user:  
    return redirect(  
        url_for("login")  
    )  

members = query_all(  
    """  
    SELECT  
        id,  
        username,  
        fullname,  
        phone,  
        created_at  
    FROM users  
    WHERE referred_by=%s  
    ORDER BY created_at DESC  
    """,  
    (user["referral_code"],),  
)  

account = current_account(  
    user["id"]  
)  

referral_income = money(  
    account["referral_account"]  
)  

return render_template(  
    "team.html",  
    user=user,  
    members=members,  
    total_team=len(members),  
    referral_income=referral_income,  
)

============================================================

SUPPORT

============================================================

@app.route("/support")
@app.route("/service")
def support():

return render_template(  
    "support.html"  
)

============================================================

PROFILE

============================================================

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
    deposit_balance=account["deposit_account"],  
    withdraw_balance=account["withdraw_account"],  
    income_balance=account["income_account"],  
    referral_balance=account["referral_account"],  
)

============================================================

CHANGE LOGIN PASSWORD

============================================================

@app.route(
"/change_login_password",
methods=["GET", "POST"],
)
def change_login_password():

user = current_user()  

if not user:  
    return redirect(  
        url_for("login")  
    )  

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

    execute(  
        """  
        UPDATE users  
        SET password_hash=%s  
        WHERE id=%s  
        """,  
        (  
            generate_password_hash(  
                new_password  
            ),  
            user["id"],  
        ),  
    )  

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

============================================================

CHANGE WITHDRAWAL PASSWORD

============================================================

@app.route(
"/change_withdraw_password",
methods=["GET", "POST"],
)
def change_withdraw_password():

user = current_user()  

if not user:  
    return redirect(  
        url_for("login")  
    )  

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

    execute(  
        """  
        UPDATE users  
        SET withdraw_password_hash=%s  
        WHERE id=%s  
        """,  
        (  
            generate_password_hash(  
                new_password  
            ),  
            user["id"],  
        ),  
    )  

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

============================================================

ADMIN AUTHORIZATION

============================================================

def admin_required():
return session.get(
"admin_logged_in"
) is True

============================================================

ADMIN LOGIN

============================================================

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

    admin = query_one(  
        """  
        SELECT *  
        FROM admins  
        WHERE username=%s  
        """,  
        (username,),  
    )  

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
        session["admin_id"] = admin["id"]  

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

============================================================

ADMIN LOGOUT

============================================================

@app.route("/admin/logout")
def admin_logout():

session.clear()  

return redirect(  
    url_for("admin_login")  
)

============================================================

ADMIN DASHBOARD

============================================================

@app.route("/admin_dashboard")
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

return render_template(  
    "admin_dashboard.html",  
    total_users=total_users,  
    pending_deposits=pending_deposits,  
    pending_withdrawals=pending_withdrawals,  
)

============================================================

ADMIN USERS

============================================================

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
    users=users,  
)

============================================================

ADMIN MANAGE USER

============================================================

@app.route(
"/admin/user/int:user_id",
methods=["GET", "POST"],
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
    (user_id,),  
)  

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
        "add_deposit": "deposit_account",  
        "deduct_deposit": "deposit_account",  
        "add_withdraw": "withdraw_account",  
        "deduct_withdraw": "withdraw_account",  
        "add_income": "income_account",  
        "deduct_income": "income_account",  
        "add_referral": "referral_account",  
        "deduct_referral": "referral_account",  
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

        column = balance_actions[action]  

        is_add = action.startswith("add_")  

        conn = get_conn()  
        cur = conn.cursor()  

        try:  

            cur.execute(  
                """  
                SELECT user_id  
                FROM accounts  
                WHERE user_id=%s  
                FOR UPDATE  
                """,  
                (user_id,),  
            )  

            if not cur.fetchone():  

                cur.execute(  
                    """  
                    INSERT INTO accounts (  
                        user_id,  
                        deposit_account,  
                        income_account,  
                        referral_account,  
                        withdraw_account  
                    )  
                    VALUES (%s,%s,0,0,0)  
                    """,  
                    (  
                        user_id,  
                        STARTING_DEPOSIT_BALANCE,  
                    ),  
                )  

            if is_add:  

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
                    generate_reference("ADM"),  
                    f"Admin adjustment: {action}",  
                ),  
            )  

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

        else:  

            execute(  
                """  
                UPDATE users  
                SET password_hash=%s  
                WHERE id=%s  
                """,  
                (  
                    generate_password_hash(  
                        new_password  
                    ),  
                    user_id,  
                ),  
            )  

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

        else:  

            execute(  
                """  
                UPDATE users  
                SET withdraw_password_hash=%s  
                WHERE id=%s  
                """,  
                (  
                    generate_password_hash(  
                        new_password  
                    ),  
                    user_id,  
                ),  
            )  

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

    # ----------------------------------------------------  
    # UPDATE MOBILE MONEY ACCOUNT  
    # ----------------------------------------------------  

    if action == "update_account":  

        account_id = request.form.get(  
            "account_id"  
        )  

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
            not account_id  
            or not account_name  
            or not phone  
            or not network  
        ):  

            flash(  
                "Please complete all withdrawal account details.",  
                "error",  
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
                    user_id,  
                ),  
            )  

            flash(  
                "Withdrawal account updated successfully.",  
                "success",  
            )  

        return redirect(  
            url_for(  
                "admin_manage_user",  
                user_id=user_id,  
            )  
        )  

    # ----------------------------------------------------  
    # DELETE MOBILE MONEY ACCOUNT  
    # ----------------------------------------------------  

    if action == "delete_account":  

        account_id = request.form.get(  
            "account_id"  
        )  

        execute(  
            """  
            DELETE FROM withdrawal_accounts  
            WHERE id=%s  
            AND user_id=%s  
            """,  
            (  
                account_id,  
                user_id,  
            ),  
        )  

        flash(  
            "Withdrawal account removed.",  
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

withdrawal_accounts = query_all(  
    """  
    SELECT *  
    FROM withdrawal_accounts  
    WHERE user_id=%s  
    ORDER BY id DESC  
    """,  
    (user_id,),  
)  

return render_template(  
    "admin_manage_user.html",  
    user=user,  
    account=account,  
    withdrawal_accounts=withdrawal_accounts,  
)

============================================================

ADMIN DEPOSITS

============================================================

@app.route("/admin_deposit")
@app.route("/admin/deposits")
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
    deposits=deposits,  
)

============================================================

ADMIN DEPOSIT ACTION

============================================================

@app.route(
"/admin/deposit/int:deposit_id/<action>",
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

if action not in {  
    "approve",  
    "reject",  
}:  

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
        (deposit_id,),  
    )  

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

    if action == "approve":  

        cur.execute(  
            """  
            SELECT user_id  
            FROM accounts  
            WHERE user_id=%s  
            FOR UPDATE  
            """,  
            (user_id,),  
        )  

        if not cur.fetchone():  

            cur.execute(  
                """  
                INSERT INTO accounts (  
                    user_id,  
                    deposit_account,  
                    income_account,  
                    referral_account,  
                    withdraw_account  
                )  
                VALUES (%s,0,0,0,0)  
                """,  
                (user_id,),  
            )  

        cur.execute(  
            """  
            UPDATE accounts  
            SET deposit_account =  
                COALESCE(deposit_account,0)  
                + %s  
            WHERE user_id=%s  
            """,  
            (  
                amount,  
                user_id,  
            ),  
        )  

        cur.execute(  
            """  
            UPDATE deposit_requests  
            SET status='approved'  
            WHERE id=%s  
            """,  
            (deposit_id,),  
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
                reference,  
            ),  
        )  

        message = (  
            f"Demo deposit of GHS {amount:.2f} approved successfully."  
        )  

    else:  

        cur.execute(  
            """  
            UPDATE deposit_requests  
            SET status='rejected'  
            WHERE id=%s  
            """,  
            (deposit_id,),  
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
                reference,  
            ),  
        )  

        message = (  
            f"Demo deposit of GHS {amount:.2f} rejected."  
        )  

    conn.commit()  

    flash(  
        message,  
        "success",  
    )  

except Exception:  

    conn.rollback()  

    app.logger.exception(  
        "ADMIN DEPOSIT ACTION ERROR"  
    )  

    flash(  
        "Unable to process the deposit.",  
        "error",  
    )  

finally:  
    cur.close()  
    conn.close()  

return redirect(  
    url_for("admin_deposits")  
)

============================================================

ADMIN WITHDRAWALS

============================================================

@app.route("/admin_withdraw")
@app.route("/admin/withdrawals")
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
    withdrawals=withdrawals,  
)

============================================================

ADMIN WITHDRAWAL ACTION

============================================================

@app.route(
"/admin/withdraw/int:withdrawal_id/<action>",
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

    cur.execute(  
        """  
        SELECT *  
        FROM withdrawal_requests  
        WHERE id=%s  
        FOR UPDATE  
        """,  
        (withdrawal_id,),  
    )  

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
            (withdrawal_id,),  
        )  

        # Update the exact pending transaction  
        # belonging to this withdrawal request.  
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
                amount,  
            ),  
        )  

        message = (  
            "Withdrawal approved successfully."  
        )  

    else:  

        # Return reserved balance.  
        cur.execute(  
            """  
            SELECT user_id  
            FROM accounts  
            WHERE user_id=%s  
            FOR UPDATE  
            """,  
            (user_id,),  
        )  

        account = cur.fetchone()  

        if account:  

            cur.execute(  
                """  
                UPDATE accounts  
                SET withdraw_account =  
                    COALESCE(withdraw_account,0)  
                    + %s  
                WHERE user_id=%s  
                """,  
                (  
                    amount,  
                    user_id,  
                ),  
            )  

        else:  

            cur.execute(  
                """  
                INSERT INTO accounts (  
                    user_id,  
                    deposit_account,  
                    income_account,  
                    referral_account,  
                    withdraw_account  
                )  
                VALUES (%s,0,0,0,%s)  
                """,  
                (  
                    user_id,  
                    amount,  
                ),  
            )  

        cur.execute(  
            """  
            UPDATE withdrawal_requests  
            SET status='rejected'  
            WHERE id=%s  
            """,  
            (withdrawal_id,),  
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
                amount,  
            ),  
        )  

        message = (  
            "Withdrawal rejected and balance restored."  
        )  

    conn.commit()  

    flash(  
        message,  
        "success",  
    )  

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

============================================================

ADMIN BOUND ACCOUNTS

============================================================

@app.route("/admin_bind_accounts")
@app.route("/admin/bind_accounts")
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
    accounts=accounts,  
)

============================================================

ERROR HANDLERS

============================================================

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

============================================================

DATABASE INITIALIZATION

============================================================

with app.app_context():
init_db()

============================================================

LOCAL DEVELOPMENT

============================================================

if name == "main":

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

<!DOCTYPE html><html lang="en"><head>  <meta charset="UTF-8">  
<meta name="viewport" content="width=device-width, initial-scale=1.0"><title>My Income - Zenith Capital</title>

<link  
    rel="stylesheet"  
    href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css"  
>  <style>  
    * {  
        margin: 0;  
        padding: 0;  
        box-sizing: border-box;  
        font-family: system-ui, -apple-system, BlinkMacSystemFont,  
            "Segoe UI", Arial, sans-serif;  
    }  
  
    body {  
        background: #f1f4fa;  
        color: #334155;  
        min-height: 100vh;  
        padding-bottom: 85px;  
    }  
  
    .phone {  
        width: 100%;  
        max-width: 440px;  
        min-height: 100vh;  
        margin: auto;  
        background: #f1f4fa;  
    }  
  
    /* HEADER */  
  
    .header {  
        background: #0b1c4d;  
        color: white;  
        padding: 20px 18px;  
        box-shadow: 0 4px 12px rgba(0, 0, 0, .10);  
    }  
  
    .header-top {  
        display: flex;  
        align-items: center;  
        justify-content: space-between;  
        gap: 10px;  
    }  
  
    .header h1 {  
        font-size: 20px;  
        font-weight: 800;  
    }  
  
    .header p {  
        margin-top: 4px;  
        color: #cbd5e1;  
        font-size: 11px;  
    }  
  
    .status {  
        background: #dcfce7;  
        color: #15803d;  
        padding: 6px 10px;  
        border-radius: 20px;  
        font-size: 9px;  
        font-weight: 800;  
    }  
  
    /* CONTENT */  
  
    .content {  
        padding: 16px;  
    }  
  
    /* FLASH */  
  
    .flash {  
        padding: 11px 13px;  
        border-radius: 10px;  
        margin-bottom: 12px;  
        font-size: 11px;  
        font-weight: 700;  
    }  
  
    .flash.success {  
        background: #dcfce7;  
        color: #15803d;  
    }  
  
    .flash.error {  
        background: #fee2e2;  
        color: #b91c1c;  
    }  
  
    .flash.info {  
        background: #dbeafe;  
        color: #1d4ed8;  
    }  
  
    /* SECTION */  
  
    .section-title {  
        display: flex;  
        justify-content: space-between;  
        align-items: center;  
        margin: 5px 2px 10px;  
    }  
  
    .section-title h2 {  
        color: #0f172a;  
        font-size: 15px;  
        font-weight: 800;  
    }  
  
    .section-title span {  
        color: #94a3b8;  
        font-size: 10px;  
    }  
  
    /* PLAN CARD */  
  
    .plan-card {  
        background: white;  
        border-radius: 20px;  
        padding: 18px;  
        margin-bottom: 18px;  
        border: 1px solid #edf0f5;  
        box-shadow: 0 7px 22px rgba(15, 23, 42, .07);  
    }  
  
    .plan-header {  
        display: flex;  
        align-items: center;  
        gap: 13px;  
        margin-bottom: 15px;  
    }  
  
    .plan-icon {  
        width: 55px;  
        height: 55px;  
        flex-shrink: 0;  
        border-radius: 15px;  
        background: #eef2ff;  
        color: #0b1c4d;  
        display: flex;  
        align-items: center;  
        justify-content: center;  
        font-size: 22px;  
    }  
  
    .plan-title {  
        min-width: 0;  
    }  
  
    .plan-title h2 {  
        color: #0f172a;  
        font-size: 18px;  
        font-weight: 800;  
        word-break: break-word;  
    }  
  
    .plan-title p {  
        color: #64748b;  
        font-size: 11px;  
        margin-top: 3px;  
    }  
  
    /* RUNNING */  
  
    .running {  
        display: flex;  
        align-items: center;  
        gap: 7px;  
        background: #f0fdf4;  
        border: 1px solid #bbf7d0;  
        color: #15803d;  
        padding: 9px 11px;  
        border-radius: 10px;  
        font-size: 11px;  
        font-weight: 700;  
        margin-bottom: 14px;  
    }  
  
    .dot {  
        width: 7px;  
        height: 7px;  
        background: #22c55e;  
        border-radius: 50%;  
        box-shadow: 0 0 0 4px rgba(34, 197, 94, .10);  
    }  
  
    /* COUNTDOWN */  
  
    .countdown-box {  
        background: #0b1c4d;  
        color: white;  
        border-radius: 15px;  
        padding: 18px 12px;  
        text-align: center;  
        margin-bottom: 14px;  
    }  
  
    .countdown-label {  
        color: #cbd5e1;  
        font-size: 10px;  
        font-weight: 700;  
        letter-spacing: .6px;  
    }  
  
    .countdown {  
        margin-top: 7px;  
        font-size: 32px;  
        font-weight: 900;  
        letter-spacing: 2px;  
        font-variant-numeric: tabular-nums;  
    }  
  
    .countdown.ready {  
        color: #86efac;  
    }  
  
    .countdown-sub {  
        margin-top: 6px;  
        color: #94a3b8;  
        font-size: 9px;  
    }  
  
    /* CLAIM BUTTON */  
  
    .claim-button {  
        width: 100%;  
        border: none;  
        background: #0b1c4d;  
        color: white;  
        padding: 13px;  
        border-radius: 10px;  
        font-size: 11px;  
        font-weight: 800;  
    }  
  
    .claim-button.disabled {  
        background: #cbd5e1;  
        color: #64748b;  
    }  
  
    /* DETAILS */  
  
    .details {  
        display: grid;  
        grid-template-columns: 1fr 1fr;  
        gap: 8px;  
    }  
  
    .detail {  
        background: #f8fafc;  
        border: 1px solid #edf0f5;  
        border-radius: 11px;  
        padding: 11px;  
    }  
  
    .detail span {  
        display: block;  
        color: #64748b;  
        font-size: 10px;  
        margin-bottom: 5px;  
    }  
  
    .detail strong {  
        color: #0f172a;  
        font-size: 13px;  
    }  
  
    /* INCOME */  
  
    .income-box {  
        margin-top: 9px;  
        background: #eef2ff;  
        border: 1px solid #dbeafe;  
        border-radius: 11px;  
        padding: 12px;  
        display: flex;  
        justify-content: space-between;  
        align-items: center;  
        gap: 10px;  
    }  
  
    .income-box span {  
        color: #475569;  
        font-size: 11px;  
    }  
  
    .income-box strong {  
        color: #0b1c4d;  
        font-size: 15px;  
    }  
  
    /* AVAILABLE PLANS */  
  
    .available-plan {  
        background: white;  
        border: 1px solid #edf0f5;  
        border-radius: 16px;  
        padding: 15px;  
        margin-bottom: 9px;  
        box-shadow: 0 3px 10px rgba(15, 23, 42, .035);  
    }  
  
    .available-top {  
        display: flex;  
        align-items: center;  
        justify-content: space-between;  
        gap: 10px;  
        margin-bottom: 12px;  
    }  
  
    .available-name {  
        display: flex;  
        align-items: center;  
        gap: 9px;  
        min-width: 0;  
    }  
  
    .available-icon {  
        width: 38px;  
        height: 38px;  
        flex-shrink: 0;  
        border-radius: 11px;  
        background: #eef2ff;  
        color: #0b1c4d;  
        display: flex;  
        align-items: center;  
        justify-content: center;  
        font-size: 15px;  
    }  
  
    .available-name h3 {  
        color: #0f172a;  
        font-size: 14px;  
        font-weight: 800;  
        word-break: break-word;  
    }  
  
    .available-name p {  
        color: #94a3b8;  
        font-size: 9px;  
        margin-top: 2px;  
    }  
  
    .plan-badge,  
    .current-plan {  
        padding: 5px 8px;  
        border-radius: 15px;  
        font-size: 8px;  
        font-weight: 800;  
        white-space: nowrap;  
    }  
  
    .plan-badge {  
        background: #f1f5f9;  
        color: #64748b;  
    }  
  
    .current-plan {  
        background: #dcfce7;  
        color: #15803d;  
    }  
  
    .available-details {  
        display: grid;  
        grid-template-columns: repeat(3, 1fr);  
        gap: 6px;  
        margin-bottom: 12px;  
    }  
  
    .available-detail {  
        background: #f8fafc;  
        border-radius: 9px;  
        padding: 9px 6px;  
        text-align: center;  
    }  
  
    .available-detail span {  
        display: block;  
        color: #94a3b8;  
        font-size: 8px;  
        margin-bottom: 4px;  
    }  
  
    .available-detail strong {  
        color: #0b1c4d;  
        font-size: 11px;  
    }  
  
    .select-plan {  
        width: 100%;  
        display: flex;  
        align-items: center;  
        justify-content: center;  
        gap: 7px;  
        padding: 11px;  
        border-radius: 10px;  
        background: #0b1c4d;  
        color: white;  
        text-decoration: none;  
        font-size: 11px;  
        font-weight: 800;  
    }  
  
    /* EMPTY */  
  
    .empty {  
        text-align: center;  
        padding: 25px 15px;  
        color: #64748b;  
    }  
  
    .empty-icon {  
        width: 55px;  
        height: 55px;  
        margin: 0 auto 10px;  
        border-radius: 15px;  
        background: #eef2ff;  
        color: #0b1c4d;  
        display: flex;  
        align-items: center;  
        justify-content: center;  
        font-size: 23px;  
    }  
  
    .empty h2 {  
        color: #0f172a;  
        font-size: 17px;  
    }  
  
    .empty p {  
        margin-top: 5px;  
        font-size: 11px;  
    }  
  
    /* INFO */  
  
    .info {  
        background: white;  
        border: 1px solid #edf0f5;  
        border-radius: 16px;  
        padding: 15px;  
        margin-top: 15px;  
    }  
  
    .info-title {  
        display: flex;  
        align-items: center;  
        gap: 8px;  
        color: #0f172a;  
        font-size: 13px;  
        font-weight: 800;  
        margin-bottom: 7px;  
    }  
  
    .info-title i {  
        color: #0b1c4d;  
    }  
  
    .info p {  
        color: #64748b;  
        font-size: 11px;  
        line-height: 1.55;  
    }  
  
    /* BOTTOM NAV */  
  
    .bottom-nav {  
        position: fixed;  
        bottom: 0;  
        left: 0;  
        right: 0;  
        height: 67px;  
        background: white;  
        border-top: 1px solid #e2e8f0;  
        display: flex;  
        justify-content: center;  
        z-index: 9999;  
        box-shadow: 0 -4px 14px rgba(0, 0, 0, .05);  
    }  
  
    .bottom-nav-inner {  
        width: 100%;  
        max-width: 440px;  
        display: grid;  
        grid-template-columns: repeat(5, 1fr);  
        align-items: center;  
    }  
  
    .bottom-nav a {  
        height: 100%;  
        position: relative;  
        display: flex;  
        flex-direction: column;  
        align-items: center;  
        justify-content: center;  
        gap: 4px;  
        text-decoration: none;  
        color: #94a3b8;  
        font-size: 9px;  
    }  
  
    .bottom-nav i {  
        font-size: 18px;  
    }  
  
    .bottom-nav a.active {  
        color: #0b1c4d;  
        font-weight: 800;  
    }  
  
    .bottom-nav a.active::after {  
        content: "";  
        position: absolute;  
        bottom: 0;  
        left: 25%;  
        right: 25%;  
        height: 3px;  
        background: #0b1c4d;  
        border-radius: 4px 4px 0 0;  
    }  
  
    @media (max-width: 360px) {  
        .content {  
            padding: 12px;  
        }  
  
        .plan-card {  
            padding: 15px;  
        }  
  
        .countdown {  
            font-size: 27px;  
        }  
  
        .available-details {  
            gap: 4px;  
        }  
  
        .available-detail {  
            padding: 8px 4px;  
        }  
    }  
</style>  </head><body><div class="phone"><header class="header">  <div class="header-top">  

    <div>  
        <h1>My Income</h1>  

        <p>  
            Manage your active plan and income  
        </p>  
    </div>  

    {% if user_plan %}  
        <div class="status">  
            ACTIVE  
        </div>  
    {% endif %}  

</div>

</header>  <main class="content">  <!-- FLASH MESSAGES -->  

{% with messages = get_flashed_messages(with_categories=true) %}  

    {% if messages %}  

        {% for category, message in messages %}  

            <div class="flash {{ category }}">  
                {{ message }}  
            </div>  

        {% endfor %}  

    {% endif %}  

{% endwith %}  


<!-- ACTIVE PLAN -->  

<div class="section-title">  

    <h2>My Active Plan</h2>  

    {% if user_plan %}  
        <span>Currently running</span>  
    {% endif %}  

</div>  


{% if user_plan %}  

<div class="plan-card">  

    <div class="plan-header">  

        <div class="plan-icon">  
            <i class="fa-solid fa-chart-line"></i>  
        </div>  

        <div class="plan-title">  

            <h2>  
                {{ user_plan.plan_name }}  
            </h2>  

            <p>  
                Your active product  
            </p>  

        </div>  

    </div>  


    <div class="running">  

        <span class="dot"></span>  

        Plan Running  

    </div>  


    <!-- COUNTDOWN -->  

    <div class="countdown-box">  

        <div class="countdown-label">  
            NEXT INCOME IN  
        </div>  

        <div  
            id="countdown"  
            class="countdown"  
        >  
            {% if can_claim %}  
                00:00:00  
            {% else %}  
                --:--:--  
            {% endif %}  
        </div>  

        <div  
            id="countdownSub"  
            class="countdown-sub"  
        >  
            {% if can_claim %}  
                Income is ready  
            {% else %}  
                Calculating next income...  
            {% endif %}  
        </div>  

    </div>  


    <!-- PLAN DETAILS -->  

    <div class="details">  

        <div class="detail">  

            <span>  
                Investment  
            </span>  

            <strong>  
                GHS {{ "%.2f"|format(  
                    user_plan.investment_amount|float  
                ) }}  
            </strong>  

        </div>  


        <div class="detail">  

            <span>  
                Daily Income  
            </span>  

            <strong>  
                GHS {{ "%.2f"|format(  
                    user_plan.daily_income|float  
                ) }}  
            </strong>  

        </div>  


        <div class="detail">  

            <span>  
                Duration  
            </span>  

            <strong>  
                {{ user_plan.duration }} Days  
            </strong>  

        </div>  


        <div class="detail">  

            <span>  
                Status  
            </span>  

            <strong>  
                Active  
            </strong>  

        </div>  

    </div>  


    <!-- DAILY INCOME -->  

    <div class="income-box">  

        <span>  
            Expected Daily Income  
        </span>  

        <strong>  
            GHS {{ "%.2f"|format(  
                user_plan.daily_income|float  
            ) }}  
        </strong>  

    </div>  


    <!-- CLAIM STATUS -->  

    <div  
        id="claimButton"  
        class="claim-button {% if not can_claim %}disabled{% endif %}"  
        style="margin-top:10px;"  
    >  

        {% if can_claim %}  

            <i class="fa-solid fa-coins"></i>  
            Income Ready  

        {% else %}  

            <i class="fa-solid fa-clock"></i>  
            Income Not Ready  

        {% endif %}  

    </div>  

</div>  


{% else %}  

<div class="plan-card">  

    <div class="empty">  

        <div class="empty-icon">  
            <i class="fa-solid fa-box-open"></i>  
        </div>  

        <h2>  
            No Active Plan  
        </h2>  

        <p>  
            You currently don't have an active plan.  
        </p>  

    </div>  

</div>  

{% endif %}  


<!-- AVAILABLE PLANS -->  

<div class="section-title">  

    <h2>  
        Available Plans  
    </h2>  

    <span>  
        Choose a product  
    </span>  

</div>  


{% if plans %}  

    {% for plan in plans %}  

        <div class="available-plan">  

            <div class="available-top">  

                <div class="available-name">  

                    <div class="available-icon">  
                        <i class="fa-solid fa-box"></i>  
                    </div>  

                    <div>  

                        <h3>  
                            {{ plan.plan_name }}  
                        </h3>  

                        <p>  
                            Zenith Capital Product  
                        </p>  

                    </div>  

                </div>  


                {% if user_plan and  
                      user_plan.plan_name == plan.plan_name %}  

                    <span class="current-plan">  
                        CURRENT  
                    </span>  

                {% else %}  

                    <span class="plan-badge">  
                        AVAILABLE  
                    </span>  

                {% endif %}  

            </div>  


            <div class="available-details">  

                <div class="available-detail">  

                    <span>  
                        Investment  
                    </span>  

                    <strong>  
                        GHS {{ "%.2f"|format(  
                            plan.investment_amount|float  
                        ) }}  
                    </strong>  

                </div>  


                <div class="available-detail">  

                    <span>  
                        Daily Income  
                    </span>  

                    <strong>  
                        GHS {{ "%.2f"|format(  
                            plan.daily_income|float  
                        ) }}  
                    </strong>  

                </div>  


                <div class="available-detail">  

                    <span>  
                        Duration  
                    </span>  

                    <strong>  
                        {{ plan.duration }} Days  
                    </strong>  

                </div>  

            </div>  


            {% if not user_plan or  
                  user_plan.plan_name != plan.plan_name %}  

                <a  
                    href="{{ url_for(  
                        'buy_plan',  
                        plan_id=plan.id  
                    ) }}"  
                    class="select-plan"  
                >  

                    <i class="fa-solid fa-arrow-right"></i>  

                    View / Select Plan  

                </a>  

            {% endif %}  

        </div>  

    {% endfor %}  

{% else %}  

    <div class="available-plan">  

        <div class="empty">  

            <div class="empty-icon">  
                <i class="fa-solid fa-box-open"></i>  
            </div>  

            <h2>  
                No Plans Available  
            </h2>  

            <p>  
                There are currently no products available.  
            </p>  

        </div>  

    </div>  

{% endif %}  


<!-- INFORMATION -->  

<div class="info">  

    <div class="info-title">  

        <i class="fa-solid fa-circle-info"></i>  

        <span>  
            Income Information  
        </span>  

    </div>  

    <p>  
        The countdown is based on the next income  
        time supplied by the server. Refreshing  
        the page does not reset the countdown.  
    </p>  

</div>

</main>  </div><!-- BOTTOM NAVIGATION --><nav class="bottom-nav"><div class="bottom-nav-inner">  <a href="{{ url_for('dashboard') }}">  

    <i class="fa-solid fa-house"></i>  

    <span>  
        Home  
    </span>  

</a>  


<a  
    href="{{ url_for('my_plan') }}"  
    class="active"  
>  

    <i class="fa-solid fa-chart-line"></i>  

    <span>  
        Income  
    </span>  

</a>  


<a href="{{ url_for('team') }}">  

    <i class="fa-solid fa-users"></i>  

    <span>  
        Team  
    </span>  

</a>  


<a href="{{ url_for('team') }}">  

    <i class="fa-solid fa-share-nodes"></i>  

    <span>  
        Share  
    </span>  

</a>  


<a href="{{ url_for('profile') }}">  

    <i class="fa-solid fa-user"></i>  

    <span>  
        My  
    </span>  

</a>

</div>  </nav><!-- COUNTDOWN SCRIPT --><script>  const countdown =  
    document.getElementById("countdown");  

const countdownSub =  
    document.getElementById("countdownSub");  

const claimButton =  
    document.getElementById("claimButton");  


/*  
 * Flask must provide next_income_at.  
 *  
 * Example:  
 *  
 * 2026-08-12T09:30:00+00:00  
 */  

{% if next_income_at %}  

    const nextIncome =  
        new Date(  
            "{{ next_income_at.isoformat() }}"  
        ).getTime();  

{% else %}  

    const nextIncome = null;  

{% endif %}  


function formatCountdown(ms) {  

    if (ms <= 0) {  
        return "00:00:00";  
    }  


    const totalSeconds =  
        Math.floor(ms / 1000);  


    const hours =  
        Math.floor(totalSeconds / 3600);  


    const minutes =  
        Math.floor(  
            (totalSeconds % 3600) / 60  
        );  


    const seconds =  
        totalSeconds % 60;  


    return (  
        String(hours).padStart(2, "0")  
        + ":"  
        + String(minutes).padStart(2, "0")  
        + ":"  
        + String(seconds).padStart(2, "0")  
    );  
}  


function updateCountdown() {  

    if (!countdown) {  
        return;  
    }  


    /*  
     * If the server says income is already  
     * available, show READY.  
     */  

    {% if can_claim %}  

        countdown.textContent =  
            "00:00:00";  

        countdown.classList.add("ready");  

        if (countdownSub) {  
            countdownSub.textContent =  
                "Your income is ready";  
        }  

        if (claimButton) {  

            claimButton.classList.remove(  
                "disabled"  
            );  

            claimButton.innerHTML =  
                '<i class="fa-solid fa-coins"></i> Income Ready';  
        }  

        return;  

    {% endif %}  


    /*  
     * No timestamp was supplied.  
     */  

    if (!nextIncome) {  

        countdown.textContent =  
            "--:--:--";  

        if (countdownSub) {  
            countdownSub.textContent =  
                "Next income time unavailable";  
        }  

        return;  
    }  


    const remaining =  
        nextIncome - Date.now();  


    /*  
     * COUNTDOWN FINISHED  
     */  

    if (remaining <= 0) {  

        countdown.textContent =  
            "00:00:00";  

        countdown.classList.add("ready");  

        if (countdownSub) {  

            countdownSub.textContent =  
                "Your income is ready";  

        }  

        if (claimButton) {  

            claimButton.classList.remove(  
                "disabled"  
            );  

            claimButton.innerHTML =  
                '<i class="fa-solid fa-coins"></i> Income Ready';  

        }  

        return;  
    }  


    /*  
     * COUNTING DOWN  
     */  

    countdown.classList.remove(  
        "ready"  
    );  


    countdown.textContent =  
        formatCountdown(remaining);  


    if (countdownSub) {  

        countdownSub.textContent =  
            "Time remaining until your next income";  

    }  


    if (claimButton) {  

        claimButton.classList.add(  
            "disabled"  
        );  

        claimButton.innerHTML =  
            '<i class="fa-solid fa-clock"></i> Income Not Ready';  

    }  

}  


updateCountdown();  


setInterval(  
    updateCountdown,  
    1000  
);

</script></body>

</html>
