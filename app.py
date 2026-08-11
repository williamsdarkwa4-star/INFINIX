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

# ---------- Configuration ----------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")
DATABASE_URL = os.environ.get("DATABASE_URL")  # required
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "Williams")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Williams12")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB screenshots

# Business constants
MIN_DEPOSIT = Decimal("45.00")
MIN_WITHDRAWAL = Decimal("30.00")
STARTING_DEPOSIT_BALANCE = Decimal("5.00")
CLAIM_INTERVAL_HOURS = 24

# Demo plans (kept for templates)
PLANS = {
    1: {"name": "Zenith 1", "investment": Decimal("50.00"), "daily": Decimal("8.00"), "duration": 30},
    2: {"name": "Zenith 2", "investment": Decimal("100.00"), "daily": Decimal("20.00"), "duration": 30},
    3: {"name": "Zenith 3", "investment": Decimal("200.00"), "daily": Decimal("40.00"), "duration": 30},
    4: {"name": "Zenith 4", "investment": Decimal("300.00"), "daily": Decimal("65.00"), "duration": 30},
    5: {"name": "Zenith 5", "investment": Decimal("500.00"), "daily": Decimal("100.00"), "duration": 30},
    6: {"name": "Zenith 6", "investment": Decimal("600.00"), "daily": Decimal("200.00"), "duration": 30},
    7: {"name": "Zenith 7", "investment": Decimal("1000.00"), "daily": Decimal("360.00"), "duration": 30},
}

# ---------- Utilities ----------
def utcnow():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def money(value):
    """Normalize numbers to Decimal(2)."""
    if value is None:
        return Decimal("0.00")
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")


def parse_amount(value):
    if value is None:
        return None
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not amount.is_finite() or amount <= 0:
        return None
    return amount.quantize(Decimal("0.01"))


def generate_referral_code():
    return "ZEN" + uuid.uuid4().hex[:12].upper()


def generate_reference(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


# ---------- Database helpers ----------
def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured.")
    if psycopg2 is None:
        raise RuntimeError("psycopg2 is required but not installed.")
    return psycopg2.connect(DATABASE_URL, sslmode="require")


def query_one(sql, params=()):
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute(sql, params)
            return cur.fetchone()
        finally:
            cur.close()
    finally:
        conn.close()


def query_all(sql, params=()):
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute(sql, params)
            return cur.fetchall()
        finally:
            cur.close()
    finally:
        conn.close()


def execute(sql, params=()):
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute(sql, params)
            conn.commit()
            # when caller expects a result they can run query_one afterwards
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
    finally:
        conn.close()


def ensure_account(cur, user_id, starting_balance=Decimal("0.00")):
    """
    Ensure accounts row exists for user. Uses provided cursor (transactional).
    """
    cur.execute(
        "SELECT user_id FROM accounts WHERE user_id=%s FOR UPDATE",
        (user_id,),
    )
    if cur.fetchone():
        return
    cur.execute(
        """
        INSERT INTO accounts (user_id, deposit_account, income_account, referral_account, withdraw_account)
        VALUES (%s,%s,0,0,0)
        ON CONFLICT (user_id) DO NOTHING
        """,
        (user_id, starting_balance),
    )


# ---------- Database initialization (safe fetchone usage) ----------
def init_db():
    conn = get_conn()
    cur = conn.cursor()  # plain cursor for DDL/inspection queries
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
                referral_code VARCHAR(120),
                referred_by VARCHAR(120),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # accounts
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                deposit_account NUMERIC(14,2) NOT NULL DEFAULT 5.00,
                income_account NUMERIC(14,2) NOT NULL DEFAULT 0,
                referral_account NUMERIC(14,2) NOT NULL DEFAULT 0,
                withdraw_account NUMERIC(14,2) NOT NULL DEFAULT 0
            )
            """
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
            )
            """
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
            )
            """
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
            )
            """
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
            )
            """
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
            )
            """
        )

        # admins
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,
                username VARCHAR(120) UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
            """
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
            )
            """
        )

        # Populate referral_code if missing
        cur.execute("SELECT id FROM users WHERE referral_code IS NULL OR referral_code=''")
        rows = cur.fetchall()
        for r in rows:
            user_id = r[0]
            cur.execute("UPDATE users SET referral_code=%s WHERE id=%s", (generate_referral_code(), user_id))

        # Create accounts for users who lack one
        cur.execute(
            """
            SELECT u.id FROM users u
            LEFT JOIN accounts a ON a.user_id=u.id
            WHERE a.user_id IS NULL
            """
        )
        rows = cur.fetchall()
        for r in rows:
            uid = r[0]
            cur.execute(
                """
                INSERT INTO accounts (user_id, deposit_account, income_account, referral_account, withdraw_account)
                VALUES (%s,%s,0,0,0)
                ON CONFLICT (user_id) DO NOTHING
                """,
                (uid, STARTING_DEPOSIT_BALANCE),
            )

        # Ensure admin exists
        admin_hash = generate_password_hash(ADMIN_PASSWORD)
        cur.execute("SELECT id FROM admins WHERE username=%s", (ADMIN_USERNAME,))
        row = cur.fetchone()
        if row:
            cur.execute("UPDATE admins SET password_hash=%s WHERE username=%s", (admin_hash, ADMIN_USERNAME))
        else:
            cur.execute("INSERT INTO admins (username,password_hash) VALUES (%s,%s)", (ADMIN_USERNAME, admin_hash))

        # Indexes
        indices = [
            "CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone)",
            "CREATE INDEX IF NOT EXISTS idx_users_referral ON users(referral_code)",
            "CREATE INDEX IF NOT EXISTS idx_users_referred_by ON users(referred_by)",
            "CREATE INDEX IF NOT EXISTS idx_plans_user_active ON plans(user_id,active)",
            "CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_deposit_requests_user ON deposit_requests(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_deposit_requests_status ON deposit_requests(status)",
            "CREATE INDEX IF NOT EXISTS idx_withdrawals_user ON withdrawal_requests(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_withdrawals_status ON withdrawal_requests(status)",
            "CREATE INDEX IF NOT EXISTS idx_invites_token ON invites(token)",
        ]
        for s in indices:
            cur.execute(s)

        conn.commit()
    except Exception:
        conn.rollback()
        app.logger.exception("init_db failed")
        raise
    finally:
        cur.close()
        conn.close()


