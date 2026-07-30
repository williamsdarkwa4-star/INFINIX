import os
import random
import string

import psycopg2
from psycopg2.extras import RealDictCursor

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from werkzeug.utils import secure_filename


# =====================================
# FLASK CONFIGURATION
# =====================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "tesla-investment-secret-key"
)

PLANS_CATALOG = [
    {
        "id": 1,
        "name": "TESLA VIP 1",
        "price": 100,
        "daily": 20,
        "duration": 100,
        "image": "https://images.unsplash.com/photo-1560958089-b8a1929cea89"
    },
    {
        "id": 2,
        "name": "TESLA VIP 2",
        "price": 300,
        "daily": 40,
        "duration": 100,
        "image": "https://images.unsplash.com/photo-1617788138017-80ad40651399"
    },
    {
        "id": 3,
        "name": "TESLA VIP 3",
        "price": 500,
        "daily": 60,
        "duration": 100,
        "image": "https://images.unsplash.com/photo-1542362567-b07e54358753"
    },
    {
        "id": 4,
        "name": "TESLA VIP 4",
        "price": 700,
        "daily": 80,
        "duration": 100,
        "image": "https://images.unsplash.com/photo-1606664515524-ed2f786a0bd6"
    },
    {
        "id": 5,
        "name": "TESLA VIP 5",
        "price": 850,
        "daily": 166,
        "duration": 100,
        "image": "https://images.unsplash.com/photo-1492144534655-ae79c964c9d7"
    },
    {
        "id": 6,
        "name": "TESLA VIP 6",
        "price": 1500,
        "daily": 280,
        "duration": 100,
        "image": "https://images.unsplash.com/photo-1560958089-b8a1929cea89"
    }
]
# =====================================
# UPLOAD SETTINGS
# =====================================

UPLOAD_FOLDER = "static/uploads"

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


ALLOWED_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg"
}


# =====================================
# DATABASE CONNECTION
# =====================================
DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db():

    if not DATABASE_URL:
        raise Exception(
            "DATABASE_URL is missing. Add Render PostgreSQL URL in Environment Variables."
        )

    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor
    )



# =====================================
# HELPER FUNCTIONS
# =====================================

def allowed_file(filename):

    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


def create_referral_code():

    while True:

        code = "TESLA" + "".join(
            random.choices(
                string.digits,
                k=6
            )
        )

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id
            FROM users
            WHERE referral_code=%s
            """,
            (code,)
        )

        exists = cur.fetchone()

        conn.close()

        if not exists:
            return code


# =====================================
# TESLA VIP PLANS
# =====================================



# =====================================
# HOME
# =====================================

@app.route("/")
def home():
    return redirect(url_for("login"))


# =====================================
# REGISTER
# =====================================

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        invite_code = request.args.get("invite_code", "")
        return render_template("register.html", invite_code=invite_code)

    # existing POST registration logic...

    if request.method == "POST":

        phone = request.form["phone"].strip()

        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        withdraw_password = request.form["withdraw_password"]
        confirm_withdraw_password = request.form["confirm_withdraw_password"]

        invite_code = request.form.get("invite_code", "").strip()

        if password != confirm_password:
            flash("Login passwords do not match.")
            return redirect(url_for("register"))

        if withdraw_password != confirm_withdraw_password:
            flash("Withdrawal passwords do not match.")
            return redirect(url_for("register"))

        conn = get_db()
        cur = conn.cursor()

        # Check if phone already exists
        cur.execute(
            """
            SELECT id
            FROM users
            WHERE phone=%s
            """,
            (phone,)
        )

        if cur.fetchone():
            conn.close()
            flash("Phone number already registered.")
            return redirect(url_for("register"))

        # Validate referral code if entered
        invited_by = None

        if invite_code:

            cur.execute(
                """
                SELECT referral_code
                FROM users
                WHERE referral_code=%s
                """,
                (invite_code,)
            )

            referrer = cur.fetchone()

            if not referrer:
                conn.close()
                flash("Invalid invite code.")
                return redirect(url_for("register"))

            invited_by = invite_code

        hashed_password = generate_password_hash(password)
        hashed_withdraw_password = generate_password_hash(withdraw_password)

        referral_code = create_referral_code()

        cur.execute(
            """
            INSERT INTO users
            (
                phone,
                password,
                withdraw_password,
                balance,
                income,
                referral_code,
                invited_by
            )

            VALUES
            (%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                phone,
                hashed_password,
                hashed_withdraw_password,
                10,
                0,
                referral_code,
                invited_by
            )
        )

        conn.commit()
        conn.close()

        flash("Registration successful. GHS 10 welcome bonus added.")

        return redirect(url_for("login"))

    return render_template("register.html")


