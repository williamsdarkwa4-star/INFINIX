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

PLANS = [

    {
        "id": 1,
        "name": "TESLA VIP 1",
        "investment": 100,
        "daily": 20,
        "duration": 100,
        "image": "https://images.unsplash.com/photo-1560958089-b8a1929cea89"
    },

    {
        "id": 2,
        "name": "TESLA VIP 2",
        "investment": 300,
        "daily": 40,
        "duration": 100,
        "image": "https://images.unsplash.com/photo-1617788138017-80ad40651399"
    },

    {
        "id": 3,
        "name": "TESLA VIP 3",
        "investment": 500,
        "daily": 60,
        "duration": 100,
        "image": "https://images.unsplash.com/photo-1542362567-b07e54358753"
    },

    {
        "id": 4,
        "name": "TESLA VIP 4",
        "investment": 700,
        "daily": 80,
        "duration": 100,
        "image": "https://images.unsplash.com/photo-1606664515524-ed2f786a0bd6"
    },

    {
        "id": 5,
        "name": "TESLA VIP 5",
        "investment": 850,
        "daily": 166,
        "duration": 100,
        "image": "https://images.unsplash.com/photo-1492144534655-ae79c964c9d7"
    },

    {
        "id": 6,
        "name": "TESLA VIP 6",
        "investment": 1500,
        "daily": 280,
        "duration": 100,
        "image": "https://images.unsplash.com/photo-1560958089-b8a1929cea89"
    }

]
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
        plans=PLANS
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