# ---------- Current user & account helpers ----------
def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return query_one("SELECT * FROM users WHERE id=%s", (user_id,))


def current_account(user_id):
    account = query_one("SELECT * FROM accounts WHERE user_id=%s", (user_id,))
    if account:
        return account
    # create if missing
    execute(
        """
        INSERT INTO accounts (user_id, deposit_account, income_account, referral_account, withdraw_account)
        VALUES (%s,%s,0,0,0)
        ON CONFLICT (user_id) DO NOTHING
        """,
        (user_id, STARTING_DEPOSIT_BALANCE),
    )
    return query_one("SELECT * FROM accounts WHERE user_id=%s", (user_id,))


@app.context_processor
def inject_user():
    return {"logged_user": current_user()}


# ---------- Simple auth pages ----------
@app.route("/")
def index():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin_dashboard"))
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    invite_code = (request.args.get("ref", "").strip() or request.form.get("referred_by", "").strip())
    referred_user = None
    if invite_code:
        referred_user = query_one("SELECT id,username,referral_code FROM users WHERE referral_code=%s", (invite_code,))

    if request.method == "POST":
        fullname = request.form.get("fullname", "").strip()
        username = request.form.get("username", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        withdraw_password = request.form.get("withdraw_password", "")

        if not fullname or not username or not phone:
            flash("Please complete all required fields.", "error")
            return render_template("register.html", invite_code=invite_code)

        if len(password) < 6 or len(withdraw_password) < 4:
            flash("Passwords too short.", "error")
            return render_template("register.html", invite_code=invite_code)

        existing = query_one("SELECT id FROM users WHERE username=%s OR phone=%s", (username, phone))
        if existing:
            flash("Username or phone already exists.", "error")
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
                INSERT INTO users (username,fullname,phone,password_hash,withdraw_password_hash,referral_code,referred_by)
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
            user_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO accounts (user_id,deposit_account,income_account,referral_account,withdraw_account)
                VALUES (%s,%s,0,0,0)
                """,
                (user_id, STARTING_DEPOSIT_BALANCE),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            app.logger.exception("Registration error")
            flash("Unable to register. Please try again.", "error")
            return render_template("register.html", invite_code=invite_code)
        finally:
            cur.close()
            conn.close()

        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html", invite_code=invite_code)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        user = query_one("SELECT * FROM users WHERE phone=%s", (phone,))
        valid = False
        if user and user.get("password_hash"):
            try:
                valid = check_password_hash(user["password_hash"], password)
            except Exception:
                valid = False
        if valid:
            session.clear()
            session["user_id"] = user["id"]
            flash("Logged in", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid phone or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- Dashboard ----------
@app.route("/dashboard")
def dashboard():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    account = current_account(user["id"])
    return render_template("dashboard.html", user=user, account=account, plans=PLANS)


# ---------- Deposit flow ----------
@app.route("/deposit", methods=["GET", "POST"])
def deposit():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    if request.method == "POST":
        amount = parse_amount(request.form.get("amount", "0"))
        phone = request.form.get("phone", "").strip()
        payment_number = request.form.get("payment_number", "").strip() or "0257425844"
        screenshot = request.files.get("screenshot")

        if amount is None:
            flash("Please enter a valid deposit amount.", "error")
            return render_template("deposit.html")
        if amount < MIN_DEPOSIT:
            flash(f"Minimum demo deposit is GHS {MIN_DEPOSIT:.2f}.", "error")
            return render_template("deposit.html")
        if not phone:
            flash("Please enter your phone number.", "error")
            return render_template("deposit.html")
        if not screenshot or not screenshot.filename:
            flash("Please upload your payment screenshot.", "error")
            return render_template("deposit.html")

        allowed = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
        filename = screenshot.filename.lower()
        mime_type = next((mime for ext, mime in allowed.items() if filename.endswith(ext)), None)
        if not mime_type:
            flash("Only PNG/JPG/JPEG/WEBP allowed.", "error")
            return render_template("deposit.html")

        data = screenshot.read()
        if not data:
            flash("Uploaded screenshot is empty.", "error")
            return render_template("deposit.html")
        if len(data) > app.config["MAX_CONTENT_LENGTH"]:
            flash("Screenshot too large.", "error")
            return render_template("deposit.html")

        reference = generate_reference("DEP")
        conn = get_conn()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO deposit_requests (user_id,amount,payment_number,screenshot,screenshot_data,screenshot_mime,reference,status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'pending')
                RETURNING id
                """,
                (user["id"], amount, payment_number, screenshot.filename, psycopg2.Binary(data), mime_type, reference),
            )
            dep_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO transactions (user_id,transaction_type,amount,status,reference,description)
                VALUES (%s,'deposit',%s,'pending',%s,%s)
                """,
                (user["id"], amount, reference, f"Demo deposit request #{dep_id}"),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            app.logger.exception("Deposit submission failed")
            flash("Could not submit deposit request.", "error")
            return render_template("deposit.html")
        finally:
            cur.close()
            conn.close()

        flash("Deposit request submitted for admin review.", "success")
        return redirect(url_for("transaction_history"))

    return render_template("deposit.html")


@app.route("/admin/deposit-image/<int:deposit_id>")
def admin_deposit_image(deposit_id):
    if not admin_required():
        return redirect(url_for("admin_login"))
    deposit = query_one("SELECT screenshot_data,screenshot_mime FROM deposit_requests WHERE id=%s", (deposit_id,))
    if not deposit or not deposit.get("screenshot_data"):
        abort(404)
    return send_file(BytesIO(bytes(deposit["screenshot_data"])), mimetype=deposit.get("screenshot_mime") or "image/jpeg", as_attachment=False, download_name=f"deposit_{deposit_id}.jpg")
@app.route("/uploads/deposits/<path:filename>")
def uploaded_deposit_image(filename):
    # Only admins can view uploaded deposit images via this path
    if not admin_required():
        return redirect(url_for("admin_login"))

    deposit = query_one(
        """
        SELECT screenshot_data, screenshot_mime
        FROM deposit_requests
        WHERE screenshot = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (filename,),
    )
    if not deposit or not deposit.get("screenshot_data"):
        abort(404)

    return send_file(
        BytesIO(bytes(deposit["screenshot_data"])),
        mimetype=deposit.get("screenshot_mime") or "image/jpeg",
        as_attachment=False,
        download_name=filename,
    )

