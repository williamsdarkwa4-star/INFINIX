import os
from datetime import datetime, timezone, timedelta
from functools import wraps

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
)
from werkzeug.security import generate_password_hash, check_password_hash


# ============================================================
# ZENITH CAPITAL
# Flask + PostgreSQL
# Demo/Sandbox Financial Platform
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "zenith-capital-demo-secret-change-this"
)

DATABASE_URL = os.environ.get("DATABASE_URL")


# ============================================================
# DATABASE
# ============================================================

def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL environment variable is not configured."
        )

    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor
    )


def query_one(sql, params=()):
    conn = get_db_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    finally:
        conn.close()


def query_all(sql, params=()):
    conn = get_db_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    finally:
        conn.close()


def execute(sql, params=(), fetch=False):
    conn = get_db_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)

            result = None

            if fetch:
                result = cur.fetchone()

            conn.commit()

            return result

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db():

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:

            # ------------------------------------------------
            # USERS
            # ------------------------------------------------

            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    fullname VARCHAR(150) NOT NULL,
                    username VARCHAR(100) NOT NULL UNIQUE,
                    phone VARCHAR(30) NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    withdraw_password_hash TEXT NOT NULL,
                    invite_code VARCHAR(50) UNIQUE NOT NULL,
                    referred_by VARCHAR(50),

                    created_at TIMESTAMP WITH TIME ZONE
                        DEFAULT CURRENT_TIMESTAMP
                )
            """)


            # ------------------------------------------------
            # ACCOUNTS
            # ------------------------------------------------

            cur.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL
                        REFERENCES users(id)
                        ON DELETE CASCADE,

                    deposit_balance NUMERIC(14,2)
                        NOT NULL DEFAULT 10.00,

                    income_balance NUMERIC(14,2)
                        NOT NULL DEFAULT 0.00,

                    referral_balance NUMERIC(14,2)
                        NOT NULL DEFAULT 0.00,

                    withdraw_balance NUMERIC(14,2)
                        NOT NULL DEFAULT 0.00,

                    updated_at TIMESTAMP WITH TIME ZONE
                        DEFAULT CURRENT_TIMESTAMP,

                    UNIQUE(user_id)
                )
            """)


            # ------------------------------------------------
            # PLANS
            # ------------------------------------------------

            cur.execute("""
                CREATE TABLE IF NOT EXISTS plans (
                    id SERIAL PRIMARY KEY,

                    plan_name VARCHAR(100) NOT NULL UNIQUE,

                    investment_amount NUMERIC(14,2)
                        NOT NULL,

                    daily_income NUMERIC(14,2)
                        NOT NULL,

                    duration INTEGER NOT NULL,

                    active BOOLEAN
                        NOT NULL DEFAULT TRUE,

                    created_at TIMESTAMP WITH TIME ZONE
                        DEFAULT CURRENT_TIMESTAMP
                )
            """)


            # ------------------------------------------------
            # USER PLANS
            # ------------------------------------------------

            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_plans (
                    id SERIAL PRIMARY KEY,

                    user_id INTEGER NOT NULL
                        REFERENCES users(id)
                        ON DELETE CASCADE,

                    plan_id INTEGER NOT NULL
                        REFERENCES plans(id),

                    plan_name VARCHAR(100) NOT NULL,

                    investment_amount NUMERIC(14,2)
                        NOT NULL,

                    daily_income NUMERIC(14,2)
                        NOT NULL,

                    duration INTEGER NOT NULL,

                    started_at TIMESTAMP WITH TIME ZONE
                        NOT NULL DEFAULT CURRENT_TIMESTAMP,

                    last_claim_at TIMESTAMP WITH TIME ZONE,

                    next_income_at TIMESTAMP WITH TIME ZONE,

                    expires_at TIMESTAMP WITH TIME ZONE,

                    status VARCHAR(20)
                        NOT NULL DEFAULT 'active'
                )
            """)


            # ------------------------------------------------
            # TRANSACTIONS
            # ------------------------------------------------

            cur.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY,

                    user_id INTEGER NOT NULL
                        REFERENCES users(id)
                        ON DELETE CASCADE,

                    transaction_type VARCHAR(50)
                        NOT NULL,

                    amount NUMERIC(14,2)
                        NOT NULL DEFAULT 0,

                    status VARCHAR(30)
                        NOT NULL DEFAULT 'completed',

                    description TEXT,

                    reference VARCHAR(150),

                    created_at TIMESTAMP WITH TIME ZONE
                        DEFAULT CURRENT_TIMESTAMP
                )
            """)


            # ------------------------------------------------
            # BIND ACCOUNTS
            # ------------------------------------------------

            cur.execute("""
                CREATE TABLE IF NOT EXISTS bind_accounts (
                    id SERIAL PRIMARY KEY,

                    user_id INTEGER NOT NULL
                        REFERENCES users(id)
                        ON DELETE CASCADE,

                    account_name VARCHAR(150) NOT NULL,

                    account_number VARCHAR(50) NOT NULL,

                    network VARCHAR(50) NOT NULL,

                    is_default BOOLEAN
                        NOT NULL DEFAULT FALSE,

                    created_at TIMESTAMP WITH TIME ZONE
                        DEFAULT CURRENT_TIMESTAMP
                )
            """)


            # ------------------------------------------------
            # REFERRALS
            # ------------------------------------------------

            cur.execute("""
                CREATE TABLE IF NOT EXISTS referrals (
                    id SERIAL PRIMARY KEY,

                    referrer_id INTEGER NOT NULL
                        REFERENCES users(id)
                        ON DELETE CASCADE,

                    referred_id INTEGER NOT NULL
                        REFERENCES users(id)
                        ON DELETE CASCADE,

                    level INTEGER NOT NULL,

                    created_at TIMESTAMP WITH TIME ZONE
                        DEFAULT CURRENT_TIMESTAMP,

                    UNIQUE(referrer_id, referred_id)
                )
            """)


            # ------------------------------------------------
            # DEMO DEPOSIT REQUESTS
            # ------------------------------------------------

            cur.execute("""
                CREATE TABLE IF NOT EXISTS deposit_requests (
                    id SERIAL PRIMARY KEY,

                    user_id INTEGER NOT NULL
                        REFERENCES users(id)
                        ON DELETE CASCADE,

                    amount NUMERIC(14,2) NOT NULL,

                    reference VARCHAR(150),

                    status VARCHAR(30)
                        NOT NULL DEFAULT 'pending',

                    created_at TIMESTAMP WITH TIME ZONE
                        DEFAULT CURRENT_TIMESTAMP
                )
            """)


            # ------------------------------------------------
            # DEMO WITHDRAWAL REQUESTS
            # ------------------------------------------------

            cur.execute("""
                CREATE TABLE IF NOT EXISTS withdrawal_requests (
                    id SERIAL PRIMARY KEY,

                    user_id INTEGER NOT NULL
                        REFERENCES users(id)
                        ON DELETE CASCADE,

                    amount NUMERIC(14,2) NOT NULL,

                    fee NUMERIC(14,2)
                        NOT NULL DEFAULT 0,

                    net_amount NUMERIC(14,2)
                        NOT NULL DEFAULT 0,

                    bind_account_id INTEGER,

                    status VARCHAR(30)
                        NOT NULL DEFAULT 'pending',

                    created_at TIMESTAMP WITH TIME ZONE
                        DEFAULT CURRENT_TIMESTAMP
                )
            """)


            # =================================================
            # DEFAULT PLANS
            # =================================================

            plans = [
                ("VIP 1", 50, 8, 100),
                ("VIP 2", 100, 18, 100),
                ("VIP 3", 200, 40, 100),
                ("VIP 4", 300, 65, 100),
                ("VIP 5", 500, 120, 100),
                ("VIP 6", 750, 200, 100),
                ("VIP 7", 1000, 360, 100),
            ]

            for plan_name, investment, daily, duration in plans:

                cur.execute("""
                    INSERT INTO plans
                    (
                        plan_name,
                        investment_amount,
                        daily_income,
                        duration
                    )
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (plan_name)
                    DO UPDATE SET
                        investment_amount = EXCLUDED.investment_amount,
                        daily_income = EXCLUDED.daily_income,
                        duration = EXCLUDED.duration
                """, (
                    plan_name,
                    investment,
                    daily,
                    duration
                ))


        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


