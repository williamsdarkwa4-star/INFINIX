from flask import Flask, render_template, request, redirect, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
import os
import secrets
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-key"
)


# =========================================================
# DATABASE
# =========================================================

def get_connection():
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured.")

    return psycopg2.connect(
        database_url,
        cursor_factory=RealDictCursor
    )


def create_tables():
    conn = get_connection()
    cur = conn.cursor()

    try:
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

        cur.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER UNIQUE REFERENCES users(id)
                    ON DELETE CASCADE,
                deposit_account NUMERIC(12,2) DEFAULT 0,
                income_account NUMERIC(12,2) DEFAULT 0,
                referral_account NUMERIC(12,2) DEFAULT 0
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS plans (
                id SERIAL PRIMARY KEY,
                plan_name VARCHAR(100) NOT NULL,
                investment_amount NUMERIC(12,2) NOT NULL,
                daily_income NUMERIC(12,2) NOT NULL,
                duration INTEGER NOT NULL,
                status VARCHAR(20) DEFAULT 'Active'
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_plans (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id)
                    ON DELETE CASCADE,
                plan_id INTEGER REFERENCES plans(id)
                    ON DELETE CASCADE,
                status VARCHAR(20) DEFAULT 'Active',
                purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id)
                    ON DELETE CASCADE,
                transaction_type VARCHAR(50),
                amount NUMERIC(12,2),
                description TEXT,
                status VARCHAR(30),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS bind_accounts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id)
                    ON DELETE CASCADE,
                account_name VARCHAR(100) NOT NULL,
                phone_number VARCHAR(30) NOT NULL,
                network VARCHAR(50) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id)
                    ON DELETE CASCADE,
                referred_user_id INTEGER REFERENCES users(id)
                    ON DELETE CASCADE,
                level INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            SELECT COUNT(*) AS total
            FROM plans
        """)

        if cur.fetchone()["total"] == 0:
            cur.execute("""
                INSERT INTO plans
                (plan_name, investment_amount, daily_income, duration)
                VALUES
                ('VIP 1', 50, 8, 100),
                ('VIP 2', 100, 20, 100),
                ('VIP 3', 200, 40, 100),
                ('VIP 4', 300, 65, 100),
                ('VIP 5', 500, 100, 100),
                ('VIP 6', 600, 200, 100),
                ('VIP 7', 1000, 360, 100)
            """)

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        cur.close()
        conn.close()


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
        "ref", ""
    ).strip().upper()

    if request.method == "POST":

        fullname = request.form.get("fullname", "").strip()
        username = request.form.get("username", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        withdrawal_password = request.form.get(
            "withdrawal_password", ""
        )

        referred_by = request.form.get(
            "referred_by", ""
        ).strip().upper()

        if not all([
            fullname,
            username,
            phone,
            password,
            withdrawal_password
        ]):
            return "Please fill in all required fields."

        if len(password) < 6:
            return "Login password must be at least 6 characters."

        if len(withdrawal_password) < 4:
            return "Withdrawal password must be at least 4 characters."

        conn = get_connection()
        cur = conn.cursor()

        try:

            cur.execute(
                "SELECT id FROM users WHERE username=%s",
                (username,)
            )

            if cur.fetchone():
                return "Username already exists."

            cur.execute(
                "SELECT id FROM users WHERE phone=%s",
                (phone,)
            )

            if cur.fetchone():
                return "Phone number already exists."

            while True:
                referral_code = secrets.token_hex(4).upper()

                cur.execute(
                    """
                    SELECT id
                    FROM users
                    WHERE referral_code=%s
                    """,
                    (referral_code,)
                )

                if not cur.fetchone():
                    break

            valid_referral = None
            inviter_id = None

            if referred_by:
                cur.execute(
                    """
                    SELECT id, referral_code
                    FROM users
                    WHERE referral_code=%s
                    """,
                    (referred_by,)
                )

                inviter = cur.fetchone()

                if inviter:
                    valid_referral = inviter["referral_code"]
                    inviter_id = inviter["id"]

            cur.execute(
                """
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
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,
                (
                    fullname,
                    username,
                    phone,
                    generate_password_hash(password),
                    generate_password_hash(
                        withdrawal_password
                    ),
                    referral_code,
                    valid_referral
                )
            )

            user_id = cur.fetchone()["id"]

            cur.execute(
                """
                INSERT INTO accounts
                (user_id)
                VALUES (%s)
                """,
                (user_id,)
            )

            if inviter_id:
                cur.execute(
                    """
                    INSERT INTO referrals
                    (user_id, referred_user_id, level)
                    VALUES (%s,%s,1)
                    """,
                    (inviter_id, user_id)
                )

            conn.commit()

            return redirect(url_for("login"))

        except Exception:
            conn.rollback()
            return "Registration could not be completed."

        finally:
            cur.close()
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

        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")

        if not phone or not password:
            return "Please enter your phone number and password."

        conn = get_connection()
        cur = conn.cursor()

        try:
            cur.execute(
                """
                SELECT *
                FROM users
                WHERE phone=%s
                """,
                (phone,)
            )

            user = cur.fetchone()

            if not user:
                return "Invalid phone number or password."

            if not check_password_hash(
                user["login_password"],
                password
            ):
                return "Invalid phone number or password."

            session.clear()
            session["user_id"] = user["id"]

            return redirect(url_for("dashboard"))

        finally:
            cur.close()
            conn.close()

    return render_template("login.html")


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_connection()
    cur = conn.cursor()

    try:

        user_id = session["user_id"]

        cur.execute(
            """
            SELECT *
            FROM users
            WHERE id=%s
            """,
            (user_id,)
        )

        user = cur.fetchone()

        if not user:
            session.clear()
            return redirect(url_for("login"))

        cur.execute(
            """
            SELECT *
            FROM accounts
            WHERE user_id=%s
            """,
            (user_id,)
        )

        account = cur.fetchone()

        cur.execute(
            """
            SELECT *
            FROM plans
            WHERE status='Active'
            ORDER BY id
            """
        )

        plans = cur.fetchall()

        cur.execute(
            """
            SELECT COUNT(*) AS total
            FROM referrals
            WHERE user_id=%s
            """,
            (user_id,)
        )

        referral_count = cur.fetchone()["total"]

        return render_template(
            "dashboard.html",
            user=user,
            account=account,
            plans=plans,
            referral_count=referral_count
        )

    finally:
        cur.close()
        conn.close()