# ---------- Buy plan ----------
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
    if money(account["deposit_account"]) < plan["investment"]:
        return render_template("insufficient_balance.html", account=account, plan={"investment_amount": plan["investment"]})
    return render_template("confirm_plan.html", user=user, account=account, plan={"id": plan_id, "plan_name": plan["name"], "investment_amount": plan["investment"], "daily_income": plan["daily"], "duration": plan["duration"]})


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
    cur = conn.cursor()
    try:
        ensure_account(cur, user["id"])
        cur.execute("SELECT deposit_account FROM accounts WHERE user_id=%s FOR UPDATE", (user["id"],))
        row = cur.fetchone()
        balance = money(row[0]) if row else Decimal("0.00")
        if balance < plan["investment"]:
            conn.rollback()
            flash("Insufficient balance.", "error")
            return redirect(url_for("dashboard"))
        cur.execute("UPDATE accounts SET deposit_account=deposit_account-%s WHERE user_id=%s AND deposit_account >= %s", (plan["investment"], user["id"], plan["investment"]))
        if cur.rowcount != 1:
            conn.rollback()
            flash("Insufficient balance.", "error")
            return redirect(url_for("dashboard"))
        started_at = utcnow()
        cur.execute(
            """
            INSERT INTO plans (user_id,plan_id,plan_name,investment_amount,daily_income,duration,started_at,last_claim_at,active)
            VALUES (%s,%s,%s,%s,%s,%s,%s,NULL,TRUE)
            """,
            (user["id"], plan_id, plan["name"], plan["investment"], plan["daily"], plan["duration"], started_at),
        )
        cur.execute("INSERT INTO transactions (user_id,transaction_type,amount,status,reference,description) VALUES (%s,'plan_purchase',%s,'successful',%s,%s)", (user["id"], plan["investment"], generate_reference("PLAN"), f"Demo plan purchase: {plan['name']}"))
        conn.commit()
    except Exception:
        conn.rollback()
        app.logger.exception("Plan activation failed")
        flash("Unable to activate plan.", "error")
        return redirect(url_for("dashboard"))
    finally:
        cur.close()
        conn.close()
    flash("Demo plan activated successfully.", "success")
    return redirect(url_for("my_plan"))