# =====================================
# LOGIN
# =====================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        phone = request.form["phone"].strip()
        password = request.form["password"]

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT *
            FROM users
            WHERE phone=%s
            """,
            (phone,)
        )

        user = cur.fetchone()

        conn.close()

        if not user:
            flash("Phone number not found.")
            return redirect(url_for("login"))

        if not check_password_hash(
            user["password"],
            password
        ):
            flash("Incorrect password.")
            return redirect(url_for("login"))

        session.clear()
        session["user_id"] = user["id"]

        return redirect(url_for("dashboard"))

    return render_template("login.html")


# =====================================
# LOGOUT
# =====================================

@app.route("/logout")
def logout():

    session.clear()

    flash("You have logged out successfully.")

    return redirect(url_for("login"))
# =====================================
# DASHBOARD
# =====================================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))


    conn = get_db()
    cur = conn.cursor()


    cur.execute(
        """
        SELECT *
        FROM users
        WHERE id=%s
        """,
        (session["user_id"],)
    )


    user = cur.fetchone()


    conn.close()


    if not user:
        session.clear()
        return redirect(url_for("login"))


    return render_template(
        "dashboard.html",
        user=user,
        plans=PLANS_CATALOG
    )



# =====================================
# PROFILE
# =====================================

@app.route("/profile")
def profile():

    if "user_id" not in session:
        return redirect(url_for("login"))


    conn = get_db()
    cur = conn.cursor()


    cur.execute(
        """
        SELECT
            phone,
            balance,
            income,
            referral_code,
            created_at
        FROM users
        WHERE id=%s
        """,
        (session["user_id"],)
    )


    user = cur.fetchone()


    conn.close()


    return render_template(
        "profile.html",
        user=user
    )



# =====================================
# TEAM / REFERRAL
# =====================================

@app.route("/team")
def team():

    if "user_id" not in session:
        return redirect(url_for("login"))


    conn = get_db()
    cur = conn.cursor()


    cur.execute(
        """
        SELECT referral_code
        FROM users
        WHERE id=%s
        """,
        (session["user_id"],)
    )


    user = cur.fetchone()


    cur.execute(
        """
        SELECT
            phone,
            created_at
        FROM users
        WHERE invited_by=%s
        ORDER BY id DESC
        """,
        (user["referral_code"],)
    )


    members = cur.fetchall()


    conn.close()


    return render_template(
        "team.html",
        referral_code=user["referral_code"],
        members=members,
        total_team=len(members)
    )



# =====================================
# SERVICE PAGE
# =====================================

@app.route("/service")
def service():

    return render_template(
        "service.html"
    )
# =====================================
# DEPOSIT
# =====================================

@app.route("/deposit", methods=["GET", "POST"])
def deposit():

    if "user_id" not in session:
        return redirect(url_for("login"))


    if request.method == "POST":

        try:
            amount = float(request.form["amount"])
        except:

            flash("Enter a valid amount.")
            return redirect(url_for("deposit"))


        if amount < 90:
            flash("Minimum deposit is GHS 90.")
            return redirect(url_for("deposit"))


        screenshot = request.files.get("screenshot")

        filename = None


        if screenshot and allowed_file(
            screenshot.filename
        ):

            filename = secure_filename(
                screenshot.filename
            )

            screenshot.save(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    filename
                )
            )


        conn = get_db()
        cur = conn.cursor()


        cur.execute(
            """
            INSERT INTO deposits
            (
                user_id,
                amount,
                screenshot,
                status
            )

            VALUES
            (%s,%s,%s,%s)
            """,
            (
                session["user_id"],
                amount,
                filename,
                "Processing"
            )
        )


        conn.commit()
        conn.close()


        flash(
            "Deposit submitted. Waiting for approval."
        )

        return redirect(
            url_for("deposit")
        )


    return render_template(
        "deposit.html"
    )

@app.route("/history")
def history():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    user_id = session["user_id"]

    cur.execute("""
        SELECT *
        FROM deposits
        WHERE user_id=%s
        ORDER BY id DESC
    """,(user_id,))

    deposits = cur.fetchall()


    cur.execute("""
        SELECT *
        FROM withdrawals
        WHERE user_id=%s
        ORDER BY id DESC
    """,(user_id,))

    withdrawals = cur.fetchall()


    cur.execute("""
        SELECT *
        FROM user_plans
        WHERE user_id=%s
        ORDER BY id DESC
    """,(user_id,))

    plans = cur.fetchall()


    cur.close()
    conn.close()


    return render_template(
        "history.html",
        deposits=deposits,
        withdrawals=withdrawals,
        plans=plans
    )

# =====================================
# DEPOSIT HISTORY
# =====================================

@app.route("/deposit_history")
def deposit_history():

    if "user_id" not in session:
        return redirect(url_for("login"))


    conn = get_db()
    cur = conn.cursor()


    cur.execute(
        """
        SELECT *
        FROM deposits
        WHERE user_id=%s
        ORDER BY id DESC
        """,
        (session["user_id"],)
    )


    deposits = cur.fetchall()


    conn.close()


    return render_template(
        "deposit_history.html",
        deposits=deposits
    )



# =====================================
# ADMIN DEPOSITS
# =====================================

@app.route("/admin/deposits")
def admin_deposits():

    if "admin_id" not in session:
        return redirect("/admin/login")


    conn = get_db()
    cur = conn.cursor()


    cur.execute(
        """
        SELECT
            deposits.*,
            users.phone

        FROM deposits

        JOIN users
        ON deposits.user_id = users.id

        WHERE deposits.status='Processing'

        ORDER BY deposits.id DESC
        """
    )


    deposits = cur.fetchall()


    conn.close()


    return render_template(
        "admin_deposits.html",
        deposits=deposits
    )



# =====================================
# ADMIN APPROVE DEPOSIT
# =====================================

@app.route("/admin/deposit/approve/<int:id>")
def approve_deposit(id):

    if "admin_id" not in session:
        return redirect("/admin/login")


    conn = get_db()
    cur = conn.cursor()


    cur.execute(
        """
        SELECT *
        FROM deposits
        WHERE id=%s
        """,
        (id,)
    )


    deposit = cur.fetchone()


    if not deposit:

        conn.close()

        flash("Deposit not found.")

        return redirect(
            "/admin/deposits"
        )


    if deposit["status"] != "Processing":

        conn.close()

        flash(
            "Deposit already processed."
        )

        return redirect(
            "/admin/deposits"
        )



    # Approve deposit

    cur.execute(
        """
        UPDATE deposits

        SET status='Approved'

        WHERE id=%s
        """,
        (id,)
    )


    # Add balance to user

    cur.execute(
        """
        UPDATE users

        SET balance = balance + %s

        WHERE id=%s
        """,
        (
            deposit["amount"],
            deposit["user_id"]
        )
    )


    conn.commit()
    conn.close()


    flash(
        "Deposit approved and balance updated."
    )


    return redirect(
        "/admin/deposits"
    )



# =====================================
# ADMIN REJECT DEPOSIT
# =====================================

@app.route("/admin/deposit/reject/<int:id>")
def reject_deposit(id):

    if "admin_id" not in session:
        return redirect("/admin/login")


    conn = get_db()
    cur = conn.cursor()


    cur.execute(
        """
        UPDATE deposits

        SET status='Rejected'

        WHERE id=%s

        AND status='Processing'
        """,
        (id,)
    )


    conn.commit()
    conn.close()


    flash(
        "Deposit rejected."
    )


    return redirect(
        "/admin/deposits"
    )
# =====================================
# BUY TESLA VIP PLAN
# =====================================

@app.route("/buy_plan/<int:plan_id>")
def buy_plan(plan_id):

    if "user_id" not in session:
        return redirect(url_for("login"))


    # Find selected plan

    selected_plan = None

    for plan in PLANS:

        if plan["id"] == plan_id:
            selected_plan = plan
            break



    if not selected_plan:

        flash("Plan not found.")
        return redirect(url_for("dashboard"))



    conn = get_db()
    cur = conn.cursor()



    # Get user balance

    cur.execute(
        """
        SELECT balance
        FROM users
        WHERE id=%s
        """,
        (session["user_id"],)
    )


    user = cur.fetchone()



    if not user:

        conn.close()

        return redirect(url_for("login"))



    if float(user["balance"]) < selected_plan["investment"]:

        conn.close()

        flash(
            "Insufficient balance. Please deposit first."
        )

        return redirect(
            url_for("deposit")
        )



    # Deduct investment amount

    cur.execute(
        """
        UPDATE users

        SET balance = balance - %s

        WHERE id=%s
        """,
        (
            selected_plan["investment"],
            session["user_id"]
        )
    )



    # Create active plan

    cur.execute(
        """
        INSERT INTO user_plans
        (
            user_id,
            plan_name,
            investment,
            daily_income,
            duration,
            status
        )

        VALUES
        (%s,%s,%s,%s,%s,%s)
        """,
        (
            session["user_id"],
            selected_plan["name"],
            selected_plan["investment"],
            selected_plan["daily"],
            selected_plan["duration"],
            "Active"
        )
    )



    # Referral commission

    cur.execute(
        """
        SELECT invited_by
        FROM users
        WHERE id=%s
        """,
        (session["user_id"],)
    )


    buyer = cur.fetchone()



    if buyer and buyer["invited_by"]:


        cur.execute(
            """
            SELECT id
            FROM users
            WHERE referral_code=%s
            """,
            (buyer["invited_by"],)
        )


        referrer = cur.fetchone()



        if referrer:

            commission = (
                selected_plan["investment"]
                * 0.20
            )


            cur.execute(
                """
                UPDATE users
                 SET
                balance = balance + %s,
                income = income + %s
                WHERE id=%s
                """,
                (
                  commission,
                  commission,
                  referrer["id"]
                )
            )



    conn.commit()
    conn.close()



    flash(
        "Tesla VIP plan activated successfully."
    )


    return redirect(
        url_for("my_plan")
    )

@app.route("/admin/delete_plan/<int:plan_id>")
def admin_delete_plan(plan_id):

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        DELETE FROM user_plans
        WHERE id=%s
        """,
        (plan_id,)
    )

    conn.commit()

    cur.close()
    conn.close()

    flash("Plan deleted successfully", "success")

    return redirect(url_for("admin_plans"))

