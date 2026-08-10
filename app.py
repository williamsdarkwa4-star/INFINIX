import os
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")

DATABASE_URL = os.environ.get("DATABASE_URL")

# DEMO ONLY:
# This application is a simulated investment dashboard.
# It does not process real-money investments or withdrawals.


PLANS = {
    1: {"name": "Zenith 1", "investment": Decimal("50"), "daily": Decimal("8"), "duration": 30},
    2: {"name": "Zenith 2", "investment": Decimal("100"), "daily": Decimal("20"), "duration": 30},
    3: {"name": "Zenith 3", "investment": Decimal("200"), "daily": Decimal("40"), "duration": 30},
    4: {"name": "Zenith 4", "investment": Decimal("300"), "daily": Decimal("65"), "duration": 30},
    5: {"name": "Zenith 5", "investment": Decimal("500"), "daily": Decimal("100"), "duration": 30},
    6: {"name": "Zenith 6", "investment": Decimal("600"), "daily": Decimal("200"), "duration": 30},
    7: {"name": "Zenith 7", "investment": Decimal("1000"), "daily": Decimal("360"), "duration": 30},
}


# ---------------- DATABASE ----------------

def get_conn():
    if not DATABASE_URL or psycopg2 is None:
        return None
    return psycopg2.connect(DATABASE_URL, sslmode="require")