# ---------- My plan ----------
def plan_times(plan_row, now=None):
    """
    plan_row: dict-like from DB with started_at, last_claim_at, duration
    returns (end_time_utc, next_claim_utc)
    """
    now = now or utcnow()
    started = plan_row.get("started_at") or now
    if getattr(started, "tzinfo", None) is None:
        started = started.replace(tzinfo=timezone.utc)
    duration_days = int(plan_row.get("duration") or 0)
    end_time = started + timedelta(days=duration_days)
    last_claim = plan_row.get("last_claim_at")
    if last_claim is None:
        next_claim = started + timedelta(hours=CLAIM_INTERVAL_HOURS)
    else:
        if getattr(last_claim, "tzinfo", None) is None:
            last_claim = last_claim.replace(tzinfo=timezone.utc)
        next_claim = last_claim + timedelta(hours=CLAIM_INTERVAL_HOURS)
    return end_time, next_claim


def deactivate_expired_plans(user_id):
    execute(
        """
        UPDATE plans
        SET active=FALSE
        WHERE user_id=%s
        AND active=TRUE
        AND started_at + (duration * INTERVAL '1 day') <= CURRENT_TIMESTAMP
        """,
        (user_id,),
    )


@app.route("/my_plan", methods=["GET", "POST"])
def my_plan():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    try:
        deactivate_expired_plans(user["id"])
    except Exception:
        app.logger.exception("Error expiring plans")

    if request.method == "POST":
        conn = get_conn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("SELECT * FROM plans WHERE user_id=%s AND active=TRUE ORDER BY id DESC LIMIT 1 FOR UPDATE", (user["id"],))
            plan = cur.fetchone()
            if not plan:
                conn.rollback()
                flash("No active plan to claim.", "error")
                return redirect(url_for("my_plan"))
            now = utcnow()
            end_time, next_claim = plan_times(plan, now)
            if now >= end_time:
                cur.execute("UPDATE plans SET active=FALSE WHERE id=%s", (plan["id"],))
                conn.commit()
                flash("Your plan completed its duration.", "info")
                return redirect(url_for("my_plan"))
            if now < next_claim:
                remaining = int((next_claim - now).total_seconds())
                hours, rem = divmod(remaining, 3600)
                minutes, _ = divmod(rem, 60)
                conn.rollback()
                flash(f"Next income available in {hours}h {minutes}m.", "error")
                return redirect(url_for("my_plan"))
            daily_income = money(plan["daily_income"])
            if daily_income <= 0:
                conn.rollback()
                flash("Plan has no valid daily income.", "error")
                return redirect(url_for("my_plan"))
            ensure_account(cur, user["id"])
            cur.execute("UPDATE accounts SET income_account=COALESCE(income_account,0)+%s, withdraw_account=COALESCE(withdraw_account,0)+%s WHERE user_id=%s", (daily_income, daily_income, user["id"]))
            claim_time = utcnow()
            cur.execute("UPDATE plans SET last_claim_at=%s WHERE id=%s", (claim_time, plan["id"]))
            cur.execute("INSERT INTO transactions (user_id,transaction_type,amount,status,reference,description) VALUES (%s,'income_claim',%s,'successful',%s,%s)", (user["id"], daily_income, generate_reference("INC"), f"Daily demo income claim: {plan['plan_name']}"))
            conn.commit()
            flash(f"GHS {daily_income:.2f} income claimed successfully.", "success")
        except Exception:
            conn.rollback()
            app.logger.exception("Error processing claim")
            flash("Unable to process claim.", "error")
        finally:
            cur.close()
            conn.close()
        return redirect(url_for("my_plan"))

    # GET
    plan = query_one("SELECT * FROM plans WHERE user_id=%s AND active=TRUE ORDER BY id DESC LIMIT 1", (user["id"],))
    can_claim = False
    seconds_remaining = 0
    cycle_seconds_remaining = 0
    next_claim_ts = None
    cycle_ended = False
    next_claim_dt = None
    if plan:
        now = utcnow()
        end_time, next_claim_dt = plan_times(plan, now)
        if now >= end_time:
            execute("UPDATE plans SET active=FALSE WHERE id=%s", (plan["id"],))
            plan = None
            cycle_ended = True
        else:
            cycle_seconds_remaining = max(0, int((end_time - now).total_seconds()))
            seconds_remaining = max(0, int((next_claim_dt - now).total_seconds()))
            if now >= next_claim_dt:
                can_claim = True
                seconds_remaining = 0
            else:
                # pass seconds or timestamp; template expects next_income_at and server_now
                next_claim_ts = int(next_claim_dt.timestamp())

    available_plans = [
        {"id": pid, "plan_name": d["name"], "investment_amount": d["investment"], "daily_income": d["daily"], "duration": d["duration"]}
        for pid, d in PLANS.items()
    ]
    active_plans = query_all("SELECT * FROM plans WHERE user_id=%s AND active=TRUE ORDER BY id DESC", (user["id"],))

    return render_template(
        "my_plan.html",
        user_plan=plan,
        active_plans=active_plans,
        plans=available_plans,
        available_plans=available_plans,
        can_claim=can_claim,
        seconds_remaining=seconds_remaining,
        cycle_seconds_remaining=cycle_seconds_remaining,
        next_claim_timestamp=next_claim_ts or 0,
        next_income_at=next_claim_dt,  # datetime or None
        server_now=utcnow(),
        cycle_ended=cycle_ended,
    )


