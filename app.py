from flask import Flask, render_template, request, redirect, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash

import os
import secrets
import psycopg2
from psycopg2.extras import RealDictCursor


# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-key-in-render"
)


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_connection():
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not configured."
        )

    return psycopg2.connect(
        database_url,
        cursor_factory=RealDictCursor
    )


# =========================================================
# DATABASE SETUP
# =========================================================

def create_tables():

    conn = get_connection()
    cursor = conn.cursor()

    try:

        # -------------------------------------------------
        # USERS
        # -------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                fullname VARCHAR(100) NOT NULL,
                username VARCHAR(50) UNIQUE NOT NULL,
                phone VARCHAR(20) UNIQUE NOT NULL,
                login_password TEXT NOT NULL,
                withdrawal_password TEXT NOT NULL,
                referral_code VARCHAR(20) UNIQUE NOT NULL,
                referred_by VARCHAR(20),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


        # -------------------------------------------------
        # ACCOUNTS
        # -------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE
                    UNIQUE,

                deposit_account NUMERIC(12,2)
                    DEFAULT 0,

                income_account NUMERIC(12,2)
                    DEFAULT 0,

                referral_account NUMERIC(12,2)
                    DEFAULT 0
            )
        """)


        # -------------------------------------------------
        # BIND ACCOUNTS
        # -------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bind_accounts (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                account_name VARCHAR(100) NOT NULL,

                phone_number VARCHAR(20) NOT NULL,

                network VARCHAR(50) NOT NULL,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


        # -------------------------------------------------
        # REFERRALS
        # -------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id SERIAL PRIMARY KEY,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                referred_user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                level INTEGER DEFAULT 1,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        cursor.close()
        conn.close()


# =========================================================
# CREATE TABLES WHEN APP STARTS
# =========================================================

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

    # Referral code from URL
    # Example:
    # /register?ref=AB12CD34

    invite_code = request.args.get(
        "ref",
        ""
    ).strip().upper()


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

        withdrawal_password = request.form.get(
            "withdrawal_password",
            ""
        )

        referred_by = request.form.get(
            "referred_by",
            ""
        ).strip().upper()


        # -------------------------------------------------
        # VALIDATION
        # -------------------------------------------------

        if not fullname:
            return "Please enter your full name."

        if not username:
            return "Please enter your username."

        if not phone:
            return "Please enter your phone number."

        if not password:
            return "Please enter your login password."

        if not withdrawal_password:
            return "Please enter your withdrawal password."


        if len(password) < 6:
            return "Login password must be at least 6 characters."


        if len(withdrawal_password) < 4:
            return "Withdrawal password must be at least 4 characters."


        # -------------------------------------------------
        # DATABASE
        # -------------------------------------------------

        conn = get_connection()
        cursor = conn.cursor()


        try:

            # Check username
            cursor.execute("""
                SELECT id
                FROM users
                WHERE username = %s
            """, (username,))

            existing_username = cursor.fetchone()


            if existing_username:
                return "Username already exists."


            # Check phone
            cursor.execute("""
                SELECT id
                FROM users
                WHERE phone = %s
            """, (phone,))

            existing_phone = cursor.fetchone()


            if existing_phone:
                return "Phone number already exists."


            # -------------------------------------------------
            # GENERATE UNIQUE REFERRAL CODE
            # -------------------------------------------------

            while True:

                referral_code = secrets.token_hex(
                    4
                ).upper()

                cursor.execute("""
                    SELECT id
                    FROM users
                    WHERE referral_code = %s
                """, (referral_code,))

                if not cursor.fetchone():
                    break


            # -------------------------------------------------
            # CHECK REFERRER
            # -------------------------------------------------

            valid_referral = None

            if referred_by:

                cursor.execute("""
                    SELECT id
                    FROM users
                    WHERE referral_code = %s
                """, (referred_by,))

                inviter = cursor.fetchone()

                if inviter:
                    valid_referral = referred_by


            # -------------------------------------------------
            # HASH PASSWORDS
            # -------------------------------------------------

            login_hash = generate_password_hash(
                password
            )

            withdrawal_hash = generate_password_hash(
                withdrawal_password
            )


            # -------------------------------------------------
            # CREATE USER
            # -------------------------------------------------

            cursor.execute("""
                INSERT INTO users (
                    fullname,
                    username,
                    phone,
                    login_password,
                    withdrawal_password,
                    referral_code,
                    referred_by
                )

                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )

                RETURNING id
            """, (
                fullname,
                username,
                phone,
                login_hash,
                withdrawal_hash,
                referral_code,
                valid_referral
            ))


            new_user = cursor.fetchone()

            user_id = new_user["id"]


            # -------------------------------------------------
            # CREATE USER ACCOUNT
            # -------------------------------------------------

            cursor.execute("""
                INSERT INTO accounts (
                    user_id,
                    deposit_account,
                    income_account,
                    referral_account
                )

                VALUES (
                    %s,
                    0,
                    0,
                    0
                )
            """, (user_id,))


            # -------------------------------------------------
            # CREATE REFERRAL RECORD
            # -------------------------------------------------

            if valid_referral:

                cursor.execute("""
                    SELECT id
                    FROM users
                    WHERE referral_code = %s
                """, (valid_referral,))

                inviter = cursor.fetchone()


                if inviter:

                    cursor.execute("""
                        INSERT INTO referrals (
                            user_id,
                            referred_user_id,
                            level
                        )

                        VALUES (
                            %s,
                            %s,
                            1
                        )
                    """, (
                        inviter["id"],
                        user_id,
                    ))


            conn.commit()


            # -------------------------------------------------
            # SEND USER TO LOGIN
            # -------------------------------------------------

            return redirect(
                url_for("login")
            )


        except psycopg2.Error:

            conn.rollback()

            return "Registration could not be completed. Please try again."


        finally:

            cursor.close()
            conn.close()


    # GET REQUEST

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

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )


        if not phone or not password:

            return "Please enter your phone number and password."


        conn = get_connection()
        cursor = conn.cursor()


        try:

            cursor.execute("""
                SELECT *
                FROM users
                WHERE phone = %s
                LIMIT 1
            """, (phone,))


            user = cursor.fetchone()


            if not user:

                return "Invalid phone number or password."


            if not check_password_hash(
                user["login_password"],
                password
            ):

                return "Invalid phone number or password."


            # -------------------------------------------------
            # LOGIN SESSION
            # -------------------------------------------------

            session.clear()

            session["user_id"] = user["id"]


            return redirect(
                url_for("dashboard")
            )


        finally:

            cursor.close()
            conn.close()


    return render_template(
        "login.html"
    )


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    user_id = session["user_id"]


    conn = get_connection()
    cursor = conn.cursor()


    try:

        # -------------------------------------------------
        # USER
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                id,
                fullname,
                username,
                phone,
                referral_code,
                referred_by,
                created_at
            FROM users
            WHERE id = %s
        """, (user_id,))


        user = cursor.fetchone()


        if not user:

            session.clear()

            return redirect(
                url_for("login")
            )


        # -------------------------------------------------
        # ACCOUNT
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                id,
                deposit_account,
                income_account,
                referral_account
            FROM accounts
            WHERE user_id = %s
        """, (user_id,))


        account = cursor.fetchone()


        # -------------------------------------------------
        # REFERRAL COUNT
        # -------------------------------------------------

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM referrals
            WHERE user_id = %s
        """, (user_id,))


        referral_result = cursor.fetchone()


        referral_count = referral_result["total"]


        # -------------------------------------------------
        # DASHBOARD
        # -------------------------------------------------

        return render_template(
            "dashboard.html",
            user=user,
            account=account,
            referral_count=referral_count
        )


    finally:

        cursor.close()
        conn.close()