# =====================================
# MY ACTIVE PLANS
# =====================================

@app.route("/my_plan")
def my_plan():

    if "user_id" not in session:
        return redirect(url_for("login"))


    conn = get_db()
    cur = conn.cursor()



    cur.execute(
        """
        SELECT *

        FROM user_plans

        WHERE user_id=%s

        ORDER BY id DESC
        """,
        (session["user_id"],)
    )


    plans = cur.fetchall()


    conn.close()



    return render_template(
        "my_plan.html",
        plans=plans
    )
# =====================================
# CLAIM DAILY INCOME
# =====================================

from datetime import datetime, timedelta

@app.route("/claim_income/<int:plan_id>")
def claim_income(plan_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM user_plans
        WHERE id=%s
        AND user_id=%s
    """, (plan_id, session["user_id"]))

    plan = cur.fetchone()

    if not plan:
        conn.close()
        flash("Plan not found.")
        return redirect(url_for("my_plan"))

    if plan["status"] != "Active":
        conn.close()
        flash("This plan has already completed.")
        return redirect(url_for("my_plan"))

    now = datetime.now()

    # First claim: 24 hours after purchase
    if plan["last_claim"] is None:
        next_claim = plan["created_at"] + timedelta(hours=24)
    else:
        next_claim = plan["last_claim"] + timedelta(hours=24)

    if now < next_claim:
        remaining = next_claim - now

        hours = remaining.days * 24 + remaining.seconds // 3600
        minutes = (remaining.seconds % 3600) // 60

        conn.close()

        flash(
            f"Next claim available in {hours}h {minutes}m."
        )

        return redirect(url_for("my_plan"))

    if plan["days_completed"] >= plan["duration"]:

        cur.execute("""
            UPDATE user_plans
            SET status='Completed'
            WHERE id=%s
        """, (plan_id,))

        conn.commit()
        conn.close()

        flash("This investment plan has completed.")

        return redirect(url_for("my_plan"))

    income = float(plan["daily_income"])

    cur.execute("""
        UPDATE users
        SET
            balance = balance + %s,
            income = income + %s
        WHERE id=%s
    """, (
        income,
        income,
        session["user_id"]
    ))

    new_days = plan["days_completed"] + 1

    status = "Completed" if new_days >= plan["duration"] else "Active"

    cur.execute("""
        UPDATE user_plans
        SET
            total_earned = total_earned + %s,
            days_completed = days_completed + 1,
            last_claim = %s,
            status = %s
        WHERE id=%s
    """, (
        income,
        now,
        status,
        plan_id
    ))

    conn.commit()
    conn.close()

    flash(f"GHS {income:.2f} credited successfully.")

    return redirect(url_for("my_plan"))



@app.route("/change_password", methods=["GET","POST"])
def change_password():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        new_password = request.form.get("password")

        hashed = generate_password_hash(new_password)

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            "UPDATE users SET password=%s WHERE id=%s",
            (hashed, session["user_id"])
        )

        conn.commit()
        cur.close()
        conn.close()

        flash("Password changed successfully")
        return redirect(url_for("profile"))

    return render_template("change_password.html")

# =====================================
# SAVE WITHDRAWAL ACCOUNT
# =====================================

@app.route("/save_account", methods=["POST"])
def save_account():

    if "user_id" not in session:
        return redirect(url_for("login"))


    account_name = request.form["account_name"]

    network = request.form["network"]

    account_number = request.form["account_number"]



    conn = get_db()
    cur = conn.cursor()


    cur.execute(
        """
        UPDATE users

        SET
            account_name=%s,
            network=%s,
            account_number=%s

        WHERE id=%s

        """,
        (
            account_name,
            network,
            account_number,
            session["user_id"]
        )
    )


    conn.commit()
    conn.close()


    flash(
        "Withdrawal account saved."
    )


    return redirect(
        url_for("withdraw")
    )

@app.route("/admin/edit_balance/<int:user_id>", methods=["GET", "POST"])
def edit_balance(user_id):

    if "admin_id" not in session:
        return redirect("/admin/login")

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":

        amount = float(request.form["amount"])
        action = request.form["action"]

        if action == "add":
            cur.execute("""
                UPDATE users
                SET balance = balance + %s
                WHERE id=%s
            """, (amount, user_id))

            flash("Balance added successfully.")

        elif action == "subtract":
            cur.execute("""
                UPDATE users
                SET balance = balance - %s
                WHERE id=%s
            """, (amount, user_id))

            flash("Balance deducted successfully.")

        conn.commit()
        conn.close()

        return redirect(url_for("admin_users"))

    cur.execute("""
        SELECT phone, balance
        FROM users
        WHERE id=%s
    """, (user_id,))

    user = cur.fetchone()

    conn.close()

    return render_template(
        "edit_balance.html",
        user=user,
        user_id=user_id
    )

# =====================================
# WITHDRAW
# =====================================

@app.route("/withdraw", methods=["GET","POST"])
def withdraw():

    if "user_id" not in session:
        return redirect(url_for("login"))



    conn = get_db()
    cur = conn.cursor()



    cur.execute(
        """
        SELECT *

        FROM users

        WHERE id=%s

        """,
        (session["user_id"],)
    )


    user = cur.fetchone()



    if request.method == "POST":


        amount = float(
            request.form["amount"]
        )


        withdraw_password = request.form[
            "withdraw_password"
        ]



        if amount < 30:

            conn.close()

            flash(
                "Minimum withdrawal is GHS 30."
            )

            return redirect(
                url_for("withdraw")
            )



        if not check_password_hash(
            user["withdraw_password"],
            withdraw_password
        ):

            conn.close()

            flash(
                "Incorrect withdrawal password."
            )

            return redirect(
                url_for("withdraw")
            )



        if float(user["balance"]) < amount:

            conn.close()

            flash(
                "Insufficient balance."
            )

            return redirect(
                url_for("withdraw")
            )



        if not user["account_number"]:

            conn.close()

            flash(
                "Please add your Mobile Money account first."
            )

            return redirect(
                url_for("withdraw")
            )



        fee = round(
            amount * 0.18,
            2
        )


        receive_amount = round(
            amount - fee,
            2
        )



        # Remove balance temporarily

        cur.execute(
            """
            UPDATE users

            SET balance = balance - %s

            WHERE id=%s

            """,
            (
                amount,
                session["user_id"]
            )
        )



        cur.execute(
            """
            INSERT INTO withdrawals
            (
                user_id,
                amount,
                fee,
                receive_amount,
                status
            )

            VALUES
            (%s,%s,%s,%s,%s)

            """,
            (
                session["user_id"],
                amount,
                fee,
                receive_amount,
                "Processing"
            )
        )


        conn.commit()
        conn.close()



        flash(
            "Withdrawal request submitted."
        )


        return redirect(
            url_for("withdraw")
        )



    conn.close()



    return render_template(
        "withdraw.html",
        user=user
    )



# =====================================
# ADMIN WITHDRAWALS
# =====================================

@app.route("/admin/withdrawals")
def admin_withdrawals():

    if "admin_id" not in session:
        return redirect("/admin/login")


    conn = get_db()
    cur = conn.cursor()



    cur.execute(
        """
        SELECT

            withdrawals.*,

            users.phone,

            users.network,

            users.account_number


        FROM withdrawals


        JOIN users

        ON withdrawals.user_id = users.id


        WHERE withdrawals.status='Processing'


        ORDER BY withdrawals.id DESC

        """
    )


    withdrawals = cur.fetchall()


    conn.close()



    return render_template(
        "admin_withdrawals.html",
        withdrawals=withdrawals
    )

@app.route("/admin/withdraw/approve/<int:id>")
def approve_withdraw(id):

    if "admin_id" not in session:
        return redirect("/admin/login")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM withdrawals
        WHERE id=%s
    """, (id,))

    withdrawal = cur.fetchone()

    if not withdrawal:
        conn.close()
        flash("Withdrawal not found.")
        return redirect("/admin/withdrawals")

    if withdrawal["status"] != "Processing":
        conn.close()
        flash("Withdrawal already processed.")
        return redirect("/admin/withdrawals")

    cur.execute("""
        UPDATE withdrawals
        SET status='Approved'
        WHERE id=%s
    """, (id,))

    conn.commit()
    conn.close()

    flash("Withdrawal approved successfully.")

    return redirect("/admin/withdrawals")