# ---------- Withdraw & bind ----------
@app.route("/withdraw")
def withdraw():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    account = current_account(user["id"])
    accounts = query_all("SELECT * FROM withdrawal_accounts WHERE user_id=%s ORDER BY id DESC", (user["id"],))
    return render_template("withdraw.html", account=account, accounts=accounts)


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
            flash("Complete account details.", "error")
        else:
            execute("INSERT INTO withdrawal_accounts (user_id,account_name,phone,network) VALUES (%s,%s,%s,%s)", (user["id"], account_name, phone, network))
            flash("Withdrawal account saved.", "success")
    accounts = query_all("SELECT * FROM withdrawal_accounts WHERE user_id=%s ORDER BY id DESC", (user["id"],))
    return render_template("bind_account.html", accounts=accounts)


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
    if not user.get("withdraw_password_hash"):
        flash("Withdrawal password not configured.", "error")
        return redirect(url_for("withdraw"))
    try:
        valid = check_password_hash(user["withdraw_password_hash"], password)
    except Exception:
        valid = False
    if not valid:
        flash("Invalid withdrawal password.", "error")
        return redirect(url_for("withdraw"))
    selected = None
    if account_id:
        selected = query_one("SELECT id FROM withdrawal_accounts WHERE id=%s AND user_id=%s", (account_id, user["id"]))
    else:
        selected = query_one("SELECT id FROM withdrawal_accounts WHERE user_id=%s ORDER BY id DESC LIMIT 1", (user["id"],))
    if not selected:
        flash("Please bind a withdrawal account first.", "error")
        return redirect(url_for("bind_account"))
    conn = get_conn()
    cur = conn.cursor()
    try:
        ensure_account(cur, user["id"])
        cur.execute("SELECT withdraw_account FROM accounts WHERE user_id=%s FOR UPDATE", (user["id"],))
        row = cur.fetchone()
        balance = money(row[0]) if row else Decimal("0.00")
        if balance < amount:
            conn.rollback()
            flash("Insufficient withdrawal balance.", "error")
            return redirect(url_for("withdraw"))
        cur.execute("UPDATE accounts SET withdraw_account=withdraw_account-%s WHERE user_id=%s AND withdraw_account >= %s", (amount, user["id"], amount))
        if cur.rowcount != 1:
            conn.rollback()
            flash("Insufficient withdrawal balance.", "error")
            return redirect(url_for("withdraw"))
        cur.execute("INSERT INTO withdrawal_requests (user_id,amount,account_id,status) VALUES (%s,%s,%s,'pending') RETURNING id", (user["id"], amount, selected["id"]))
        wid = cur.fetchone()[0]
        cur.execute("INSERT INTO transactions (user_id,transaction_type,amount,status,reference,description) VALUES (%s,'withdrawal',%s,'pending',%s,%s)", (user["id"], amount, generate_reference("WDR"), f"Demo withdrawal request #{wid}"))
        conn.commit()
    except Exception:
        conn.rollback()
        app.logger.exception("Withdrawal request failed")
        flash("Unable to submit withdrawal.", "error")
        return redirect(url_for("withdraw"))
    finally:
        cur.close()
        conn.close()
    flash("Withdrawal request submitted for review.", "success")
    return redirect(url_for("transaction_history"))


# ---------- Transactions / team / profile ----------
@app.route("/transaction_history")
def transaction_history():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    transactions = query_all("SELECT * FROM transactions WHERE user_id=%s ORDER BY created_at DESC,id DESC", (user["id"],))
    return render_template("transaction_history.html", transactions=transactions)


@app.route("/team")
def team():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    members = query_all("SELECT id,username,fullname,phone,created_at FROM users WHERE referred_by=%s ORDER BY created_at DESC", (user["referral_code"],))
    account = current_account(user["id"])
    total_team = len(members)
    referral_income = money(account["referral_account"])
    return render_template("team.html", user=user, members=members, total_team=total_team, referral_income=referral_income)


@app.route("/support")
@app.route("/service")
def support():
    return render_template("support.html")


@app.route("/profile")
def profile():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    account = current_account(user["id"])
    return render_template("profile.html", user=user, deposit_balance=account["deposit_account"], withdraw_balance=account["withdraw_account"], income_balance=account["income_account"], referral_balance=account["referral_account"])


# ---------- Password changes ----------
@app.route("/change_login_password", methods=["GET", "POST"])
def change_login_password():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        try:
            valid = check_password_hash(user["password_hash"], current_password)
        except Exception:
            valid = False
        if not valid:
            flash("Current password incorrect.", "error")
            return render_template("change_login_password.html")
        if len(new_password) < 6 or new_password != confirm_password:
            flash("New passwords invalid or do not match.", "error")
            return render_template("change_login_password.html")
        execute("UPDATE users SET password_hash=%s WHERE id=%s", (generate_password_hash(new_password), user["id"]))
        flash("Login password changed.", "success")
        return redirect(url_for("profile"))
    return render_template("change_login_password.html")


@app.route("/change_withdraw_password", methods=["GET", "POST"])
def change_withdraw_password():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    # inside admin_manage_user(...) POST handling