def init_db():
    conn = get_conn()
    if conn is None:
        raise RuntimeError("DATABASE_URL is missing or psycopg2 is unavailable.")

    cur = conn.cursor()

    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(80) UNIQUE NOT NULL,
                fullname VARCHAR(120) DEFAULT '',
                phone VARCHAR(30) UNIQUE NOT NULL,
                password_hash TEXT,
                withdraw_password_hash TEXT,
                referral_code VARCHAR(100) UNIQUE,
                referred_by VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(80)
        """)
        cur.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS fullname VARCHAR(120) DEFAULT ''
        """)
        cur.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(30)
        """)
        cur.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT
        """)
        cur.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS password TEXT
        """)
        cur.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS withdraw_password_hash TEXT
        """)
        cur.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_code VARCHAR(100)
        """)
        cur.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by VARCHAR(100)
        """)
        cur.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        """)

        cur.execute("""
            UPDATE users
            SET password_hash = password
            WHERE password_hash IS NULL AND password IS NOT NULL
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                deposit_account NUMERIC(14,2) DEFAULT 5.00,
                income_account NUMERIC(14,2) DEFAULT 0,
                referral_account NUMERIC(14,2) DEFAULT 0,
                withdraw_account NUMERIC(14,2) DEFAULT 0
            )
        """)

        cur.execute("""
            ALTER TABLE accounts ADD COLUMN IF NOT EXISTS deposit_account NUMERIC(14,2) DEFAULT 5.00
        """)
        cur.execute("""
            ALTER TABLE accounts ADD COLUMN IF NOT EXISTS income_account NUMERIC(14,2) DEFAULT 0
        """)
        cur.execute("""
            ALTER TABLE accounts ADD COLUMN IF NOT EXISTS referral_account NUMERIC(14,2) DEFAULT 0
        """)
        cur.execute("""
            ALTER TABLE accounts ADD COLUMN IF NOT EXISTS withdraw_account NUMERIC(14,2) DEFAULT 0
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS plans (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                plan_id INTEGER NOT NULL,
                plan_name VARCHAR(120) NOT NULL,
                investment_amount NUMERIC(14,2) NOT NULL,
                daily_income NUMERIC(14,2) NOT NULL,
                duration INTEGER NOT NULL,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_claim_at TIMESTAMP,
                active BOOLEAN DEFAULT TRUE
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                transaction_type VARCHAR(50) NOT NULL,
                amount NUMERIC(14,2) NOT NULL,
                status VARCHAR(30) NOT NULL,
                reference VARCHAR(150),
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS withdrawal_accounts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                account_name VARCHAR(120) NOT NULL,
                phone VARCHAR(30) NOT NULL,
                network VARCHAR(40) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS deposit_requests (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                amount NUMERIC(14,2) NOT NULL,
                reference VARCHAR(150),
                status VARCHAR(30) NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS withdrawal_requests (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                amount NUMERIC(14,2) NOT NULL,
                account_id INTEGER REFERENCES withdrawal_accounts(id) ON DELETE SET NULL,
                status VARCHAR(30) NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,
                username VARCHAR(80) UNIQUE NOT NULL,
                password_hash TEXT
            )
        """)

        cur.execute("""
            ALTER TABLE admins ADD COLUMN IF NOT EXISTS password_hash TEXT
        """)
        cur.execute("""
            ALTER TABLE admins ADD COLUMN IF NOT EXISTS password TEXT
        """)
        cur.execute("""
            ALTER TABLE admins ALTER COLUMN password DROP NOT NULL
        """)

        # Give existing users referral codes.
        cur.execute("""
            SELECT id FROM users
            WHERE referral_code IS NULL OR referral_code = ''
        """)
        for row in cur.fetchall():
            user_id = row[0]
            referral_code = (
                f"ZEN{user_id}{datetime.utcnow().strftime('%y%m%d%H%M%S')}"
                f"{os.urandom(3).hex()}"
            )
            cur.execute("""
                UPDATE users SET referral_code=%s WHERE id=%s
            """, (referral_code, user_id))

        # Ensure every user has an account row.
        cur.execute("""
            INSERT INTO accounts (
                user_id, deposit_account, income_account,
                referral_account, withdraw_account
            )
            SELECT u.id, 5.00, 0, 0, 0
            FROM users u
            LEFT JOIN accounts a ON a.user_id=u.id
            WHERE a.user_id IS NULL
        """)

        # Correctly scoped admin variables.
        admin_username = os.environ.get("ADMIN_USERNAME", "Williams")
        admin_password = os.environ.get("ADMIN_PASSWORD", "Williams12")
        admin_hash = generate_password_hash(admin_password)

        cur.execute("""
            INSERT INTO admins (username, password_hash)
            VALUES (%s, %s)
            ON CONFLICT (username)
            DO UPDATE SET password_hash = EXCLUDED.password_hash
        """, (admin_username, admin_hash))

        required_tables = [
            "users", "accounts", "plans", "transactions",
            "withdrawal_accounts", "deposit_requests",
            "withdrawal_requests", "admins"
        ]

        for table_name in required_tables:
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema='public' AND table_name=%s
                )
            """, (table_name,))
            if not cur.fetchone()[0]:
                raise RuntimeError(f"Required table '{table_name}' was not created.")

        conn.commit()

        print("======================================")
        print("DATABASE INITIALIZATION SUCCESS")
        print("Admin username:", admin_username)
        print("======================================")

    except Exception as exc:
        conn.rollback()
        print("DATABASE INITIALIZATION ERROR:", exc)
        raise

    finally:
        cur.close()
        conn.close()


def query_one(sql, params=()):
    conn = get_conn()
    if conn is None:
        return None
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(sql, params)
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()


def query_all(sql, params=()):
    conn = get_conn()
    if conn is None:
        return []
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def execute(sql, params=(), fetchone=False):
    conn = get_conn()
    if conn is None:
        return None
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


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return query_one("SELECT * FROM users WHERE id=%s", (user_id,))


def current_account(user_id):
    return query_one("SELECT * FROM accounts WHERE user_id=%s", (user_id,))


@app.context_processor
def inject_user():
    return {"logged_user": current_user()}


# ---------------- USER ROUTES ----------------

@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


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
        fullname = request.form.get("fullname", "").strip()
        username = request.form.get("username", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        withdraw_password = request.form.get("withdraw_password", "")

        if not fullname or not username or not phone:
            flash("Please complete all required fields.", "error")
            return render_template("register.html", invite_code=invite_code)

        if not password or not withdraw_password:
            flash("Please enter both passwords.", "error")
            return render_template("register.html", invite_code=invite_code)

        existing_user = query_one("""
            SELECT id FROM users
            WHERE username=%s OR phone=%s
        """, (username, phone))

        if existing_user:
            flash("Username or phone number already exists.", "error")
            return render_template("register.html", invite_code=invite_code)

        if invite_code and not referred_user:
            flash("Invalid referral code.", "error")
            return render_template("register.html", invite_code=invite_code)

        referral_code = (
            f"ZEN{datetime.utcnow().strftime('%y%m%d%H%M%S')}"
            f"{os.urandom(3).hex()}"
        )

        user = execute("""
            INSERT INTO users (
                username, fullname, phone, password_hash,
                withdraw_password_hash, referral_code, referred_by
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
            referred_user["referral_code"] if referred_user else None
        ), fetchone=True)

        execute("""
            INSERT INTO accounts (
                user_id, deposit_account, income_account,
                referral_account, withdraw_account
            )
            VALUES (%s, 5.00, 0, 0, 0)
        """, (user["id"],))

        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html", invite_code=invite_code)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")

        if not phone or not password:
            flash("Please enter your phone number and password.", "error")
            return render_template("login.html")

        user = query_one("""
            SELECT id, username, fullname, phone, password_hash,
                   withdraw_password_hash, referral_code, referred_by, created_at
            FROM users WHERE phone=%s
        """, (phone,))

        if not user:
            flash("Invalid phone number or password.", "error")
            return render_template("login.html")

        stored_password = user.get("password_hash")
        if not stored_password:
            flash("This account has no valid password. Please contact support.", "error")
            return render_template("login.html")

        try:
            valid = check_password_hash(stored_password, password)
        except Exception:
            valid = False

        if valid:
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))

        flash("Invalid phone number or password.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
def dashboard():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    account = current_account(user["id"])
    return render_template("dashboard.html", user=user, account=account, plans=PLANS)


@app.route("/deposit")
def deposit():
    if not current_user():
        return redirect(url_for("login"))
    return render_template("deposit.html")


@app.route("/deposit_success")
def deposit_success():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    reference = request.args.get("reference", "").strip()

    try:
        amount = Decimal(request.args.get("amount", "0"))
    except (InvalidOperation, ValueError):
        amount = Decimal("0")

    if amount < Decimal("45"):
        flash("Minimum demo deposit is GHS 45.", "error")
        return redirect(url_for("deposit"))

    execute("""
        INSERT INTO deposit_requests (user_id, amount, reference)
        VALUES (%s,%s,%s)
    """, (user["id"], amount, reference))

    execute("""
        INSERT INTO transactions
        (user_id, transaction_type, amount, status, reference, description)
        VALUES (%s,'deposit',%s,'pending',%s,'Demo deposit request')
    """, (user["id"], amount, reference))

    return redirect(url_for("transaction_history"))


@app.route("/buy_plan/<int:plan_id>")
def buy_plan(plan_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    if plan_id not in PLANS:
        flash("Plan not found.", "error")
        return redirect(url_for("dashboard"))

    plan = PLANS[plan_id]
    account = current_account(user["id"])

    if Decimal(account["deposit_account"] or 0) < plan["investment"]:
        return render_template(
            "insufficient_balance.html",
            account=account,
            plan={"investment_amount": plan["investment"]}
        )

    db_plan = {
        "id": plan_id,
        "plan_name": plan["name"],
        "investment_amount": plan["investment"],
        "daily_income": plan["daily"],
        "duration": plan["duration"],
    }

    return render_template(
        "confirm_plan.html",
        user=user,
        account=account,
        plan=db_plan
    )


@app.route("/confirm_buy_plan/<int:plan_id>", methods=["POST"])
def confirm_buy_plan(plan_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    if plan_id not in PLANS:
        flash("Plan not found.", "error")
        return redirect(url_for("dashboard"))

    plan = PLANS[plan_id]
    account = current_account(user["id"])
    balance = Decimal(account["deposit_account"] or 0)

    if balance < plan["investment"]:
        return render_template(
            "insufficient_balance.html",
            account=account,
            plan={"investment_amount": plan["investment"]}
        )

    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            UPDATE accounts
            SET deposit_account = deposit_account - %s
            WHERE user_id=%s AND deposit_account >= %s
        """, (plan["investment"], user["id"], plan["investment"]))

        if cur.rowcount != 1:
            conn.rollback()
            flash("Insufficient balance.", "error")
            return redirect(url_for("dashboard"))

        cur.execute("""
            INSERT INTO plans (
                user_id, plan_id, plan_name, investment_amount,
                daily_income, duration
            )
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (
            user["id"], plan_id, plan["name"], plan["investment"],
            plan["daily"], plan["duration"]
        ))

        cur.execute("""
            INSERT INTO transactions
            (user_id, transaction_type, amount, status, description)
            VALUES (%s,'plan_purchase',%s,'successful',%s)
        """, (
            user["id"], plan["investment"], f"Demo plan {plan_id} selected"
        ))

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("my_plan"))


@app.route("/my_plan", methods=["GET", "POST"])
def my_plan():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    plan = query_one("""
        SELECT * FROM plans
        WHERE user_id=%s AND active=TRUE
        ORDER BY id DESC LIMIT 1
    """, (user["id"],))

    can_claim = False

    if plan:
        last_claim = plan["last_claim_at"]
        can_claim = (
            last_claim is None
            or datetime.utcnow() >= last_claim + timedelta(hours=24)
        )

        if request.method == "POST" and can_claim:
            execute("""
                UPDATE accounts
                SET income_account = income_account + %s,
                    withdraw_account = withdraw_account + %s
                WHERE user_id=%s
            """, (plan["daily_income"], plan["daily_income"], user["id"]))

            execute("""
                UPDATE plans SET last_claim_at=%s WHERE id=%s
            """, (datetime.utcnow(), plan["id"]))

            execute("""
                INSERT INTO transactions
                (user_id, transaction_type, amount, status, description)
                VALUES (%s,'income_claim',%s,'successful','Demo daily income claim')
            """, (user["id"], plan["daily_income"]))

            return redirect(url_for("my_plan"))

    return render_template("my_plan.html", plan=plan, can_claim=can_claim)


@app.route("/withdraw")
def withdraw():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    accounts = query_all("""
        SELECT * FROM withdrawal_accounts
        WHERE user_id=%s ORDER BY id DESC
    """, (user["id"],))

    return render_template("withdraw.html", accounts=accounts)


@app.route("/bind_account", methods=["GET", "POST"])
def bind_account():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    if request.method == "POST":
        account_name = request.form.get("account_name", "").strip()
        phone = request.form.get("phone", "").strip()
        network = request.form.get("network", "").strip()

        if not account_name or not phone or not network:
            flash("Please complete the account details.", "error")
        else:
            execute("""
                INSERT INTO withdrawal_accounts
                (user_id, account_name, phone, network)
                VALUES (%s,%s,%s,%s)
            """, (user["id"], account_name, phone, network))
            flash("Withdrawal account saved.", "success")

    accounts = query_all("""
        SELECT * FROM withdrawal_accounts
        WHERE user_id=%s ORDER BY id DESC
    """, (user["id"],))

    return render_template("bind_account.html", accounts=accounts)


@app.route("/request_withdrawal", methods=["POST"])
def request_withdrawal():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    try:
        amount = Decimal(request.form.get("amount", "0"))
    except (InvalidOperation, ValueError):
        amount = Decimal("0")

    password = request.form.get("password", "")
    account_id = request.form.get("account_id")

    if amount < Decimal("30"):
        flash("Minimum demo withdrawal is GHS 30.", "error")
        return redirect(url_for("withdraw"))

    if not user["withdraw_password_hash"]:
        flash("Withdrawal password is not configured.", "error")
        return redirect(url_for("withdraw"))

    try:
        valid_password = check_password_hash(
            user["withdraw_password_hash"], password
        )
    except Exception:
        valid_password = False

    if not valid_password:
        flash("Invalid withdrawal password.", "error")
        return redirect(url_for("withdraw"))

    account = current_account(user["id"])
    balance = Decimal(account["withdraw_account"] or 0)

    if balance < amount:
        flash("Insufficient withdrawal balance.", "error")
        return redirect(url_for("withdraw"))

    if account_id:
        withdrawal_account = query_one("""
            SELECT id FROM withdrawal_accounts
            WHERE id=%s AND user_id=%s
        """, (account_id, user["id"]))
        if not withdrawal_account:
            flash("Invalid withdrawal account.", "error")
            return redirect(url_for("withdraw"))

    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            UPDATE accounts
            SET withdraw_account = withdraw_account - %s
            WHERE user_id=%s AND withdraw_account >= %s
        """, (amount, user["id"], amount))

        if cur.rowcount != 1:
            conn.rollback()
            flash("Insufficient withdrawal balance.", "error")
            return redirect(url_for("withdraw"))

        cur.execute("""
            INSERT INTO withdrawal_requests (user_id, amount, account_id)
            VALUES (%s,%s,%s)
        """, (user["id"], amount, account_id or None))

        cur.execute("""
            INSERT INTO transactions
            (user_id, transaction_type, amount, status, description)
            VALUES (%s,'withdrawal',%s,'pending','Demo withdrawal request')
        """, (user["id"], amount))

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    flash("Withdrawal request submitted for review.", "success")
    return redirect(url_for("transaction_history"))


@app.route("/transaction_history")
def transaction_history():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    transactions = query_all("""
        SELECT * FROM transactions
        WHERE user_id=%s ORDER BY created_at DESC
    """, (user["id"],))

    return render_template("transaction_history.html", transactions=transactions)


@app.route("/team")
def team():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    members = query_all("""
        SELECT id, username, phone, created_at
        FROM users WHERE referred_by=%s
        ORDER BY created_at DESC
    """, (user["referral_code"],))

    account = current_account(user["id"])
    referral_income = account["referral_account"] if account else 0

    return render_template(
        "team.html",
        user=user,
        members=members,
        total_team=len(members),
        referral_income=referral_income
    )


@app.route("/support")
def support():
    return render_template("support.html")


@app.route("/profile")
def profile():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    account = current_account(user["id"])

    return render_template(
        "profile.html",
        user=user,
        deposit_balance=account["deposit_account"],
        withdraw_balance=account["withdraw_account"],
        income_balance=account["income_account"],
        referral_balance=account["referral_account"],
    )


# ---------------- ADMIN ----------------

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "Williams")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Williams12")


def admin_required():
    return session.get("admin_logged_in") is True


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            flash("Administrator login successful.", "success")
            return redirect(url_for("admin_dashboard"))

        flash("Invalid administrator credentials.", "error")

    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))