# =====================================
# ADMIN REJECT WITHDRAWAL
# =====================================

@app.route('/admin/withdraw/reject/<int:id>')
def reject_withdraw(id):

    if "admin_id" not in session:
        return redirect('/admin/login')


    conn = get_db()
    cur = conn.cursor()


    cur.execute("""
        SELECT user_id, amount, status
        FROM withdrawals
        WHERE id=%s
    """, (id,))


    withdrawal = cur.fetchone()


    if not withdrawal:
        conn.close()
        flash("Withdrawal not found.")
        return redirect('/admin/withdrawals')


    if withdrawal["status"] == "Processing":

        # Refund user balance
        cur.execute("""
            UPDATE users
            SET balance = balance + %s
            WHERE id=%s
        """,
        (
            withdrawal["amount"],
            withdrawal["user_id"]
        ))


        # Change withdrawal status
        cur.execute("""
            UPDATE withdrawals
            SET status='Rejected'
            WHERE id=%s
        """,
        (id,))


        conn.commit()

        flash("Withdrawal rejected and refunded successfully.")

    else:

        flash("This withdrawal was already processed.")


    conn.close()

    return redirect('/admin/withdrawals')





@app.route("/create_admin")
def create_admin():

    conn = get_db()
    cur = conn.cursor()

    from werkzeug.security import generate_password_hash

    username = "Williams12"
    password = "Williams12"

    hashed = generate_password_hash(password)

    cur.execute(
        """
        SELECT id FROM admins
        WHERE username=%s
        """,
        (username,)
    )

    existing = cur.fetchone()

    if not existing:

        cur.execute(
            """
            INSERT INTO admins
            (username, password)
            VALUES (%s,%s)
            """,
            (
                username,
                hashed
            )
        )

        conn.commit()

        message = "Admin created successfully"

    else:
        message = "Admin already exists"


    conn.close()

    return message
