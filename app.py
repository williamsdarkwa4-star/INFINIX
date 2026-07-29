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

@app.route("/register", methods=["GET","POST"])
def register():

    if request.method == "POST":

        phone = request.form["phone"]
        password = request.form["password"]
        confirm = request.form["confirm_password"]


        if password != confirm:

            flash("Passwords do not match")
            return redirect("/register")



        conn = get_db()
        cur = conn.cursor()


        cur.execute(
            """
            SELECT id
            FROM users
            WHERE phone=%s
            """,
            (phone,)
        )


        exists = cur.fetchone()


        if exists:

            conn.close()

            flash("Phone already registered")
            return redirect("/register")



        hashed = generate_password_hash(password)

        referral = create_referral_code()


        cur.execute(
            """
            INSERT INTO users
            (
                phone,
                password,
                balance,
                referral_code
            )

            VALUES
            (%s,%s,%s,%s)

            """,
            (
                phone,
                hashed,
                10,
                referral
            )
        )


        conn.commit()
        conn.close()


        flash(
            "Registration successful. Welcome bonus added."
        )


        return redirect("/login")



    return render_template(
        "register.html"
    )




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