# ============================================================
# HELPERS
# ============================================================

def now_utc():
    return datetime.now(timezone.utc)


def make_invite_code(username):
    cleaned = "".join(
        character
        for character in username.upper()
        if character.isalnum()
    )

    timestamp = datetime.now().strftime("%H%M%S")

    return f"ZC{cleaned[:8]}{timestamp}"


def get_current_user():

    user_id = session.get("user_id")

    if not user_id:
        return None

    return query_one("""
        SELECT *
        FROM users
        WHERE id = %s
    """, (user_id,))


def get_current_account():

    user_id = session.get("user_id")

    if not user_id:
        return None

    return query_one("""
        SELECT *
        FROM accounts
        WHERE user_id = %s
    """, (user_id,))


def get_active_user_plan(user_id):

    return query_one("""
        SELECT
            up.*,
            p.active AS plan_available
        FROM user_plans up
        JOIN plans p
            ON p.id = up.plan_id
        WHERE up.user_id = %s
          AND up.status = 'active'
        ORDER BY up.id DESC
        LIMIT 1
    """, (user_id,))


def login_required(view):

    @wraps(view)
    def wrapped(*args, **kwargs):

        if not session.get("user_id"):

            flash(
                "Please login to continue.",
                "error"
            )

            return redirect(url_for("login"))

        return view(*args, **kwargs)

    return wrapped


