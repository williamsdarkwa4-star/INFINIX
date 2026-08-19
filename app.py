#!/usr/bin/env python3
"""
app.py - Complete application

Key behavior:
- New users receive MIN_WITHDRAWAL (GHS 30.00) in withdraw_account at registration.
- Withdrawals are allowed only when the user has at least one active plan.
- All routes included; syntax issues fixed.
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from pydantic import BaseSettings, Field
from werkzeug.security import check_password_hash, generate_password_hash

# Optional import of psycopg2; raise helpful error if not available when DB used.
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except Exception:  # pragma: no cover - environment dependent
    psycopg2 = None
    RealDictCursor = None

# ============================================================
# CONFIGURATION
# ============================================================


class Settings(BaseSettings):
    SECRET_KEY: str = Field("change-this-secret-key", env="SECRET_KEY")
    DATABASE_URL: Optional[str] = Field(None, env="DATABASE_URL")
    ADMIN_USERNAME: str = Field("Williams", env="ADMIN_USERNAME")
    ADMIN_PASSWORD: str = Field("Williams12", env="ADMIN_PASSWORD")
    PORT: int = Field(5000, env="PORT")
    FLASK_DEBUG: bool = Field(False, env="FLASK_DEBUG")
    MAX_CONTENT_LENGTH: int = Field(5 * 1024 * 1024)  # 5 MB
    SESSION_PERMANENT_DAYS: int = Field(7, env="SESSION_PERMANENT_DAYS")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# ============================================================
# FLASK APP & LOGGING
# ============================================================

app = Flask(__name__)
app.secret_key = settings.SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = settings.MAX_CONTENT_LENGTH
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "False").lower() in (
    "1",
    "true",
    "yes",
)
app.permanent_session_lifetime = timedelta(days=settings.SESSION_PERMANENT_DAYS)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("zenith.app")

# ============================================================
# PLATFORM SETTINGS & PLANS
# ============================================================

MIN_DEPOSIT = Decimal("100.00")
MIN_WITHDRAWAL = Decimal("30.00")
STARTING_DEPOSIT_BALANCE = Decimal("0")
CLAIM_INTERVAL_HOURS = 24

REFERRAL_PERCENTS: List[Decimal] = [Decimal("0.20"), Decimal("0.03"), Decimal("0.01")]

PLANS = {
    1: {"name": "INFINIX 1", "investment": Decimal("100.00"), "daily": Decimal("20.00"), "duration": 180},
    2: {"name": "INFINIX 2", "investment": Decimal("250.00"), "daily": Decimal("45.00"), "duration": 180},
    3: {"name": "INFINIX 3", "investment": Decimal("600.00"), "daily": Decimal("120.00"), "duration": 180},
    4: {"name": "INFININX 4", "investment": Decimal("1000.00"), "daily": Decimal("200.00"), "duration": 180},
    5: {"name": "INFINIX 5", "investment": Decimal("2500.00"), "daily": Decimal("500.00"), "duration": 180},
    6: {"name": "INFINIX 6", "investment": Decimal("5000.00"), "daily": Decimal("1000.00"), "duration": 180},
    7: {"name": "INFINIX 7", "investment": Decimal("8000.00"), "daily": Decimal("1600.00"), "duration": 180},
    8: {"name": "INFINIX 8", "investment": Decimal("10000.00"), "daily": Decimal("2000.00"), "duration": 180},
    9: {"name": "INFINIX 9", "investment": Decimal("20000.00"), "daily": Decimal("3600.00"), "duration": 180},
}

# ============================================================
# UTILITIES
# ============================================================


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def money(value: Any) -> Decimal:
    if value is None:
        return Decimal("0.00")
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")


def parse_amount(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not amount.is_finite() or amount <= 0:
        return None
    return amount.quantize(Decimal("0.01"))


def generate_referral_code() -> str:
    return "INFIN" + uuid.uuid4().hex[:12].upper()


def generate_reference(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


def fetch_id(row: Optional[Any], key: str = "id"):
    """
    Safely extract an 'id' (or other single value) from a DB cursor.fetchone() row.
    """
    if row is None:
        return None
    try:
        if isinstance(row, dict):
            if key in row:
                return row.get(key)
            if len(row) == 1:
                return next(iter(row.values()))
            return None
        if isinstance(row, (list, tuple, Sequence)):
            return row[0]
        return getattr(row, key, None)
    except Exception:
        return None


# ============================================================
# DATABASE: connection & helpers
# ============================================================


def _ensure_psycopg2_available():
    if psycopg2 is None:
        raise RuntimeError("psycopg2 is required but not installed. Set up DATABASE_URL only after installing dependencies.")


def get_conn():
    if not settings.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured.")
    _ensure_psycopg2_available()
    return psycopg2.connect(settings.DATABASE_URL, sslmode="require")


@contextmanager
def db_cursor(commit: bool = False, dict_cursor: bool = True):
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor if dict_cursor else None)
        try:
            yield cur
            if commit:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
    finally:
        conn.close()


def query_one(sql: str, params: Iterable = ()) -> Optional[Dict[str, Any]]:
    with db_cursor(commit=False, dict_cursor=True) as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def query_all(sql: str, params: Iterable = ()) -> List[Dict[str, Any]]:
    with db_cursor(commit=False, dict_cursor=True) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
        return rows or []


def execute(sql: str, params: Iterable = ()):
    with db_cursor(commit=True, dict_cursor=False) as cur:
        cur.execute(sql, params)
        return True


# ============================================================
# ACCOUNT HELPERS
# ============================================================


def ensure_account(cur, user_id: int, starting_balance: Decimal = Decimal("0.00")) -> None:
    """
    Ensure an accounts row exists for user_id. If not present, create it.
    Newly created accounts will have withdraw_account initialized to MIN_WITHDRAWAL.
    """
    cur.execute("SELECT user_id FROM accounts WHERE user_id=%s FOR UPDATE", (user_id,))
    if cur.fetchone():
        return
    cur.execute(
        """
        INSERT INTO accounts (
            user_id, deposit_account, income_account, referral_account, withdraw_account
        )
        VALUES (%s, %s, 0, 0, %s)
        ON CONFLICT (user_id) DO NOTHING
        """,
        (user_id, starting_balance, MIN_WITHDRAWAL),
    )


# ============================================================
# DATABASE INITIALIZATION
# ============================================================


def init_db():
    _ensure_psycopg2_available()
    conn = get_conn()
    cur = conn.cursor()
    try:
        # users
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(120),
                fullname VARCHAR(200) DEFAULT '',
                phone VARCHAR(50),
                password_hash TEXT,
                withdraw_password_hash TEXT,
                password TEXT,
                withdraw_password TEXT,
                referral_code VARCHAR(120),
                referred_by VARCHAR(120),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )

        # accounts
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                deposit_account NUMERIC(14,2) NOT NULL DEFAULT 0,
                income_account NUMERIC(14,2) NOT NULL DEFAULT 0,
                referral_account NUMERIC(14,2) NOT NULL DEFAULT 0,
                withdraw_account NUMERIC(14,2) NOT NULL DEFAULT 30.00
            )"""
        )

        # plans
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS plans (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                plan_id INTEGER NOT NULL,
                plan_name VARCHAR(120) NOT NULL,
                investment_amount NUMERIC(14,2) NOT NULL,
                daily_income NUMERIC(14,2) NOT NULL,
                duration INTEGER NOT NULL,
                started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_claim_at TIMESTAMP,
                active BOOLEAN NOT NULL DEFAULT TRUE
            )"""
        )

        # transactions
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                transaction_type VARCHAR(60) NOT NULL,
                amount NUMERIC(14,2) NOT NULL,
                status VARCHAR(40) NOT NULL,
                reference VARCHAR(200),
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )

        # withdrawal_accounts
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS withdrawal_accounts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                account_name VARCHAR(150) NOT NULL,
                phone VARCHAR(50) NOT NULL,
                network VARCHAR(60) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )

        # deposit_requests
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS deposit_requests (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                amount NUMERIC(14,2) NOT NULL,
                payment_number VARCHAR(80),
                screenshot TEXT,
                screenshot_data BYTEA,
                screenshot_mime VARCHAR(100),
                reference VARCHAR(200),
                status VARCHAR(40) NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )

        # withdrawal_requests
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS withdrawal_requests (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                amount NUMERIC(14,2) NOT NULL,
                account_id INTEGER REFERENCES withdrawal_accounts(id) ON DELETE SET NULL,
                status VARCHAR(40) NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )

        # admins
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,
                username VARCHAR(120) UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )"""
        )

        # invites
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS invites (
                id SERIAL PRIMARY KEY,
                token VARCHAR(120) UNIQUE NOT NULL,
                owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                amount NUMERIC(14,2) NOT NULL DEFAULT 0,
                approved BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )

        # Backfill missing referral codes
        cur.execute("SELECT id FROM users WHERE referral_code IS NULL OR referral_code=''")
        rows = cur.fetchall() or []
        for (uid,) in rows:
            cur.execute("UPDATE users SET referral_code=%s WHERE id=%s", (generate_referral_code(), uid))

        # Ensure every user has an account
        cur.execute(
            """
            SELECT u.id FROM users u
            LEFT JOIN accounts a ON a.user_id=u.id
            WHERE a.user_id IS NULL
            """
        )
        rows = cur.fetchall() or []
        for (uid,) in rows:
            cur.execute(
                """
                INSERT INTO accounts (user_id, deposit_account, income_account, referral_account, withdraw_account)
                VALUES (%s, %s, 0, 0, %s)
                ON CONFLICT (user_id) DO NOTHING
                """,
                (uid, STARTING_DEPOSIT_BALANCE, MIN_WITHDRAWAL),
            )

        # Ensure admin account
        admin_hash = generate_password_hash(settings.ADMIN_PASSWORD)
        cur.execute("SELECT id FROM admins WHERE username=%s", (settings.ADMIN_USERNAME,))
        if cur.fetchone():
            cur.execute("UPDATE admins SET password_hash=%s WHERE username=%s", (admin_hash, settings.ADMIN_USERNAME))
        else:
            cur.execute("INSERT INTO admins (username, password_hash) VALUES (%s, %s)", (settings.ADMIN_USERNAME, admin_hash))

        # Indexes
        indices = [
            "CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone)",
            "CREATE INDEX IF NOT EXISTS idx_users_referral ON users(referral_code)",
            "CREATE INDEX IF NOT EXISTS idx_users_referred_by ON users(referred_by)",
            "CREATE INDEX IF NOT EXISTS idx_plans_user_active ON plans(user_id,active)",
            "CREATE INDEX IF NOT EXISTS idx_deposit_requests_status ON deposit_requests(status)",
            "CREATE INDEX IF NOT EXISTS idx_withdrawals_status ON withdrawal_requests(status)",
            "CREATE INDEX IF NOT EXISTS idx_invites_token ON invites(token)",
        ]
        for stmt in indices:
            cur.execute(stmt)

        conn.commit()
        logger.info("Database initialized successfully.")
    except Exception:
        conn.rollback()
        logger.exception("DATABASE INITIALIZATION ERROR")
        raise
    finally:
        cur.close()
        conn.close()