# =====================================
# ADMIN LOGIN
# =====================================

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT *
            FROM admins
            WHERE username=%s
            """,
            (username,)
        )

        admin = cur.fetchone()

        conn.close()


        if admin and check_password_hash(
            admin["password"],
            password
        ):

            session["admin_id"] = admin["id"]

            return redirect(
                url_for("admin_dashboard")
            )


        flash("Invalid admin login")


    return render_template("admin_login.html")


# =====================================
# ADMIN LOGOUT
# =====================================

@app.route("/admin/logout")
def admin_logout():

    session.pop(
        "admin_id",
        None
    )

    return redirect(
        "/admin/login"
    )

def get_db_connection():
    return psycopg2.connect(
        os.environ.get("DATABASE_URL")
    )


def fix_database():

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        ALTER TABLE user_plans
        ADD COLUMN IF NOT EXISTS days_completed INTEGER DEFAULT 0
    """)

    cur.execute("""
        ALTER TABLE user_plans
        ADD COLUMN IF NOT EXISTS total_earned NUMERIC(12,2) DEFAULT 0
    """)

    cur.execute("""
        ALTER TABLE user_plans
        ADD COLUMN IF NOT EXISTS last_claim TIMESTAMP
    """)

    conn.commit()
    cur.close()
    conn.close()