if action == "change_login_password":
    new_password = request.form.get("new_password", "")
    if len(new_password) < 6:
        flash("Login password must contain at least 6 characters.", "error")
    else:
        new_hash = generate_password_hash(new_password)
        # Update both hashed and legacy plaintext columns to keep DB consistent.
        # This keeps older code that still reads 'password' working.
        execute(
            "UPDATE users SET password_hash=%s, password=%s WHERE id=%s",
            (new_hash, new_password, user_id),
        )
        app.logger.info("Admin %s set new login password for user %s", session.get("admin_id"), user_id)
        flash("Login password updated successfully.", "success")
    return redirect(url_for("admin_manage_user", user_id=user_id))

if action == "change_withdraw_password":
    new_password = request.form.get("new_password", "")
    if len(new_password) < 4:
        flash("Withdrawal password must contain at least 4 characters.", "error")
    else:
        new_hash = generate_password_hash(new_password)
        execute(
            "UPDATE users SET withdraw_password_hash=%s, withdraw_password=%s WHERE id=%s",
            (new_hash, new_password, user_id),
        )
        app.logger.info("Admin %s set new withdraw password for user %s", session.get("admin_id"), user_id)
        flash("Withdrawal password updated successfully.", "success")
    return redirect(url_for("admin_manage_user", user_id=user_id))

# ---------- Admin auth helpers ----------
def admin_required():
    return session.get("admin_logged_in") is True


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        admin = query_one("SELECT * FROM admins WHERE username=%s", (username,))
        valid = False
        if admin:
            try:
                valid = check_password_hash(admin["password_hash"], password)
            except Exception:
                valid = False
        if valid:
            session.clear()
            session["admin_logged_in"] = True
            session["admin_id"] = admin["id"]
            flash("Administrator logged in.", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Invalid admin credentials.", "error")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/admin/dashboard")
def admin_dashboard():
    if not admin_required():
        return redirect(url_for("admin_login"))
    total_users = query_one("SELECT COUNT(*) AS count FROM users")["count"]
    pending_deposits = query_one("SELECT COUNT(*) AS count FROM deposit_requests WHERE status='pending'")["count"]
    pending_withdrawals = query_one("SELECT COUNT(*) AS count FROM withdrawal_requests WHERE status='pending'")["count"]
    invites = query_all("SELECT i.*, u.username AS owner_username FROM invites i LEFT JOIN users u ON u.id=i.owner_id ORDER BY i.created_at DESC LIMIT 100")
    return render_template("admin_dashboard.html", total_users=total_users, pending_deposits=pending_deposits, pending_withdrawals=pending_withdrawals, invites=invites)
# Admin user list
@app.route("/admin_users")
@app.route("/admin/users")
def admin_users():
    if not admin_required():
        return redirect(url_for("admin_login"))

    users = query_all(
        """
        SELECT u.*,
               a.deposit_account,
               a.income_account,
               a.referral_account,
               a.withdraw_account
        FROM users u
        LEFT JOIN accounts a ON a.user_id=u.id
        ORDER BY u.id DESC
        """
    )
    return render_template("admin_users.html", users=users)