# ============================================================
# AUTH & CURRENT USER HELPERS
# ============================================================


def current_user() -> Optional[Dict[str, Any]]:
    uid = session.get("user_id")
    if not uid:
        return None
    return query_one("SELECT * FROM users WHERE id=%s", (uid,))


def current_account(user_id: int) -> Dict[str, Any]:
    acc = query_one("SELECT * FROM accounts WHERE user_id=%s", (user_id,))
    if acc:
        return acc
    execute(
        """
        INSERT INTO accounts (user_id, deposit_account, income_account, referral_account, withdraw_account)
        VALUES (%s, %s, 0, 0, %s) ON CONFLICT (user_id) DO NOTHING
        """,
        (user_id, STARTING_DEPOSIT_BALANCE, MIN_WITHDRAWAL),
    )
    return query_one("SELECT * FROM accounts WHERE user_id=%s", (user_id,))


def withdrawable_balance(account: Optional[Dict[str, Any]]) -> Decimal:
    if not account:
        return Decimal("0.00")
    return money(account.get("withdraw_account")) + money(account.get("referral_account"))


def account_for_display(account: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not account:
        return account
    res = dict(account)
    res["withdraw_account"] = withdrawable_balance(account)
    res["withdrawable_balance"] = res["withdraw_account"]
    return res


@app.context_processor
def inject_user():
    return {"logged_user": current_user()}


# ============================================================
# ROUTES (kept names and behavior)
# ============================================================


@app.route("/")
def index():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin_dashboard"))
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


# ---------------------------
# Registration
# ---------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    invite_code = (
        request.args.get("ref", "").strip()
        or request.form.get("referred_by", "").strip()
        or request.form.get("referral_code", "").strip()
    )
    referred_user = None
    if invite_code:
        referred_user = query_one("SELECT id, username, referral_code FROM users WHERE referral_code=%s", (invite_code,))

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

        existing = query_one("SELECT id FROM users WHERE username=%s OR phone=%s", (username, phone))
        if existing:
            flash("Username or phone number already exists.", "error")
            return render_template("register.html", invite_code=invite_code)

        if invite_code and not referred_user:
            flash("Invalid referral code.", "error")
            return render_template("register.html", invite_code=invite_code)

        referral_code = generate_referral_code()
        try:
            with db_cursor(commit=True, dict_cursor=True) as cur:
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
                row = cur.fetchone()
                new_user_id = fetch_id(row, "id")
                if not new_user_id:
                    # Defensive: if DB didn't return id, try to find inserted user by phone/username
                    logger.warning("INSERT returned no id when registering user; attempting lookup by phone/username.")
                    maybe = query_one("SELECT id FROM users WHERE phone=%s OR username=%s ORDER BY id DESC LIMIT 1", (phone, username))
                    new_user_id = fetch_id(maybe, "id")
                    if not new_user_id:
                        raise RuntimeError("Could not determine new user id after insert.")
                # Create accounts row and ensure withdraw_account initialized to MIN_WITHDRAWAL
                cur.execute(
                    """
                    INSERT INTO accounts (
                        user_id, deposit_account, income_account, referral_account, withdraw_account
                    ) VALUES (%s,%s,0,0,%s) ON CONFLICT (user_id) DO NOTHING
                    """,
                    (new_user_id, STARTING_DEPOSIT_BALANCE, MIN_WITHDRAWAL),
                )
        except Exception:
            logger.exception("REGISTRATION ERROR")
            flash("Unable to register at this time.", "error")
            return render_template("register.html", invite_code=invite_code)

        # Keep user experience: after registering, redirect to login page
        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html", invite_code=invite_code)


