import os
from datetime import datetime, timedelta
from decimal import Decimal

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
# Use a test payment environment only while developing.


PLANS = {
    1: {"name": "Zenith 1", "investment": Decimal("50"), "daily": Decimal("8"), "duration": 30},
    2: {"name": "Zenith 2", "investment": Decimal("100"), "daily": Decimal("20"), "duration": 30},
    3: {"name": "Zenith 3", "investment": Decimal("200"), "daily": Decimal("40"), "duration": 30},
    4: {"name": "Zenith 4", "investment": Decimal("300"), "daily": Decimal("65"), "duration": 30},
    5: {"name": "Zenith  5", "investment": Decimal("500"), "daily": Decimal("100"), "duration": 30},
    6: {"name": "Zenith 6", "investment": Decimal("600"), "daily": Decimal("200"), "duration": 30},
    7: {"name": "Zenith Demo 7", "investment": Decimal("1000"), "daily": Decimal("360"), "duration": 30},
}


def get_conn():
    if not DATABASE_URL or psycopg2 is None:
        return None
    return psycopg2.connect(DATABASE_URL, sslmode="require")


def init_db():
    conn = get_conn()
    if conn is None:
        return

    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(80) UNIQUE NOT NULL,
            fullname VARCHAR(120) DEFAULT '',
            phone VARCHAR(30) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            withdraw_password_hash TEXT,
            referral_code VARCHAR(40) UNIQUE NOT NULL,
            referred_by VARCHAR(40),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            deposit_account NUMERIC(14,2) DEFAULT 0,
            income_account NUMERIC(14,2) DEFAULT 0,
            referral_account NUMERIC(14,2) DEFAULT 0,
            withdraw_account NUMERIC(14,2) DEFAULT 0
        )
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
            transaction_type VARCHAR(30) NOT NULL,
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
        CREATE TABLE IF NOT EXISTS admins (
            id SERIAL PRIMARY KEY,
            username VARCHAR(80) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS deposit_requests (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            amount NUMERIC(14,2) NOT NULL,
            reference VARCHAR(150),
            status VARCHAR(30) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS withdrawal_requests (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            amount NUMERIC(14,2) NOT NULL,
            account_id INTEGER REFERENCES withdrawal_accounts(id),
            status VARCHAR(30) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        INSERT INTO admins (username, password_hash)
        VALUES (%s, %s)
        ON CONFLICT (username) DO NOTHING
    """, ("admin", generate_password_hash(os.environ.get("ADMIN_PASSWORD", "change-me"))))

    conn.commit()
    cur.close()
    conn.close()


def query_one(sql, params=()):
    conn = get_conn()
    if conn is None:
        return None
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql, params)
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def query_all(sql, params=()):
    conn = get_conn()
    if conn is None:
        return []
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def execute(sql, params=(), fetchone=False):
    conn = get_conn()
    if conn is None:
        return None

    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql, params)
    result = cur.fetchone() if fetchone else None
    conn.commit()
    cur.close()
    conn.close()
    return result


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return query_one("SELECT * FROM users WHERE id=%s", (user_id,))


def current_account(user_id):
    return query_one(
        "SELECT * FROM accounts WHERE user_id=%s",
        (user_id,)
    )


@app.context_processor
def inject_user():
    return {"logged_user": current_user()}


@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        fullname = request.form.get("fullname", "").strip()
        username = request.form.get("username", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        withdraw_password = request.form.get("withdraw_password", "")
        ref = request.args.get("ref") or request.form.get("referral_code", "")

        if not username or not phone or not password:
            flash("Please complete all required fields.", "error")
            return render_template("register.html")

        if query_one(
            "SELECT id FROM users WHERE username=%s OR phone=%s",
            (username, phone)
        ):
            flash("Username or phone number already exists.", "error")
            return render_template("register.html")

        referral_code = f"ZEN{datetime.utcnow().strftime('%y%m%d%H%M%S')}{os.urandom(2).hex()}"

        user = execute(
            """
            INSERT INTO users
            (username, fullname, phone, password_hash,
             withdraw_password_hash, referral_code, referred_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                username,
                fullname,
                phone,
                generate_password_hash(password),
                generate_password_hash(withdraw_password) if withdraw_password else None,
                referral_code,
                ref or None,
            ),
            fetchone=True,
        )

        execute(
            "INSERT INTO accounts (user_id) VALUES (%s)",
            (user["id"],)
        )

        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")

        user = query_one(
            "SELECT * FROM users WHERE phone=%s",
            (phone,)
        )

        if user and check_password_hash(user["password_hash"], password):
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
    return render_template(
        "dashboard.html",
        user=user,
        account=account,
        plans=PLANS
    )


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

    reference = request.args.get("reference", "")
    amount = Decimal(request.args.get("amount", "0"))

    if amount < Decimal("45"):
        flash("Minimum demo deposit is GHS 45.", "error")
        return redirect(url_for("deposit"))

    # Demo flow: create a pending request.
    # Do not credit the account directly from a browser callback in production.
    execute(
        """
        INSERT INTO deposit_requests (user_id, amount, reference)
        VALUES (%s,%s,%s)
        """,
        (user["id"], amount, reference)
    )

    execute(
        """
        INSERT INTO transactions
        (user_id, transaction_type, amount, status, reference, description)
        VALUES (%s,'deposit',%s,'pending',%s,'Demo deposit request')
        """,
        (user["id"], amount, reference)
    )

    return render_template(
        "transaction_history.html",
        transactions=query_all(
            "SELECT * FROM transactions WHERE user_id=%s ORDER BY created_at DESC",
            (user["id"],)
        )
    )


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
        db_plan = {
            "investment_amount": plan["investment"]
        }
        return render_template(
            "insufficient_balance.html",
            account=account,
            plan=db_plan
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
        cur.execute(
            """
            UPDATE accounts
            SET deposit_account = deposit_account - %s
            WHERE user_id=%s AND deposit_account >= %s
            """,
            (plan["investment"], user["id"], plan["investment"])
        )

        if cur.rowcount != 1:
            conn.rollback()
            flash("Insufficient balance.", "error")
            return redirect(url_for("dashboard"))

        cur.execute(
            """
            INSERT INTO plans
            (user_id, plan_id, plan_name, investment_amount,
             daily_income, duration)
            VALUES (%s,%s,%s,%s,%s,%s)
            """,
            (
                user["id"],
                plan_id,
                plan["name"],
                plan["investment"],
                plan["daily"],
                plan["duration"],
            )
        )

        cur.execute(
            """
            INSERT INTO transactions
            (user_id, transaction_type, amount, status, description)
            VALUES (%s,'plan_purchase',%s,'successful',%s)
            """,
            (user["id"], plan["investment"], f"Demo plan {plan_id} selected")
        )

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

    plan = query_one(
        """
        SELECT * FROM plans
        WHERE user_id=%s AND active=TRUE
        ORDER BY id DESC
        LIMIT 1
        """,
        (user["id"],)
    )

    can_claim = False

    if plan:
        last_claim = plan["last_claim_at"]
        can_claim = (
            last_claim is None
            or datetime.utcnow() >= last_claim + timedelta(hours=24)
        )

        if request.method == "POST" and can_claim:
            # Demo-only claim mechanism.
            execute(
                """
                UPDATE accounts
                SET income_account = income_account + %s,
                    withdraw_account = withdraw_account + %s
                WHERE user_id=%s
                """,
                (plan["daily_income"], plan["daily_income"], user["id"])
            )

            execute(
                """
                UPDATE plans
                SET last_claim_at=%s
                WHERE id=%s
                """,
                (datetime.utcnow(), plan["id"])
            )

            execute(
                """
                INSERT INTO transactions
                (user_id, transaction_type, amount, status, description)
                VALUES (%s,'income_claim',%s,'successful','Demo daily income claim')
                """,
                (user["id"], plan["daily_income"])
            )

            return redirect(url_for("my_plan"))

    return render_template(
        "my_plan.html",
        plan=plan,
        can_claim=can_claim
    )


@app.route("/withdraw")
def withdraw():
    if not current_user():
        return redirect(url_for("login"))
    return render_template("withdraw.html")


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
            execute(
                """
                INSERT INTO withdrawal_accounts
                (user_id, account_name, phone, network)
                VALUES (%s,%s,%s,%s)
                """,
                (user["id"], account_name, phone, network)
            )
            flash("Withdrawal account saved.", "success")

    accounts = query_all(
        """
        SELECT * FROM withdrawal_accounts
        WHERE user_id=%s
        ORDER BY id DESC
        """,
        (user["id"],)
    )

    return render_template(
        "bind_account.html",
        accounts=accounts
    )


@app.route("/request_withdrawal", methods=["POST"])
def request_withdrawal():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    amount = Decimal(request.form.get("amount", "0"))
    password = request.form.get("password", "")
    account_id = request.form.get("account_id")

    if amount < Decimal("30"):
        flash("Minimum demo withdrawal is GHS 30.", "error")
        return redirect(url_for("withdraw"))

    if not user["withdraw_password_hash"] or not check_password_hash(
        user["withdraw_password_hash"], password
    ):
        flash("Invalid withdrawal password.", "error")
        return redirect(url_for("withdraw"))

    account = current_account(user["id"])
    balance = Decimal(account["withdraw_account"] or 0)

    if balance < amount:
        flash("Insufficient withdrawal balance.", "error")
        return redirect(url_for("withdraw"))

    execute(
        """
        UPDATE accounts
        SET withdraw_account = withdraw_account - %s
        WHERE user_id=%s AND withdraw_account >= %s
        """,
        (amount, user["id"], amount)
    )

    execute(
        """
        INSERT INTO withdrawal_requests
        (user_id, amount, account_id)
        VALUES (%s,%s,%s)
        """,
        (user["id"], amount, account_id or None)
    )

    execute(
        """
        INSERT INTO transactions
        (user_id, transaction_type, amount, status, description)
        VALUES (%s,'withdrawal',%s,'pending','Demo withdrawal request')
        """,
        (user["id"], amount)
    )

    flash("Withdrawal request submitted for review.", "success")
    return redirect(url_for("transaction_history"))


@app.route("/transaction_history")
def transaction_history():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    transactions = query_all(
        """
        SELECT * FROM transactions
        WHERE user_id=%s
        ORDER BY created_at DESC
        """,
        (user["id"],)
    )

    return render_template(
        "transaction_history.html",
        transactions=transactions
    )


@app.route("/team")
def team():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    members = query_all(
        """
        SELECT id, username, phone, created_at
        FROM users
        WHERE referred_by=%s
        ORDER BY created_at DESC
        """,
        (user["referral_code"],)
    )

    referral_income = current_account(user["id"])["referral_account"]

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

def admin_required():
    return session.get("admin_id") is not None


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        admin = query_one(
            "SELECT * FROM admins WHERE username=%s",
            (username,)
        )

        if admin and check_password_hash(admin["password_hash"], password):
            session["admin_id"] = admin["id"]
            return redirect(url_for("admin_dashboard"))

        flash("Invalid administrator credentials.", "error")

    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_id", None)
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

    users = query_all(
        """
        SELECT u.*, a.deposit_account, a.withdraw_account
        FROM users u
        LEFT JOIN accounts a ON a.user_id=u.id
        ORDER BY u.id DESC
        """
    )

    return render_template("admin_users.html", users=users)


@app.route("/admin/user/<int:user_id>", methods=["GET", "POST"])
def admin_manage_user(user_id):
    if not admin_required():
        return redirect(url_for("admin_login"))

    user = query_one("SELECT * FROM users WHERE id=%s", (user_id,))
    if not user:
        return "User not found", 404

    if request.method == "POST":
        action = request.form.get("action")
        amount = Decimal(request.form.get("amount", "0") or "0")

        if action == "add_deposit":
            execute(
                "UPDATE accounts SET deposit_account=deposit_account+%s WHERE user_id=%s",
                (amount, user_id)
            )
        elif action == "deduct_deposit":
            execute(
                """
                UPDATE accounts
                SET deposit_account=GREATEST(deposit_account-%s,0)
                WHERE user_id=%s
                """,
                (amount, user_id)
            )
        elif action == "add_withdraw":
            execute(
                "UPDATE accounts SET withdraw_account=withdraw_account+%s WHERE user_id=%s",
                (amount, user_id)
            )
        elif action == "deduct_withdraw":
            execute(
                """
                UPDATE accounts
                SET withdraw_account=GREATEST(withdraw_account-%s,0)
                WHERE user_id=%s
                """,
                (amount, user_id)
            )
        elif action == "update_login_password":
            new_password = request.form.get("new_password", "")
            if new_password:
                execute(
                    "UPDATE users SET password_hash=%s WHERE id=%s",
                    (generate_password_hash(new_password), user_id)
                )
        elif action == "update_withdraw_password":
            new_password = request.form.get("new_password", "")
            if new_password:
                execute(
                    """
                    UPDATE users
                    SET withdraw_password_hash=%s
                    WHERE id=%s
                    """,
                    (generate_password_hash(new_password), user_id)
                )

        return redirect(url_for("admin_manage_user", user_id=user_id))

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

    deposits = query_all(
        """
        SELECT d.*, u.username, u.phone
        FROM deposit_requests d
        JOIN users u ON u.id=d.user_id
        ORDER BY d.created_at DESC
        """
    )

    return render_template(
        "admin_deposit.html",
        deposits=deposits
    )


@app.route("/admin/deposit/<int:deposit_id>/<action>", methods=["POST"])
def admin_deposit_action(deposit_id, action):
    if not admin_required():
        return redirect(url_for("admin_login"))

    deposit = query_one(
        "SELECT * FROM deposit_requests WHERE id=%s",
        (deposit_id,)
    )

    if not deposit or deposit["status"] != "pending":
        flash("Deposit request is no longer pending.", "error")
        return redirect(url_for("admin_deposits"))

    if action == "approve":
        execute(
            """
            UPDATE accounts
            SET deposit_account=deposit_account+%s
            WHERE user_id=%s
            """,
            (deposit["amount"], deposit["user_id"])
        )

        execute(
            """
            UPDATE deposit_requests
            SET status='approved'
            WHERE id=%s
            """,
            (deposit_id,)
        )

        execute(
            """
            UPDATE transactions
            SET status='successful'
            WHERE user_id=%s
              AND reference=%s
            """,
            (deposit["user_id"], deposit["reference"])
        )

    elif action == "reject":
        execute(
            "UPDATE deposit_requests SET status='rejected' WHERE id=%s",
            (deposit_id,)
        )

        execute(
            """
            UPDATE transactions
            SET status='failed'
            WHERE user_id=%s
              AND reference=%s
            """,
            (deposit["user_id"], deposit["reference"])
        )

    return redirect(url_for("admin_deposits"))


@app.route("/admin_withdraw")
@app.route("/admin/withdrawals")
def admin_withdrawals():
    if not admin_required():
        return redirect(url_for("admin_login"))

    withdrawals = query_all(
        """
        SELECT w.*, u.username, u.phone,
               wa.account_name, wa.phone AS account_phone,
               wa.network
        FROM withdrawal_requests w
        JOIN users u ON u.id=w.user_id
        LEFT JOIN withdrawal_accounts wa ON wa.id=w.account_id
        ORDER BY w.created_at DESC
        """
    )

    return render_template(
        "admin_withdraw.html",
        withdrawals=withdrawals
    )


@app.route("/admin/withdraw/<int:withdrawal_id>/<action>", methods=["POST"])
def admin_withdraw_action(withdrawal_id, action):
    if not admin_required():
        return redirect(url_for("admin_login"))

    withdrawal = query_one(
        "SELECT * FROM withdrawal_requests WHERE id=%s",
        (withdrawal_id,)
    )

    if not withdrawal or withdrawal["status"] != "pending":
        return redirect(url_for("admin_withdrawals"))

    if action == "approve":
        execute(
            """
            UPDATE withdrawal_requests
            SET status='approved'
            WHERE id=%s
            """,
            (withdrawal_id,)
        )

        execute(
            """
            UPDATE transactions
            SET status='successful'
            WHERE user_id=%s
              AND transaction_type='withdrawal'
              AND amount=%s
              AND status='pending'
            """,
            (withdrawal["user_id"], withdrawal["amount"])
        )

    elif action == "reject":
        execute(
            """
            UPDATE accounts
            SET withdraw_account=withdraw_account+%s
            WHERE user_id=%s
            """,
            (withdrawal["amount"], withdrawal["user_id"])
        )

        execute(
            """
            UPDATE withdrawal_requests
            SET status='rejected'
            WHERE id=%s
            """,
            (withdrawal_id,)
        )

        execute(
            """
            UPDATE transactions
            SET status='failed'
            WHERE user_id=%s
              AND transaction_type='withdrawal'
              AND amount=%s
              AND status='pending'
            """,
            (withdrawal["user_id"], withdrawal["amount"])
        )

    return redirect(url_for("admin_withdrawals"))


@app.route("/admin_bind_accounts")
@app.route("/admin/bind_accounts")
def admin_bind_accounts():
    if not admin_required():
        return redirect(url_for("admin_login"))

    accounts = query_all(
        """
        SELECT wa.*, u.username, u.phone AS user_phone
        FROM withdrawal_accounts wa
        JOIN users u ON u.id=wa.user_id
        ORDER BY wa.created_at DESC
        """
    )

    return render_template(
        "admin_bind_accounts.html",
        accounts=accounts
    )


@app.errorhandler(404)
def not_found(error):
    return "Page not found", 404


@app.errorhandler(500)
def server_error(error):
    return "An internal server error occurred.", 500


with app.app_context():
    try:
        init_db()
    except Exception as exc:
        print("Database initialization skipped:", exc)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