def admin_required(view):

    @wraps(view)
    def wrapped(*args, **kwargs):

        if not session.get("admin_logged_in"):

            flash(
                "Administrator login required.",
                "error"
            )

            return redirect(
                url_for("admin_login")
            )

        return view(*args, **kwargs)

    return wrapped


# ============================================================
# HOME
# ============================================================

@app.route("/")
def index():

    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


# ============================================================
# REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

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

        referral_code = request.form.get(
            "referral_code",
            ""
        ).strip()

        if not all([
            fullname,
            username,
            phone,
            password,
            withdraw_password
        ]):

            flash(
                "Please complete all required fields.",
                "error"
            )

            return render_template(
                "register.html",
                invite_code=referral_code
            )


        existing = query_one("""
            SELECT id
            FROM users
            WHERE phone = %s
               OR username = %s
        """, (
            phone,
            username
        ))

        if existing:

            flash(
                "Username or phone number already exists.",
                "error"
            )

            return render_template(
                "register.html",
                invite_code=referral_code
            )


        referred_by = None

        if referral_code:

            referrer = query_one("""
                SELECT id
                FROM users
                WHERE invite_code = %s
            """, (referral_code,))

            if referrer:
                referred_by = referral_code


        invite_code = make_invite_code(username)

        while query_one("""
            SELECT id
            FROM users
            WHERE invite_code = %s
        """, (invite_code,)):

            invite_code += "X"


        password_hash = generate_password_hash(
            password
        )

        withdraw_hash = generate_password_hash(
            withdraw_password
        )


        conn = get_db_connection()

        try:

            with conn.cursor() as cur:

                cur.execute("""
                    INSERT INTO users
                    (
                        fullname,
                        username,
                        phone,
                        password_hash,
                        withdraw_password_hash,
                        invite_code,
                        referred_by
                    )
                    VALUES
                    (
                        %s, %s, %s, %s,
                        %s, %s, %s
                    )
                    RETURNING id
                """, (
                    fullname,
                    username,
                    phone,
                    password_hash,
                    withdraw_hash,
                    invite_code,
                    referred_by
                ))

                user = cur.fetchone()

                user_id = user["id"]


                cur.execute("""
                    INSERT INTO accounts
                    (
                        user_id,
                        deposit_balance
                    )
                    VALUES
                    (%s, 10.00)
                """, (user_id,))


                # Create level-1 referral record.
                if referred_by:

                    referrer = cur.execute("""
                        SELECT id
                        FROM users
                        WHERE invite_code = %s
                    """, (referred_by,))


                    cur.execute("""
                        INSERT INTO referrals
                        (
                            referrer_id,
                            referred_id,
                            level
                        )
                        SELECT
                            id,
                            %s,
                            1
                        FROM users
                        WHERE invite_code = %s
                        ON CONFLICT DO NOTHING
                    """, (
                        user_id,
                        referred_by
                    ))


            conn.commit()

        except Exception:

            conn.rollback()
            raise

        finally:

            conn.close()


        flash(
            "Registration successful. Please login.",
            "success"
        )

        return redirect(url_for("login"))


    invite_code = request.args.get(
        "ref",
        ""
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
            WHERE phone = %s
        """, (phone,))


        if not user or not check_password_hash(
            user["password_hash"],
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


    return render_template(
        "login.html"
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():

    user = get_current_user()
    account = get_current_account()
    user_plan = get_active_user_plan(
        user["id"]
    )

    return render_template(
        "dashboard.html",
        user=user,
        account=account,
        user_plan=user_plan
    )


# ============================================================
# AVAILABLE PLANS
# ============================================================

@app.route("/plan")
@login_required
def plan():

    plans = query_all("""
        SELECT *
        FROM plans
        WHERE active = TRUE
        ORDER BY investment_amount ASC
    """)

    user_plan = get_active_user_plan(
        session["user_id"]
    )

    return render_template(
        "plan.html",
        plans=plans,
        user_plan=user_plan
    )


# ============================================================
# BUY PLAN
# ============================================================

@app.route("/buy_plan/<int:plan_id>")
@login_required
def buy_plan(plan_id):

    plan = query_one("""
        SELECT *
        FROM plans
        WHERE id = %s
          AND active = TRUE
    """, (plan_id,))


    if not plan:

        flash(
            "Selected plan is unavailable.",
            "error"
        )

        return redirect(
            url_for("my_plan")
        )


    account = get_current_account()


    return render_template(
        "confirm_plan.html",
        plan=plan,
        account=account
    )


# ============================================================
# CONFIRM PLAN
# ============================================================

@app.route(
    "/confirm_buy_plan/<int:plan_id>",
    methods=["POST"]
)
@login_required
def confirm_buy_plan(plan_id):

    user_id = session["user_id"]


    plan = query_one("""
        SELECT *
        FROM plans
        WHERE id = %s
          AND active = TRUE
    """, (plan_id,))


    if not plan:

        flash(
            "This plan is no longer available.",
            "error"
        )

        return redirect(
            url_for("my_plan")
        )


    existing = get_active_user_plan(
        user_id
    )


    if existing:

        flash(
            "You already have an active plan.",
            "error"
        )

        return redirect(
            url_for("my_plan")
        )


    account = get_current_account()


    investment = float(
        plan["investment_amount"]
    )

    deposit_balance = float(
        account["deposit_balance"]
    )


    if deposit_balance < investment:

        flash(
            "Insufficient deposit balance.",
            "error"
        )

        return redirect(
            url_for(
                "buy_plan",
                plan_id=plan_id
            )
        )


    started = now_utc()

    next_income = (
        started + timedelta(hours=24)
    )

    expires = (
        started
        + timedelta(days=int(plan["duration"]))
    )


    conn = get_db_connection()

    try:

        with conn.cursor() as cur:

            # Deduct plan price.
            cur.execute("""
                UPDATE accounts
                SET deposit_balance =
                    deposit_balance - %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s
                  AND deposit_balance >= %s
            """, (
                investment,
                user_id,
                investment
            ))


            if cur.rowcount != 1:

                raise ValueError(
                    "Unable to deduct plan amount."
                )


            # Create active plan.
            cur.execute("""
                INSERT INTO user_plans
                (
                    user_id,
                    plan_id,
                    plan_name,
                    investment_amount,
                    daily_income,
                    duration,
                    started_at,
                    last_claim_at,
                    next_income_at,
                    expires_at,
                    status
                )
                VALUES
                (
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    NULL, %s, %s,
                    'active'
                )
            """, (
                user_id,
                plan["id"],
                plan["plan_name"],
                plan["investment_amount"],
                plan["daily_income"],
                plan["duration"],
                started,
                next_income,
                expires
            ))


            # Transaction record.
            cur.execute("""
                INSERT INTO transactions
                (
                    user_id,
                    transaction_type,
                    amount,
                    status,
                    description
                )
                VALUES
                (
                    %s,
                    'plan_purchase',
                    %s,
                    'completed',
                    %s
                )
            """, (
                user_id,
                plan["investment_amount"],
                f"Purchased {plan['plan_name']}"
            ))


        conn.commit()

    except Exception:

        conn.rollback()
        raise

    finally:

        conn.close()


    flash(
        f"{plan['plan_name']} activated successfully.",
        "success"
    )

    return redirect(
        url_for("my_plan")
    )


# ============================================================
# MY INCOME
# ============================================================

@app.route("/my_plan")
@login_required
def my_plan():

    user_id = session["user_id"]


    user_plan = get_active_user_plan(
        user_id
    )


    plans = query_all("""
        SELECT *
        FROM plans
        WHERE active = TRUE
        ORDER BY investment_amount ASC
    """)


    can_claim = False
    next_income_at = None


    if user_plan:

        current_time = now_utc()


        # ----------------------------------------------------
        # Check whether plan has expired.
        # ----------------------------------------------------

        expires_at = user_plan["expires_at"]

        if expires_at:

            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(
                    tzinfo=timezone.utc
                )

            if current_time >= expires_at:

                execute("""
                    UPDATE user_plans
                    SET status = 'completed'
                    WHERE id = %s
                """, (
                    user_plan["id"],
                ))

                user_plan = None


        # ----------------------------------------------------
        # Determine income availability.
        # ----------------------------------------------------

        if user_plan:

            next_income_at = (
                user_plan["next_income_at"]
            )


            if next_income_at:

                if next_income_at.tzinfo is None:
                    next_income_at = next_income_at.replace(
                        tzinfo=timezone.utc
                    )


                if current_time >= next_income_at:

                    can_claim = True


    return render_template(
        "my_plan.html",
        user_plan=user_plan,
        plans=plans,
        can_claim=can_claim,
        next_income_at=next_income_at
    )


# ============================================================
# CLAIM DAILY INCOME
# ============================================================

@app.route(
    "/claim_income",
    methods=["POST"]
)
@login_required
def claim_income():

    user_id = session["user_id"]


    conn = get_db_connection()

    try:

        with conn.cursor() as cur:

            cur.execute("""
                SELECT *
                FROM user_plans
                WHERE user_id = %s
                  AND status = 'active'
                ORDER BY id DESC
                LIMIT 1
                FOR UPDATE
            """, (user_id,))

            user_plan = cur.fetchone()


            if not user_plan:

                conn.rollback()

                return jsonify({
                    "success": False,
                    "message": "No active plan."
                }), 400


            current_time = now_utc()


            expires_at = user_plan["expires_at"]

            if expires_at and expires_at.tzinfo is None:
                expires_at = expires_at.replace(
                    tzinfo=timezone.utc
                )


            if expires_at and current_time >= expires_at:

                cur.execute("""
                    UPDATE user_plans
                    SET status = 'completed'
                    WHERE id = %s
                """, (
                    user_plan["id"],
                ))

                conn.commit()

                return jsonify({
                    "success": False,
                    "message": "Your plan has expired."
                }), 400


            next_income_at = (
                user_plan["next_income_at"]
            )


            if next_income_at and next_income_at.tzinfo is None:
                next_income_at = next_income_at.replace(
                    tzinfo=timezone.utc
                )


            # ------------------------------------------------
            # SERVER-SIDE 24-HOUR CHECK
            # ------------------------------------------------

            if (
                next_income_at
                and current_time < next_income_at
            ):

                remaining = (
                    next_income_at - current_time
                ).total_seconds()

                conn.rollback()

                return jsonify({
                    "success": False,
                    "message": "Income is not ready yet.",
                    "remaining_seconds": int(
                        max(0, remaining)
                    )
                }), 400


            daily_income = float(
                user_plan["daily_income"]
            )


            # ------------------------------------------------
            # CREDIT INCOME ACCOUNT
            # ------------------------------------------------

            cur.execute("""
                UPDATE accounts
                SET income_balance =
                    income_balance + %s,
                    withdraw_balance =
                    withdraw_balance + %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s
            """, (
                daily_income,
                daily_income,
                user_id
            ))


            # ------------------------------------------------
            # CALCULATE NEXT INCOME
            # ------------------------------------------------

            new_next_income = (
                current_time
                + timedelta(hours=24)
            )


            cur.execute("""
                UPDATE user_plans
                SET
                    last_claim_at = %s,
                    next_income_at = %s
                WHERE id = %s
            """, (
                current_time,
                new_next_income,
                user_plan["id"]
            ))


            # ------------------------------------------------
            # TRANSACTION
            # ------------------------------------------------

            cur.execute("""
                INSERT INTO transactions
                (
                    user_id,
                    transaction_type,
                    amount,
                    status,
                    description
                )
                VALUES
                (
                    %s,
                    'daily_income',
                    %s,
                    'completed',
                    %s
                )
            """, (
                user_id,
                daily_income,
                f"Daily income from {user_plan['plan_name']}"
            ))


        conn.commit()


        return jsonify({
            "success": True,
            "message": "Daily income credited successfully.",
            "amount": daily_income,
            "next_income_at":
                new_next_income.isoformat()
        })


    except Exception as error:

        conn.rollback()

        app.logger.exception(
            "Income claim error: %s",
            error
        )

        return jsonify({
            "success": False,
            "message": "Unable to process income claim."
        }), 500

    finally:

        conn.close()


# ============================================================
# PROFILE
# ============================================================

@app.route("/profile")
@login_required
def profile():

    user = get_current_user()
    account = get_current_account()


    return render_template(
        "profile.html",
        user=user,
        account=account
    )


# ============================================================
# CHANGE LOGIN PASSWORD
# ============================================================

@app.route(
    "/change_login_password",
    methods=["GET", "POST"]
)
@login_required
def change_login_password():

    if request.method == "POST":

        current_password = request.form.get(
            "current_password",
            ""
        )

        new_password = request.form.get(
            "new_password",
            ""
        )

        confirm_password = request.form.get(
            "confirm_password",
            ""
        )


        user = get_current_user()


        if not check_password_hash(
            user["password_hash"],
            current_password
        ):

            flash(
                "Current password is incorrect.",
                "error"
            )

            return redirect(
                url_for(
                    "change_login_password"
                )
            )


        if len(new_password) < 6:

            flash(
                "New password must be at least 6 characters.",
                "error"
            )

            return redirect(
                url_for(
                    "change_login_password"
                )
            )


        if new_password != confirm_password:

            flash(
                "Passwords do not match.",
                "error"
            )

            return redirect(
                url_for(
                    "change_login_password"
                )
            )


        execute("""
            UPDATE users
            SET password_hash = %s
            WHERE id = %s
        """, (
            generate_password_hash(new_password),
            user["id"]
        ))


        flash(
            "Login password changed successfully.",
            "success"
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
    methods=["GET", "POST"]
)
@login_required
def change_withdraw_password():

    if request.method == "POST":

        current_password = request.form.get(
            "current_password",
            ""
        )

        new_password = request.form.get(
            "new_password",
            ""
        )

        confirm_password = request.form.get(
            "confirm_password",
            ""
        )


        user = get_current_user()


        if not check_password_hash(
            user["withdraw_password_hash"],
            current_password
        ):

            flash(
                "Current withdrawal password is incorrect.",
                "error"
            )

            return redirect(
                url_for(
                    "change_withdraw_password"
                )
            )


        if new_password != confirm_password:

            flash(
                "Passwords do not match.",
                "error"
            )

            return redirect(
                url_for(
                    "change_withdraw_password"
                )
            )


        execute("""
            UPDATE users
            SET withdraw_password_hash = %s
            WHERE id = %s
        """, (
            generate_password_hash(new_password),
            user["id"]
        ))


        flash(
            "Withdrawal password changed successfully.",
            "success"
        )

        return redirect(
            url_for("profile")
        )


    return render_template(
        "change_withdraw_password.html"
    )


# ============================================================
# BIND ACCOUNT
# ============================================================

@app.route(
    "/bind_account",
    methods=["GET", "POST"]
)
@login_required
def bind_account():

    user_id = session["user_id"]


    if request.method == "POST":

        account_name = request.form.get(
            "account_name",
            ""
        ).strip()

        account_number = request.form.get(
            "account_number",
            ""
        ).strip()

        network = request.form.get(
            "network",
            ""
        ).strip()


        if not all([
            account_name,
            account_number,
            network
        ]):

            flash(
                "Please complete all account fields.",
                "error"
            )

            return redirect(
                url_for("bind_account")
            )


        execute("""
            UPDATE bind_accounts
            SET is_default = FALSE
            WHERE user_id = %s
        """, (
            user_id,
        ))


        execute("""
            INSERT INTO bind_accounts
            (
                user_id,
                account_name,
                account_number,
                network,
                is_default
            )
            VALUES
            (
                %s, %s, %s, %s, TRUE
            )
        """, (
            user_id,
            account_name,
            account_number,
            network
        ))


        flash(
            "Withdrawal account added successfully.",
            "success"
        )

        return redirect(
            url_for("bind_account")
        )


    accounts = query_all("""
        SELECT *
        FROM bind_accounts
        WHERE user_id = %s
        ORDER BY is_default DESC, id DESC
    """, (
        user_id,
    ))


    return render_template(
        "bind_account.html",
        accounts=accounts
    )


# ============================================================
# DEMO DEPOSIT
# ============================================================

@app.route(
    "/deposit",
    methods=["GET", "POST"]
)
@login_required
def deposit():

    if request.method == "POST":

        amount_raw = request.form.get(
            "amount",
            ""
        ).strip()


        try:
            amount = float(amount_raw)

        except ValueError:

            flash(
                "Invalid deposit amount.",
                "error"
            )

            return redirect(
                url_for("deposit")
            )


        if amount < 45:

            flash(
                "Minimum demo deposit is GHS 45.",
                "error"
            )

            return redirect(
                url_for("deposit")
            )


        reference = (
            request.form.get(
                "reference"
            )
            or
            f"DEMO-{int(datetime.now().timestamp())}"
        )


        execute("""
            INSERT INTO deposit_requests
            (
                user_id,
                amount,
                reference,
                status
            )
            VALUES
            (
                %s, %s, %s, 'pending'
            )
        """, (
            session["user_id"],
            amount,
            reference
        ))


        execute("""
            INSERT INTO transactions
            (
                user_id,
                transaction_type,
                amount,
                status,
                description,
                reference
            )
            VALUES
            (
                %s,
                'deposit',
                %s,
                'pending',
                'Demo deposit request',
                %s
            )
        """, (
            session["user_id"],
            amount,
            reference
        ))


        flash(
            "Demo deposit request submitted.",
            "success"
        )

        return redirect(
            url_for("transaction_history")
        )


    return render_template(
        "deposit.html"
    )


# ============================================================
# DEMO WITHDRAWAL
# ============================================================

@app.route(
    "/withdraw",
    methods=["GET", "POST"]
)
@login_required
def withdraw():

    user_id = session["user_id"]


    if request.method == "POST":

        amount_raw = request.form.get(
            "amount",
            ""
        ).strip()

        withdrawal_password = request.form.get(
            "withdraw_password",
            ""
        )


        try:
            amount = float(amount_raw)

        except ValueError:

            flash(
                "Invalid withdrawal amount.",
                "error"
            )

            return redirect(
                url_for("withdraw")
            )


        if amount < 30:

            flash(
                "Minimum withdrawal is GHS 30.",
                "error"
            )

            return redirect(
                url_for("withdraw")
            )


        user = get_current_user()
        account = get_current_account()


        if not check_password_hash(
            user["withdraw_password_hash"],
            withdrawal_password
        ):

            flash(
                "Incorrect withdrawal password.",
                "error"
            )

            return redirect(
                url_for("withdraw")
            )


        available = float(
            account["withdraw_balance"]
        )


        if amount > available:

            flash(
                "Insufficient withdrawal balance.",
                "error"
            )

            return redirect(
                url_for("withdraw")
            )


        bound = query_one("""
            SELECT *
            FROM bind_accounts
            WHERE user_id = %s
              AND is_default = TRUE
            ORDER BY id DESC
            LIMIT 1
        """, (
            user_id,
        ))


        if not bound:

            flash(
                "Please bind a withdrawal account first.",
                "error"
            )

            return redirect(
                url_for("bind_account")
            )


        # Demo fee.
        fee = round(
            amount * 0.16,
            2
        )

        net_amount = round(
            amount - fee,
            2
        )


        conn = get_db_connection()

        try:

            with conn.cursor() as cur:

                cur.execute("""
                    UPDATE accounts
                    SET withdraw_balance =
                        withdraw_balance - %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = %s
                      AND withdraw_balance >= %s
                """, (
                    amount,
                    user_id,
                    amount
                ))


                if cur.rowcount != 1:

                    raise ValueError(
                        "Insufficient withdrawal balance."
                    )


                cur.execute("""
                    INSERT INTO withdrawal_requests
                    (
                        user_id,
                        amount,
                        fee,
                        net_amount,
                        bind_account_id,
                        status
                    )
                    VALUES
                    (
                        %s, %s, %s, %s, %s,
                        'pending'
                    )
                """, (
                    user_id,
                    amount,
                    fee,
                    net_amount,
                    bound["id"]
                ))


                cur.execute("""
                    INSERT INTO transactions
                    (
                        user_id,
                        transaction_type,
                        amount,
                        status,
                        description
                    )
                    VALUES
                    (
                        %s,
                        'withdrawal',
                        %s,
                        'pending',
                        %s
                    )
                """, (
                    user_id,
                    amount,
                    f"Demo withdrawal request; fee GHS {fee:.2f}"
                ))


            conn.commit()

        except Exception:

            conn.rollback()
            raise

        finally:

            conn.close()


        flash(
            "Demo withdrawal request submitted.",
            "success"
        )

        return redirect(
            url_for("transaction_history")
        )


    account = get_current_account()


    return render_template(
        "withdraw.html",
        account=account
    )


# ============================================================
# TRANSACTION HISTORY
# ============================================================

@app.route("/transaction_history")
@login_required
def transaction_history():

    transactions = query_all("""
        SELECT *
        FROM transactions
        WHERE user_id = %s
        ORDER BY created_at DESC, id DESC
    """, (
        session["user_id"],
    ))


    return render_template(
        "transaction_history.html",
        transactions=transactions
    )


# ============================================================
# TEAM / REFERRALS
# ============================================================

@app.route("/team")
@login_required
def team():

    user_id = session["user_id"]


    referrals = query_all("""
        SELECT
            u.id,
            u.username,
            u.phone,
            u.created_at,
            r.level
        FROM referrals r
        JOIN users u
            ON u.id = r.referred_id
        WHERE r.referrer_id = %s
        ORDER BY r.created_at DESC
    """, (
        user_id,
    ))


    account = get_current_account()


    return render_template(
        "team.html",
        referrals=referrals,
        account=account
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
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# ============================================================
# ADMIN LOGIN
# ============================================================

ADMIN_USERNAME = os.environ.get(
    "ADMIN_USERNAME",
    "admin"
)

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "change-this-password"
)


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


        if (
            username == ADMIN_USERNAME
            and password == ADMIN_PASSWORD
        ):

            session["admin_logged_in"] = True

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
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():

    total_users = query_one("""
        SELECT COUNT(*) AS count
        FROM users
    """)["count"]


    pending_deposits = query_one("""
        SELECT COUNT(*) AS count
        FROM deposit_requests
        WHERE status = 'pending'
    """)["count"]


    pending_withdrawals = query_one("""
        SELECT COUNT(*) AS count
        FROM withdrawal_requests
        WHERE status = 'pending'
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

@app.route("/admin/users")
@admin_required
def admin_users():

    users = query_all("""
        SELECT
            u.id,
            u.fullname,
            u.username,
            u.phone,
            u.invite_code,
            u.created_at,

            COALESCE(
                a.deposit_balance,
                0
            ) AS deposit_balance,

            COALESCE(
                a.income_balance,
                0
            ) AS income_balance,

            COALESCE(
                a.referral_balance,
                0
            ) AS referral_balance,

            COALESCE(
                a.withdraw_balance,
                0
            ) AS withdraw_balance

        FROM users u

        LEFT JOIN accounts a
            ON a.user_id = u.id

        ORDER BY u.id DESC
    """)


    return render_template(
        "admin_users.html",
        users=users
    )


# ============================================================
# ADMIN DEPOSITS
# ============================================================

@app.route("/admin/deposits")
@admin_required
def admin_deposits():

    deposits = query_all("""
        SELECT
            dr.*,
            u.username,
            u.phone
        FROM deposit_requests dr
        JOIN users u
            ON u.id = dr.user_id
        ORDER BY dr.created_at DESC
    """)


    return render_template(
        "admin_deposits.html",
        deposits=deposits
    )


# ============================================================
# ADMIN WITHDRAWALS
# ============================================================

@app.route("/admin/withdrawals")
@admin_required
def admin_withdrawals():

    withdrawals = query_all("""
        SELECT
            wr.*,
            u.username,
            u.phone
        FROM withdrawal_requests wr
        JOIN users u
            ON u.id = wr.user_id
        ORDER BY wr.created_at DESC
    """)


    return render_template(
        "admin_withdrawals.html",
        withdrawals=withdrawals
    )


# ============================================================
# ADMIN BIND ACCOUNTS
# ============================================================

@app.route("/admin/bind_accounts")
@admin_required
def admin_bind_accounts():

    accounts = query_all("""
        SELECT
            ba.*,
            u.username,
            u.phone
        FROM bind_accounts ba
        JOIN users u
            ON u.id = ba.user_id
        ORDER BY ba.created_at DESC
    """)


    return render_template(
        "admin_bind_accounts.html",
        accounts=accounts
    )


# ============================================================
# ADMIN ADJUST BALANCE
# ============================================================

@app.route(
    "/admin/adjust_balance",
    methods=["POST"]
)
@admin_required
def admin_adjust_balance():

    user_id = request.form.get(
        "user_id",
        type=int
    )

    account_type = request.form.get(
        "account_type",
        ""
    ).strip()

    amount = request.form.get(
        "amount",
        type=float
    )

    action = request.form.get(
        "action",
        "add"
    ).strip()


    allowed_accounts = {
        "deposit_balance",
        "income_balance",
        "referral_balance",
        "withdraw_balance"
    }


    if (
        not user_id
        or account_type not in allowed_accounts
        or amount is None
        or amount < 0
    ):

        flash(
            "Invalid balance adjustment.",
            "error"
        )

        return redirect(
            url_for("admin_users")
        )


    if action == "deduct":

        amount = -amount


    sql = f"""
        UPDATE accounts
        SET {account_type} =
            {account_type} + %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = %s
    """


    execute(
        sql,
        (
            amount,
            user_id
        )
    )


    flash(
        "Balance updated successfully.",
        "success"
    )


    return redirect(
        url_for("admin_users")
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
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    try:

        query_one(
            "SELECT 1 AS ok"
        )

        return jsonify({
            "status": "ok",
            "database": "connected"
        })

    except Exception as error:

        return jsonify({
            "status": "error",
            "database": "unavailable",
            "message": str(error)
        }), 500


# ============================================================
# STARTUP
# ============================================================

try:

    if DATABASE_URL:
        init_db()

except Exception as error:

    print(
        "DATABASE INITIALIZATION ERROR:",
        error
    )


# ============================================================
# LOCAL DEVELOPMENT
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