@app.route("/admin_dashboard")
@app.route("/admin/dashboard")
def admin_dashboard():
    if not admin_required():
        return redirect(url_for("admin_login"))

    total_users = query_one("SELECT COUNT(*) AS count FROM users")["count"]
    pending_deposits = query_one(
        "SELECT COUNT(*) AS count FROM deposit_requests WHERE status='pending'"
    )["count"]
    pending_withdrawals = query_one(
        "SELECT COUNT(*) AS count FROM withdrawal_requests WHERE status='pending'"
    )["count"]

    return render_template(
        "admin_dashboard.html",
        total_users=total_users,
        pending_deposits=pending_deposits,
        pending_withdrawals=pending_withdrawals
    )


@app.route("/admin_users")
@app.route("/admin/users")
def admin_users():
    if not admin_required():
        return redirect(url_for("admin_login"))

    users = query_all("""
        SELECT u.*, a.deposit_account, a.withdraw_account
        FROM users u
        LEFT JOIN accounts a ON a.user_id=u.id
        ORDER BY u.id DESC
    """)

    return render_template("admin_users.html", users=users)


@app.route("/admin/user/<int:user_id>", methods=["GET", "POST"])
def admin_manage_user(user_id):
    if not admin_required():
        return redirect(url_for("admin_login"))

    user = query_one(
        "SELECT * FROM users WHERE id=%s",
        (user_id,)
    )

    if not user:
        return "User not found", 404

    if request.method == "POST":

        action = request.form.get("action", "").strip()

        # ---------------- BALANCE ACTIONS ----------------

        balance_actions = {
            "add_deposit": ("deposit_account", 1),
            "deduct_deposit": ("deposit_account", -1),
            "add_withdraw": ("withdraw_account", 1),
            "deduct_withdraw": ("withdraw_account", -1),
        }

        if action in balance_actions:

            try:
                amount = Decimal(
                    request.form.get("amount", "0") or "0"
                )
            except (InvalidOperation, ValueError):

                flash("Invalid amount.", "error")
                return redirect(
                    url_for(
                        "admin_manage_user",
                        user_id=user_id
                    )
                )

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

            column, multiplier = balance_actions[action]

            if multiplier == 1:

                execute(
                    f"""
                    UPDATE accounts
                    SET {column} = {column} + %s
                    WHERE user_id=%s
                    """,
                    (amount, user_id)
                )

            else:

                execute(
                    f"""
                    UPDATE accounts
                    SET {column} = GREATEST(0, {column} - %s)
                    WHERE user_id=%s
                    """,
                    (amount, user_id)
                )

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

        # ---------------- LOGIN PASSWORD ----------------

        if action == "update_login_password":

            new_password = request.form.get(
                "new_password",
                ""
            )

            if len(new_password) < 6:

                flash(
                    "Login password must be at least 6 characters.",
                    "error"
                )

                return redirect(
                    url_for(
                        "admin_manage_user",
                        user_id=user_id
                    )
                )

            password_hash = generate_password_hash(
                new_password
            )

            execute(
                """
                UPDATE users
                SET password_hash=%s
                WHERE id=%s
                """,
                (password_hash, user_id)
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

        # ---------------- WITHDRAWAL PASSWORD ----------------

        if action == "update_withdraw_password":

            new_password = request.form.get(
                "new_password",
                ""
            )

            if len(new_password) < 6:

                flash(
                    "Withdrawal password must be at least 6 characters.",
                    "error"
                )

                return redirect(
                    url_for(
                        "admin_manage_user",
                        user_id=user_id
                    )
                )

            password_hash = generate_password_hash(
                new_password
            )

            execute(
                """
                UPDATE users
                SET withdraw_password_hash=%s
                WHERE id=%s
                """,
                (password_hash, user_id)
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

    account = current_account(user_id)

    return render_template(
        "admin_manage_user.html",
        user=user,
        account=account
    )


@app.route("/admin_deposit")
@app.route("/admin/deposits")
def admin_deposits():
    if not admin_required():
        return redirect(url_for("admin_login"))

    deposits = query_all("""
        SELECT d.*, u.username, u.phone
        FROM deposit_requests d
        JOIN users u ON u.id=d.user_id
        ORDER BY d.created_at DESC
    """)

    return render_template("admin_deposit.html", deposits=deposits)


@app.route("/admin/deposit/<int:deposit_id>/<action>", methods=["POST"])
def admin_deposit_action(deposit_id, action):
    if not admin_required():
        return redirect(url_for("admin_login"))

    if action not in ("approve", "reject"):
        flash("Invalid deposit action.", "error")
        return redirect(url_for("admin_deposits"))

    deposit = query_one(
        "SELECT * FROM deposit_requests WHERE id=%s",
        (deposit_id,)
    )

    if not deposit or deposit["status"] != "pending":
        flash("Deposit request is no longer pending.", "error")
        return redirect(url_for("admin_deposits"))

    if action == "approve":
        conn = get_conn()
        cur = conn.cursor()

        try:
            cur.execute("""
                UPDATE accounts
                SET deposit_account=deposit_account+%s
                WHERE user_id=%s
            """, (deposit["amount"], deposit["user_id"]))

            cur.execute("""
                UPDATE deposit_requests
                SET status='approved' WHERE id=%s
            """, (deposit_id,))

            if deposit["reference"]:
                cur.execute("""
                    UPDATE transactions
                    SET status='successful'
                    WHERE user_id=%s AND reference=%s AND status='pending'
                """, (deposit["user_id"], deposit["reference"]))

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

    else:
        conn = get_conn()
        cur = conn.cursor()
        try:
            cur.execute("""
                UPDATE deposit_requests
                SET status='rejected' WHERE id=%s
            """, (deposit_id,))

            if deposit["reference"]:
                cur.execute("""
                    UPDATE transactions
                    SET status='failed'
                    WHERE user_id=%s AND reference=%s AND status='pending'
                """, (deposit["user_id"], deposit["reference"]))

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

    flash(f"Deposit {action}d successfully.", "success")
    return redirect(url_for("admin_deposits"))


@app.route("/admin_withdraw")
@app.route("/admin/withdrawals")
def admin_withdrawals():
    if not admin_required():
        return redirect(url_for("admin_login"))

    withdrawals = query_all("""
        SELECT w.*, u.username, u.phone,
               wa.account_name, wa.phone AS account_phone,
               wa.network
        FROM withdrawal_requests w
        JOIN users u ON u.id=w.user_id
        LEFT JOIN withdrawal_accounts wa ON wa.id=w.account_id
        ORDER BY w.created_at DESC
    """)

    return render_template("admin_withdraw.html", withdrawals=withdrawals)


@app.route("/admin/withdraw/<int:withdrawal_id>/<action>", methods=["POST"])
def admin_withdraw_action(withdrawal_id, action):
    if not admin_required():
        return redirect(url_for("admin_login"))

    if action not in ("approve", "reject"):
        flash("Invalid withdrawal action.", "error")
        return redirect(url_for("admin_withdrawals"))

    withdrawal = query_one("""
        SELECT * FROM withdrawal_requests WHERE id=%s
    """, (withdrawal_id,))

    if not withdrawal or withdrawal["status"] != "pending":
        flash("Withdrawal request is no longer pending.", "error")
        return redirect(url_for("admin_withdrawals"))

    if action == "approve":
        execute("""
            UPDATE withdrawal_requests
            SET status='approved' WHERE id=%s
        """, (withdrawal_id,))

        execute("""
            UPDATE transactions
            SET status='successful'
            WHERE user_id=%s
              AND transaction_type='withdrawal'
              AND amount=%s
              AND status='pending'
        """, (withdrawal["user_id"], withdrawal["amount"]))

    else:
        conn = get_conn()
        cur = conn.cursor()
        try:
            cur.execute("""
                UPDATE accounts
                SET withdraw_account=withdraw_account+%s
                WHERE user_id=%s
            """, (withdrawal["amount"], withdrawal["user_id"]))

            cur.execute("""
                UPDATE withdrawal_requests
                SET status='rejected' WHERE id=%s
            """, (withdrawal_id,))

            cur.execute("""
                UPDATE transactions
                SET status='failed'
                WHERE user_id=%s
                  AND transaction_type='withdrawal'
                  AND amount=%s
                  AND status='pending'
            """, (withdrawal["user_id"], withdrawal["amount"]))

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

    flash(f"Withdrawal {action}d successfully.", "success")
    return redirect(url_for("admin_withdrawals"))


@app.route("/admin_bind_accounts")
@app.route("/admin/bind_accounts")
def admin_bind_accounts():
    if not admin_required():
        return redirect(url_for("admin_login"))

    accounts = query_all("""
        SELECT wa.*, u.username, u.phone AS user_phone
        FROM withdrawal_accounts wa
        JOIN users u ON u.id=wa.user_id
        ORDER BY wa.created_at DESC
    """)

    return render_template(
        "admin_bind_accounts.html",
        accounts=accounts
    )


# ---------------- ERROR HANDLERS ----------------

@app.errorhandler(404)
def not_found(error):
    return "Page not found", 404


@app.errorhandler(500)
def server_error(error):
    return "An internal server error occurred.", 500


# Initialize the database when the module is imported by Gunicorn.
with app.app_context():
    init_db()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