# Admin manage single user (GET + POST actions)
@app.route("/admin/user/<int:user_id>", methods=["GET", "POST"])
def admin_manage_user(user_id):
    if not admin_required():
        return redirect(url_for("admin_login"))

    user = query_one("SELECT * FROM users WHERE id=%s", (user_id,))
    if not user:
        return "User not found", 404

    if request.method == "POST":
        action = request.form.get("action", "")

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
            amount = parse_amount(request.form.get("amount", "0"))
            if amount is None:
                flash("Amount must be greater than zero.", "error")
                return redirect(url_for("admin_manage_user", user_id=user_id))

            column = balance_actions[action]
            is_add = action.startswith("add_")

            conn = get_conn()
            cur = conn.cursor()
            try:
                ensure_account(cur, user_id, STARTING_DEPOSIT_BALANCE)

                if is_add:
                    cur.execute(
                        f"""
                        UPDATE accounts
                        SET {column}=COALESCE({column},0)+%s
                        WHERE user_id=%s
                        """,
                        (amount, user_id),
                    )
                else:
                    cur.execute(
                        f"""
                        UPDATE accounts
                        SET {column}=GREATEST(0,COALESCE({column},0)-%s)
                        WHERE user_id=%s
                        """,
                        (amount, user_id),
                    )

                cur.execute(
                    """
                    INSERT INTO transactions (
                        user_id,transaction_type,amount,status,
                        reference,description
                    )
                    VALUES (%s,'admin_balance_adjustment',%s,'successful',%s,%s)
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
                app.logger.exception("ADMIN MANAGE USER: balance action failed")
                flash("Unable to update balance.", "error")
            finally:
                cur.close()
                conn.close()

            flash("User balance updated successfully.", "success")
            return redirect(url_for("admin_manage_user", user_id=user_id))

        if action == "change_login_password":
            new_password = request.form.get("new_password", "")
            if len(new_password) < 6:
                flash("Login password must contain at least 6 characters.", "error")
            else:
                execute(
                    "UPDATE users SET password_hash=%s WHERE id=%s",
                    (generate_password_hash(new_password), user_id),
                )
                flash("Login password updated successfully.", "success")
            return redirect(url_for("admin_manage_user", user_id=user_id))

        if action == "change_withdraw_password":
            new_password = request.form.get("new_password", "")
            if len(new_password) < 4:
                flash("Withdrawal password must contain at least 4 characters.", "error")
            else:
                execute(
                    "UPDATE users SET withdraw_password_hash=%s WHERE id=%s",
                    (generate_password_hash(new_password), user_id),
                )
                flash("Withdrawal password updated successfully.", "success")
            return redirect(url_for("admin_manage_user", user_id=user_id))

        if action == "update_account":
            account_id = request.form.get("account_id")
            account_name = request.form.get("account_name", "").strip()
            phone = request.form.get("phone", "").strip()
            network = request.form.get("network", "").strip()

            if not account_id or not account_name or not phone or not network:
                flash("Please complete all withdrawal account details.", "error")
            else:
                execute(
                    """
                    UPDATE withdrawal_accounts
                    SET account_name=%s,phone=%s,network=%s
                    WHERE id=%s AND user_id=%s
                    """,
                    (account_name, phone, network, account_id, user_id),
                )
                flash("Withdrawal account updated successfully.", "success")
            return redirect(url_for("admin_manage_user", user_id=user_id))

        if action == "delete_account":
            execute(
                """
                DELETE FROM withdrawal_accounts
                WHERE id=%s AND user_id=%s
                """,
                (request.form.get("account_id"), user_id),
            )
            flash("Withdrawal account removed.", "success")
            return redirect(url_for("admin_manage_user", user_id=user_id))

        flash("Unknown admin action.", "error")
        return redirect(url_for("admin_manage_user", user_id=user_id))

    account = current_account(user_id)
    withdrawal_accounts = query_all(
        """
        SELECT * FROM withdrawal_accounts
        WHERE user_id=%s ORDER BY id DESC
        """,
        (user_id,),
    )

    return render_template(
        "admin_manage_user.html",
        user=user,
        account=account,
        withdrawal_accounts=withdrawal_accounts,
    )


# Admin bind accounts listing
@app.route("/admin_bind_accounts")
@app.route("/admin/bind_accounts")
def admin_bind_accounts():
    if not admin_required():
        return redirect(url_for("admin_login"))

    accounts = query_all(
        """
        SELECT wa.*,u.username,u.phone AS user_phone
        FROM withdrawal_accounts wa
        JOIN users u ON u.id=wa.user_id
        ORDER BY wa.created_at DESC,wa.id DESC
        """
    )
    return render_template("admin_bind_accounts.html", accounts=accounts)

@app.route("/admin/invites/create", methods=["POST"])
def admin_create_invite():
    if not admin_required():
        return redirect(url_for("admin_login"))
    owner_id = request.form.get("owner_id")
    amount = parse_amount(request.form.get("amount", "0")) or Decimal("0.00")
    token = request.form.get("token") or ("INV-" + uuid.uuid4().hex[:10].upper())
    execute("INSERT INTO invites (token,owner_id,amount,approved) VALUES (%s,%s,%s,FALSE) ON CONFLICT (token) DO NOTHING", (token, owner_id, amount))
    flash("Invite created.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/approve_invite/<token>", methods=["POST", "GET"])
def admin_approve_invite(token):
    if not admin_required():
        return redirect(url_for("admin_login"))
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM invites WHERE token=%s FOR UPDATE", (token,))
        invite = cur.fetchone()
        if not invite:
            flash("Invite not found.", "error")
            return redirect(url_for("admin_dashboard"))
        if invite.get("approved"):
            flash("Invite already approved.", "info")
            return redirect(url_for("admin_dashboard"))
        owner_id = invite["owner_id"]
        amount = money(invite.get("amount") or 0)
        ensure_account(cur, owner_id, STARTING_DEPOSIT_BALANCE)
        cur.execute("UPDATE accounts SET referral_account=COALESCE(referral_account,0)+%s WHERE user_id=%s", (amount, owner_id))
        cur.execute("UPDATE invites SET approved=TRUE WHERE id=%s", (invite["id"],))
        cur.execute("INSERT INTO transactions (user_id,transaction_type,amount,status,reference,description) VALUES (%s,'invite_credit',%s,'successful',%s,%s)", (owner_id, amount, generate_reference("INV"), f"Admin approved invite {token}"))
        conn.commit()
        flash(f"Invite approved and GHS {amount:.2f} credited to user id {owner_id}.", "success")
    except Exception:
        conn.rollback()
        app.logger.exception("Failed to approve invite")
        flash("Unable to approve invite.", "error")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("admin_dashboard"))


# ---------- Admin deposit/withdrawal review ----------
@app.route("/admin/deposits")
def admin_deposits():
    if not admin_required():
        return redirect(url_for("admin_login"))
    deposits = query_all("SELECT d.*, u.username,u.fullname,u.phone FROM deposit_requests d JOIN users u ON u.id=d.user_id ORDER BY d.created_at DESC")
    return render_template("admin_deposit.html", deposits=deposits)


@app.route("/admin/deposit/<int:deposit_id>/<action>", methods=["POST"])
def admin_deposit_action(deposit_id, action):
    if not admin_required():
        return redirect(url_for("admin_login"))
    if action not in {"approve", "reject"}:
        flash("Invalid action.", "error")
        return redirect(url_for("admin_deposits"))
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM deposit_requests WHERE id=%s FOR UPDATE", (deposit_id,))
        dep = cur.fetchone()
        if not dep:
            flash("Deposit not found.", "error")
            return redirect(url_for("admin_deposits"))
        if dep["status"] != "pending":
            flash("Already reviewed.", "info")
            return redirect(url_for("admin_deposits"))
        uid = dep["user_id"]
        amount = money(dep["amount"])
        ref = dep.get("reference")
        if action == "approve":
            ensure_account(cur, uid, Decimal("0.00"))
            cur.execute("UPDATE accounts SET deposit_account=COALESCE(deposit_account,0)+%s WHERE user_id=%s", (amount, uid))
            cur.execute("UPDATE deposit_requests SET status='approved' WHERE id=%s", (deposit_id,))
            cur.execute("UPDATE transactions SET status='successful' WHERE user_id=%s AND transaction_type='deposit' AND reference=%s AND status='pending'", (uid, ref))
            msg = f"Approved deposit GHS {amount:.2f}"
        else:
            cur.execute("UPDATE deposit_requests SET status='rejected' WHERE id=%s", (deposit_id,))
            cur.execute("UPDATE transactions SET status='failed' WHERE user_id=%s AND transaction_type='deposit' AND reference=%s AND status='pending'", (uid, ref))
            msg = f"Rejected deposit GHS {amount:.2f}"
        conn.commit()
        flash(msg, "success")
    except Exception:
        conn.rollback()
        app.logger.exception("Admin deposit action failed")
        flash("Unable to process deposit action.", "error")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("admin_deposits"))


@app.route("/admin/withdrawals")
def admin_withdrawals():
    if not admin_required():
        return redirect(url_for("admin_login"))
    withdrawals = query_all("SELECT w.*, u.username,u.fullname,u.phone, wa.account_name, wa.phone AS account_phone, wa.network FROM withdrawal_requests w JOIN users u ON u.id=w.user_id LEFT JOIN withdrawal_accounts wa ON wa.id=w.account_id ORDER BY w.created_at DESC")
    return render_template("admin_withdraw.html", withdrawals=withdrawals)


@app.route("/admin/withdraw/<int:withdrawal_id>/<action>", methods=["POST"])
def admin_withdraw_action(withdrawal_id, action):
    if not admin_required():
        return redirect(url_for("admin_login"))
    if action not in {"approve", "reject"}:
        flash("Invalid action.", "error")
        return redirect(url_for("admin_withdrawals"))
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM withdrawal_requests WHERE id=%s FOR UPDATE", (withdrawal_id,))
        w = cur.fetchone()
        if not w:
            flash("Withdrawal not found.", "error")
            return redirect(url_for("admin_withdrawals"))
        if w["status"] != "pending":
            flash("Already reviewed.", "info")
            return redirect(url_for("admin_withdrawals"))
        uid = w["user_id"]
        amount = money(w["amount"])
        if action == "approve":
            cur.execute("UPDATE withdrawal_requests SET status='approved' WHERE id=%s", (withdrawal_id,))
            cur.execute("UPDATE transactions SET status='successful' WHERE id=(SELECT id FROM transactions WHERE user_id=%s AND transaction_type='withdrawal' AND amount=%s AND status='pending' ORDER BY created_at DESC LIMIT 1)", (uid, amount))
            msg = "Withdrawal approved."
        else:
            ensure_account(cur, uid, Decimal("0.00"))
            cur.execute("UPDATE accounts SET withdraw_account=COALESCE(withdraw_account,0)+%s WHERE user_id=%s", (amount, uid))
            cur.execute("UPDATE withdrawal_requests SET status='rejected' WHERE id=%s", (withdrawal_id,))
            cur.execute("UPDATE transactions SET status='failed' WHERE id=(SELECT id FROM transactions WHERE user_id=%s AND transaction_type='withdrawal' AND amount=%s AND status='pending' ORDER BY created_at DESC LIMIT 1)", (uid, amount))
            msg = "Withdrawal rejected; balance restored."
        conn.commit()
        flash(msg, "success")
    except Exception:
        conn.rollback()
        app.logger.exception("Admin withdrawal action failed")
        flash("Unable to process withdrawal action.", "error")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("admin_withdrawals"))


# ---------- Error handlers ----------
@app.errorhandler(413)
def too_large(e):
    flash("Uploaded file too large (max 5MB).", "error")
    return redirect(url_for("deposit"))


@app.errorhandler(404)
def not_found(e):
    return "Not found", 404


@app.errorhandler(500)
def internal_error(e):
    app.logger.exception("Internal server error")
    return "Internal server error", 500


# ---------- Startup ----------
with app.app_context():
    init_db()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "False").lower() in ("1", "true", "yes")
    app.run(host="0.0.0.0", port=port, debug=debug)
