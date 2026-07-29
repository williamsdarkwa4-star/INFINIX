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