fix_database()

# =====================================
# ADMIN DASHBOARD
# =====================================

@app.route("/admin/dashboard")
def admin_dashboard():

    if "admin_id" not in session:
        return redirect(
            "/admin/login"
        )


    conn = get_db()
    cur = conn.cursor()



    cur.execute(
        "SELECT COUNT(*) FROM users"
    )

    total_users = cur.fetchone()["count"]



    cur.execute(
        """
        SELECT COALESCE(SUM(amount),0)

        FROM deposits

        WHERE status='Approved'
        """
    )

    total_deposits = cur.fetchone()["coalesce"]



    cur.execute(
        """
        SELECT COUNT(*)

        FROM withdrawals

        WHERE status='Processing'
        """
    )

    pending_withdrawals = cur.fetchone()["count"]



    cur.execute(
        """
        SELECT COUNT(*)

        FROM user_plans
        """
    )

    total_plans = cur.fetchone()["count"]



    conn.close()



    return render_template(
        "admin_dashboard.html",

        total_users=total_users,

        total_deposits=total_deposits,

        pending_withdrawals=pending_withdrawals,

        total_plans=total_plans
    )


@app.route("/admin/add_balance/<int:user_id>")
def add_balance(user_id):

    if "admin_id" not in session:
        return redirect("/admin/login")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE users
        SET balance = balance + 100
        WHERE id=%s
    """, (user_id,))

    conn.commit()
    conn.close()

    flash("GHS 100 added to user balance.")

    return redirect("/admin/users")


@app.route("/admin/deduct_balance/<int:user_id>")
def deduct_balance(user_id):

    if "admin_id" not in session:
        return redirect("/admin/login")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE users
        SET balance = balance - 100
        WHERE id=%s
    """, (user_id,))

    conn.commit()
    conn.close()

    flash("GHS 100 deducted from user balance.")

    return redirect("/admin/users")