# ---------------------------
# Login / Logout
# ---------------------------
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
            # Upgrade legacy plaintext password to hashed password on first login
            if used_legacy_password:
                execute("UPDATE users SET password_hash=%s, password=NULL WHERE id=%s", (generate_password_hash(password), user["id"]))
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))

        flash("Invalid phone number or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------
# Dashboard
# ---------------------------
@app.route("/dashboard")
def dashboard():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    account = account_for_display(current_account(user["id"]))
    return render_template("dashboard.html", user=user, account=account, plans=PLANS)


# ---------------------------
# Buy/Confirm Plan
# ---------------------------
@app.route("/buy_plan/<int:plan_id>")
def buy_plan(plan_id: int):
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    if plan_id not in PLANS:
        flash("Plan not found.", "error")
        return redirect(url_for("dashboard"))
    plan = PLANS[plan_id]
    account = current_account(user["id"])
    if money(account["deposit_account"]) < plan["investment"]:
        return render_template("insufficient_balance.html", account=account, plan={"investment_amount": plan["investment"]})
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


@app.route("/confirm_buy_plan/<int:plan_id>", methods=["POST"])
def confirm_buy_plan(plan_id: int):
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    if plan_id not in PLANS:
        flash("Plan not found.", "error")
        return redirect(url_for("dashboard"))
    plan = PLANS[plan_id]

    try:
        with db_cursor(commit=True, dict_cursor=True) as cur:
            ensure_account(cur, user["id"], STARTING_DEPOSIT_BALANCE)
            cur.execute("SELECT deposit_account FROM accounts WHERE user_id=%s FOR UPDATE", (user["id"],))
            row = cur.fetchone()
            balance = money(row["deposit_account"] if row else 0)
            if balance < plan["investment"]:
                raise ValueError("Insufficient deposit balance.")
            cur.execute(
                "UPDATE accounts SET deposit_account = deposit_account - %s WHERE user_id=%s AND deposit_account >= %s",
                (plan["investment"], user["id"], plan["investment"]),
            )
            if cur.rowcount != 1:
                raise ValueError("Insufficient deposit balance.")

            started_at = utcnow()
            cur.execute(
                """
                INSERT INTO plans (
                    user_id, plan_id, plan_name, investment_amount,
                    daily_income, duration, started_at, last_claim_at, active
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,NULL,TRUE)
                RETURNING id
                """,
                (user["id"], plan_id, plan["name"], plan["investment"], plan["daily"], plan["duration"], started_at),
            )
            new_plan = cur.fetchone()
            purchase_ref = generate_reference("PLAN")
            new_plan_id = fetch_id(new_plan, "id")
            cur.execute(
                """
                INSERT INTO transactions (
                    user_id, transaction_type, amount, status, reference, description
                ) VALUES (%s,'plan_purchase',%s,'successful',%s,%s)
                """,
                (user["id"], plan["investment"], purchase_ref, f"Plan purchase: {plan['name']} (plan record #{new_plan_id})"),
            )

            # Referral bonuses (levels)
            purchaser_id = user["id"]
            current_ref_code = user.get("referred_by")
            for level_index, pct in enumerate(REFERRAL_PERCENTS, start=1):
                if not current_ref_code:
                    break
                cur.execute("SELECT id, referred_by, referral_code FROM users WHERE referral_code=%s", (current_ref_code,))
                owner_row = cur.fetchone()
                if not owner_row:
                    break
                owner_id = owner_row["id"]
                if owner_id != purchaser_id:
                    bonus_amount = money(plan["investment"] * pct)
                    if bonus_amount > 0:
                        ensure_account(cur, owner_id, Decimal("0.00"))
                        cur.execute("UPDATE accounts SET referral_account = COALESCE(referral_account,0) + %s WHERE user_id=%s", (bonus_amount, owner_id))
                        cur.execute(
                            """
                            INSERT INTO transactions (user_id, transaction_type, amount, status, reference, description)
                            VALUES (%s,'referral_bonus_invest',%s,'successful',%s,%s)
                            """,
                            (owner_id, bonus_amount, generate_reference("RINV"), f"Referral bonus level {level_index} for plan purchase {purchase_ref}"),
                        )
                current_ref_code = owner_row.get("referred_by")
        flash(f"{plan['name']} activated successfully. You can buy additional plans anytime your deposit balance is sufficient.", "success")
    except ValueError as ve:
        logger.warning("Plan purchase validation failed: %s", ve)
        flash(str(ve), "error")
    except Exception:
        logger.exception("PLAN PURCHASE ERROR")
        flash("Unable to activate the plan.", "error")

    return redirect(url_for("my_plan"))


# ============================================================
# Error handlers
# ============================================================
@app.errorhandler(413)
def file_too_large(error):
    flash("Screenshot is too large. Maximum size is 5 MB.", "error")
    return redirect(url_for("deposit"))


@app.errorhandler(404)
def not_found(error):
    return "Page not found", 404


@app.errorhandler(500)
def server_error(error):
    logger.exception("INTERNAL SERVER ERROR")
    return "An internal server error occurred.", 500


# ============================================================
# Application startup
# ============================================================
with app.app_context():
    try:
        if settings.DATABASE_URL:
            init_db()
    except Exception:
        logger.exception("Failed to initialize DB at startup (continuing).")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", str(settings.PORT)))
    debug = os.environ.get("FLASK_DEBUG", str(settings.FLASK_DEBUG)).lower() in ("1", "true", "yes")
    app.run(host="0.0.0.0", port=port, debug=debug)