# =========================================================
# PLAN CHECK
# =========================================================

@app.route("/buy_plan/<int:plan_id>")
def buy_plan(plan_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_connection()
    cur = conn.cursor()

    try:

        cur.execute(
            """
            SELECT *
            FROM plans
            WHERE id=%s
            AND status='Active'
            """,
            (plan_id,)
        )

        plan = cur.fetchone()

        if not plan:
            return "Plan not found."

        cur.execute(
            """
            SELECT *
            FROM accounts
            WHERE user_id=%s
            """,
            (session["user_id"],)
        )

        account = cur.fetchone()

        if not account:
            return "Account not found."

        # Balance is checked BEFORE confirmation.
        if account["deposit_account"] < plan["investment_amount"]:
            return render_template(
                "insufficient_balance.html",
                plan=plan,
                account=account
            )

        return render_template(
            "confirm_plan.html",
            plan=plan,
            account=account
        )

    finally:
        cur.close()
        conn.close()


# =========================================================
# PLAN CONFIRMATION
# =========================================================

@app.route(
    "/confirm_buy_plan/<int:plan_id>",
    methods=["POST"]
)
def confirm_buy_plan(plan_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_connection()
    cur = conn.cursor()

    try:

        user_id = session["user_id"]

        cur.execute(
            """
            SELECT *
            FROM plans
            WHERE id=%s
            AND status='Active'
            """,
            (plan_id,)
        )

        plan = cur.fetchone()

        if not plan:
            return "Plan is no longer available."

        cur.execute(
            """
            SELECT *
            FROM accounts
            WHERE user_id=%s
            FOR UPDATE
            """,
            (user_id,)
        )

        account = cur.fetchone()

        if not account:
            return "Account not found."

        # Final balance check.
        if account["deposit_account"] < plan["investment_amount"]:
            conn.rollback()

            return render_template(
                "insufficient_balance.html",
                plan=plan,
                account=account
            )

        cur.execute(
            """
            UPDATE accounts
            SET deposit_account =
                deposit_account - %s
            WHERE user_id=%s
            """,
            (
                plan["investment_amount"],
                user_id
            )
        )

        cur.execute(
            """
            INSERT INTO user_plans
            (user_id, plan_id, status)
            VALUES (%s,%s,'Active')
            """,
            (user_id, plan_id)
        )

        cur.execute(
            """
            INSERT INTO transactions
            (
                user_id,
                transaction_type,
                amount,
                description,
                status
            )
            VALUES (%s,%s,%s,%s,%s)
            """,
            (
                user_id,
                "Demo Plan Purchase",
                plan["investment_amount"],
                "Demo purchase of " + plan["plan_name"],
                "Successful"
            )
        )

        conn.commit()

        return redirect(url_for("my_plan"))

    except Exception:
        conn.rollback()
        return "The demo purchase could not be completed."

    finally:
        cur.close()
        conn.close()


# =========================================================
# MY PLAN
# =========================================================

@app.route("/my_plan")
def my_plan():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_connection()
    cur = conn.cursor()

    try:

        cur.execute(
            """
            SELECT
                user_plans.*,
                plans.plan_name,
                plans.investment_amount,
                plans.daily_income,
                plans.duration
            FROM user_plans
            JOIN plans
                ON plans.id=user_plans.plan_id
            WHERE user_plans.user_id=%s
            ORDER BY user_plans.id DESC
            """,
            (session["user_id"],)
        )

        user_plans = cur.fetchall()

        return render_template(
            "my_plan.html",
            user_plans=user_plans
        )

    finally:
        cur.close()
        conn.close()


# =========================================================
# PROFILE
# =========================================================

@app.route("/profile")
def profile():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_connection()
    cur = conn.cursor()

    try:

        cur.execute(
            "SELECT * FROM users WHERE id=%s",
            (session["user_id"],)
        )

        user = cur.fetchone()

        cur.execute(
            "SELECT * FROM accounts WHERE user_id=%s",
            (session["user_id"],)
        )

        account = cur.fetchone()

        return render_template(
            "profile.html",
            user=user,
            account=account
        )

    finally:
        cur.close()
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
        return redirect(url_for("login"))

    conn = get_connection()
    cur = conn.cursor()

    try:

        if request.method == "POST":

            account_name = request.form.get(
                "account_name", ""
            ).strip()

            phone_number = request.form.get(
                "phone_number", ""
            ).strip()

            network = request.form.get(
                "network", ""
            ).strip()

            if not account_name or not phone_number or not network:
                return "Please complete all fields."

            cur.execute(
                """
                INSERT INTO bind_accounts
                (
                    user_id,
                    account_name,
                    phone_number,
                    network
                )
                VALUES (%s,%s,%s,%s)
                """,
                (
                    session["user_id"],
                    account_name,
                    phone_number,
                    network
                )
            )

            conn.commit()

            return redirect(url_for("bind_account"))

        cur.execute(
            """
            SELECT *
            FROM bind_accounts
            WHERE user_id=%s
            ORDER BY id DESC
            """,
            (session["user_id"],)
        )

        accounts = cur.fetchall()

        return render_template(
            "bind_account.html",
            accounts=accounts
        )

    finally:
        cur.close()
        conn.close()


# =========================================================
# TEAM
# =========================================================

@app.route("/team")
def team():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_connection()
    cur = conn.cursor()

    try:

        cur.execute(
            """
            SELECT referral_code
            FROM users
            WHERE id=%s
            """,
            (session["user_id"],)
        )

        user = cur.fetchone()

        if not user:
            return redirect(url_for("login"))

        cur.execute(
            """
            SELECT *
            FROM users
            WHERE referred_by=%s
            ORDER BY id DESC
            """,
            (user["referral_code"],)
        )

        level1 = cur.fetchall()

        level2 = []

        for member in level1:
            cur.execute(
                """
                SELECT *
                FROM users
                WHERE referred_by=%s
                """,
                (member["referral_code"],)
            )

            level2.extend(cur.fetchall())

        level3 = []

        for member in level2:
            cur.execute(
                """
                SELECT *
                FROM users
                WHERE referred_by=%s
                """,
                (member["referral_code"],)
            )

            level3.extend(cur.fetchall())

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
        cur.close()
        conn.close()


# =========================================================
# TRANSACTION HISTORY
# =========================================================

@app.route("/transaction_history")
def transaction_history():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_connection()
    cur = conn.cursor()

    try:

        cur.execute(
            """
            SELECT *
            FROM transactions
            WHERE user_id=%s
            ORDER BY id DESC
            """,
            (session["user_id"],)
        )

        transactions = cur.fetchall()

        return render_template(
            "transaction_history.html",
            transactions=transactions
        )

    finally:
        cur.close()
        conn.close()


# =========================================================
# DEMO DEPOSIT
# =========================================================

@app.route("/deposit", methods=["GET", "POST"])
def deposit():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        try:
            amount = float(
                request.form.get("amount", 0)
            )
        except ValueError:
            amount = 0

        if amount < 45:
            return "Demo deposit minimum is GHS 45."

        conn = get_connection()
        cur = conn.cursor()

        try:

            cur.execute(
                """
                UPDATE accounts
                SET deposit_account =
                    deposit_account + %s
                WHERE user_id=%s
                """,
                (
                    amount,
                    session["user_id"]
                )
            )

            cur.execute(
                """
                INSERT INTO transactions
                (
                    user_id,
                    transaction_type,
                    amount,
                    description,
                    status
                )
                VALUES (%s,%s,%s,%s,%s)
                """,
                (
                    session["user_id"],
                    "Demo Deposit",
                    amount,
                    "Sandbox deposit",
                    "Successful"
                )
            )

            conn.commit()

            return redirect(url_for("dashboard"))

        finally:
            cur.close()
            conn.close()

    return render_template("deposit.html")


# =========================================================
# DEMO WITHDRAWAL
# =========================================================

@app.route("/withdraw", methods=["GET", "POST"])
def withdraw():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        try:
            amount = float(
                request.form.get("amount", 0)
            )
        except ValueError:
            amount = 0

        if amount < 30:
            return "Demo withdrawal minimum is GHS 30."

        conn = get_connection()
        cur = conn.cursor()

        try:

            cur.execute(
                """
                SELECT income_account
                FROM accounts
                WHERE user_id=%s
                """,
                (session["user_id"],)
            )

            account = cur.fetchone()

            if not account or account["income_account"] < amount:
                return "Insufficient demo balance."

            # Demo only. No real payment is sent.
            fee = amount * 0.16
            final_amount = amount - fee

            cur.execute(
                """
                UPDATE accounts
                SET income_account =
                    income_account - %s
                WHERE user_id=%s
                """,
                (amount, session["user_id"])
            )

            cur.execute(
                """
                INSERT INTO transactions
                (
                    user_id,
                    transaction_type,
                    amount,
                    description,
                    status
                )
                VALUES (%s,%s,%s,%s,%s)
                """,
                (
                    session["user_id"],
                    "Demo Withdrawal",
                    final_amount,
                    "Sandbox withdrawal; 16% demo fee",
                    "Pending"
                )
            )

            conn.commit()

            return redirect(
                url_for("transaction_history")
            )

        finally:
            cur.close()
            conn.close()

    return render_template("withdraw.html")


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get("PORT", 5000)
        ),
        debug=False
    )