# =========================================================
# PROFILE
# =========================================================

@app.route("/profile")
def profile():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    conn = get_connection()
    cursor = conn.cursor()


    try:

        cursor.execute("""
            SELECT
                id,
                fullname,
                username,
                phone,
                referral_code,
                referred_by,
                created_at
            FROM users
            WHERE id = %s
        """, (
            session["user_id"],
        ))


        user = cursor.fetchone()


        cursor.execute("""
            SELECT *
            FROM accounts
            WHERE user_id = %s
        """, (
            session["user_id"],
        ))


        account = cursor.fetchone()


        return render_template(
            "profile.html",
            user=user,
            account=account
        )


    finally:

        cursor.close()
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

        return redirect(
            url_for("login")
        )


    conn = get_connection()
    cursor = conn.cursor()


    try:

        if request.method == "POST":

            account_name = request.form.get(
                "account_name",
                ""
            ).strip()

            phone_number = request.form.get(
                "phone_number",
                ""
            ).strip()

            network = request.form.get(
                "network",
                ""
            ).strip()


            if not account_name:
                return "Please enter account name."

            if not phone_number:
                return "Please enter phone number."

            if not network:
                return "Please select a network."


            cursor.execute("""
                INSERT INTO bind_accounts (
                    user_id,
                    account_name,
                    phone_number,
                    network
                )

                VALUES (
                    %s,
                    %s,
                    %s,
                    %s
                )
            """, (
                session["user_id"],
                account_name,
                phone_number,
                network
            ))


            conn.commit()


            return redirect(
                url_for("bind_account")
            )


        cursor.execute("""
            SELECT *
            FROM bind_accounts
            WHERE user_id = %s
            ORDER BY id DESC
        """, (
            session["user_id"],
        ))


        accounts = cursor.fetchall()


        return render_template(
            "bind_account.html",
            accounts=accounts
        )


    finally:

        cursor.close()
        conn.close()


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# =========================================================
# RUN APP
# =========================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        ),
        debug=False
    )