# =====================================
# ADMIN USERS
# =====================================

@app.route("/admin/users")
def admin_users():

    if "admin_id" not in session:
        return redirect(
            "/admin/login"
        )


    conn = get_db()
    cur = conn.cursor()


    cur.execute(
        """
        SELECT *

        FROM users

        ORDER BY id DESC
        """
    )


    users = cur.fetchall()


    conn.close()



    return render_template(
        "admin_users.html",
        users=users
    )

@app.route("/admin/plans")
def admin_plans():

    if "admin_id" not in session:
        return redirect("/admin/login")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM user_plans
        ORDER BY id DESC
    """)

    plans = cur.fetchall()

    conn.close()

    return render_template(
        "admin_plans.html",
        plans=plans
    )

# =====================================
# ADMIN ALL DEPOSITS
# =====================================

@app.route("/admin/all_deposits")
def admin_all_deposits():

    if "admin_id" not in session:
        return redirect(
            "/admin/login"
        )


    conn = get_db()
    cur = conn.cursor()


    cur.execute(
        """
        SELECT

        deposits.*,

        users.phone


        FROM deposits


        JOIN users

        ON deposits.user_id = users.id


        ORDER BY deposits.id DESC

        """
    )


    deposits = cur.fetchall()


    conn.close()


    return render_template(
        "admin_all_deposits.html",
        deposits=deposits
    )



# =====================================
# ERROR HANDLER
# =====================================

@app.errorhandler(404)
def not_found(error):

    return "Page not found", 404



@app.errorhandler(500)
def server_error(error):

    return "Server error", 500



# =====================================
# CREATE UPLOAD FOLDER
# =====================================

if not os.path.exists(
    UPLOAD_FOLDER
):

    os.makedirs(
        UPLOAD_FOLDER
    )
@app.route("/daily_checkin")
def daily_checkin():

    if "user_id" not in session:
        return redirect(url_for("login"))

    flash("Daily check-in is not available yet.")

    return redirect(url_for("dashboard"))

@app.route("/setup_database")
def setup_database():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        phone VARCHAR(30) UNIQUE NOT NULL,
        password TEXT NOT NULL,
        withdraw_password TEXT NOT NULL,
        balance DECIMAL(12,2) DEFAULT 10.00,
        income DECIMAL(12,2) DEFAULT 0.00,
        referral_code VARCHAR(20) UNIQUE NOT NULL,
        invited_by VARCHAR(20),
        account_name VARCHAR(100),
        network VARCHAR(50),
        account_number VARCHAR(50),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS deposits (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        amount DECIMAL(12,2),
        screenshot TEXT,
        status VARCHAR(30) DEFAULT 'Processing',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS withdrawals (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        amount DECIMAL(12,2),
        fee DECIMAL(12,2),
        receive_amount DECIMAL(12,2),
        status VARCHAR(30) DEFAULT 'Processing',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS user_plans (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        plan_name VARCHAR(100),
        investment DECIMAL(12,2),
        daily_income DECIMAL(12,2),
        duration INTEGER,
        total_earned DECIMAL(12,2) DEFAULT 0,
        days_completed INTEGER DEFAULT 0,
        last_claim TIMESTAMP,
        status VARCHAR(30) DEFAULT 'Active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS admins (
        id SERIAL PRIMARY KEY,
        username VARCHAR(50) UNIQUE,
        password TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    conn.commit()
    conn.close()

    return "Database created successfully!"

# =====================================
# RUN APPLICATION
# =====================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        )
    )
