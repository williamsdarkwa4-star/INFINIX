import os
import random
import string
import psycopg2
from werkzeug.utils import secure_filename
from psycopg2.extras import RealDictCursor

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    session,
    flash
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)


# =========================
# FLASK CONFIGURATION
# =========================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "tesla-secret-key-change-this"
)


# =========================
# DATABASE CONNECTION
# =========================

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db():

    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor
    )



# =========================
# TESLA VIP PLANS
# =========================

PLANS = [

    {
        "id": 1,
        "name": "TESLA VIP 1",
        "price": 100,
        "daily": 20,
        "days": 100
    },

    {
        "id": 2,
        "name": "TESLA VIP 2",
        "price": 300,
        "daily": 40,
        "days": 100
    },

    {
        "id": 3,
        "name": "TESLA VIP 3",
        "price": 500,
        "daily": 60,
        "days": 100
    },

    {
        "id": 4,
        "name": "TESLA VIP 4",
        "price": 700,
        "daily": 80,
        "days": 100
    }
    {
    "id": 5,
    "name": "TESLA VIP 5",
    "price": 850,
    "daily": 166,
    "days": 100
},

{
    "id": 6,
    "name": "TESLA VIP 6",
    "price": 1500,
    "daily": 280,
    "days": 100
}
]



# =========================
# GENERATE REFERRAL CODE
# =========================

def create_referral_code():

    return "TESLA" + "".join(
        random.choices(
            string.digits,
            k=6
        )
    )



# =========================
# HOME
# =========================

@app.route("/")
def home():

    return redirect("/login")



# =========================
# REGISTER
# =========================
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
            return redirect("/register")

        if withdraw_password != confirm_withdraw_password:
            flash("Withdrawal passwords do not match.")
            return redirect("/register")

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            "SELECT id FROM users WHERE phone=%s",
            (phone,)
        )

        if cur.fetchone():
            conn.close()
            flash("Phone number already registered.")
            return redirect("/register")

        hashed_password = generate_password_hash(password)
        hashed_withdraw_password = generate_password_hash(withdraw_password)

        referral_code = create_referral_code()

        cur.execute("""
            INSERT INTO users
            (
                phone,
                password,
                withdraw_password,
                balance,
                referral_code,
                invited_by
            )
            VALUES
            (%s,%s,%s,%s,%s,%s)
        """,
        (
            phone,
            hashed_password,
            hashed_withdraw_password,
            10,
            referral_code,
            invite_code if invite_code else None
        ))

        conn.commit()
        conn.close()

        flash("Registration successful. GHS 10 welcome bonus added.")

        return redirect("/login")

    return render_template("register.html")





# =========================
# LOGIN
# =========================

@app.route("/login", methods=["GET","POST"])
def login():

    if request.method == "POST":

        phone = request.form["phone"]

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



        if user and check_password_hash(
            user["password"],
            password
        ):

            session["user_id"] = user["id"]

            return redirect("/dashboard")



        flash("Invalid login")



    return render_template(
        "login.html"
    )



# =========================
# LOGOUT
# =========================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")

# =========================
# DASHBOARD
# =========================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect("/login")


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


    return render_template(
        "dashboard.html",
        user=user,
        plans=PLANS
    )



# =========================
# PROFILE
# =========================

@app.route("/profile")
def profile():

    if "user_id" not in session:
        return redirect("/login")


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


    return render_template(
        "profile.html",
        user=user
    )



# =========================
# TEAM / REFERRAL PAGE
# =========================

@app.route("/team")
def team():

    if "user_id" not in session:
        return redirect("/login")


    conn = get_db()
    cur = conn.cursor()


    # Get user's referral code

    cur.execute(
        """
        SELECT referral_code
        FROM users
        WHERE id=%s
        """,
        (session["user_id"],)
    )


    user = cur.fetchone()



    # Find people invited by this user

    cur.execute(
        """
        SELECT phone, created_at
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



# =========================
# SERVICE PAGE
# =========================

@app.route("/service")
def service():

    return render_template(
        "service.html"
    )

# =========================
# RUN APP
# =========================

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
