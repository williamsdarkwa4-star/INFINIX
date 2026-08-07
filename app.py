from flask import Flask, render_template, request, redirect, session
from database import get_db, create_tables
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import secrets


app = Flask(__name__)

app.secret_key = "change_this_secret_key"


# Create database tables
create_tables()



# HOME

@app.route("/")
def home():

    return redirect("/login")





# REGISTER

@app.route("/register", methods=["GET","POST"])
def register():

    invite_code = request.args.get("ref","")


    if request.method == "POST":

        fullname = request.form["fullname"]
        username = request.form["username"]
        phone = request.form["phone"]

        password = request.form["password"]

        withdrawal_password = request.form["withdrawal_password"]

        referred_by = request.form.get("referred_by")



        login_password_hash = generate_password_hash(password)


        withdrawal_password_hash = generate_password_hash(
            withdrawal_password
        )



        referral_code = secrets.token_hex(4).upper()



        db = get_db()

        cursor = db.cursor()



        try:


            cursor.execute("""
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

            VALUES (?,?,?,?,?,?,?)

            """,
            (
                fullname,
                username,
                phone,
                login_password_hash,
                withdrawal_password_hash,
                referral_code,
                referred_by
            ))



            user_id = cursor.lastrowid




            # Create user wallets

            cursor.execute("""
            INSERT INTO accounts(user_id)

            VALUES(?)

            """,
            (user_id,))





            # Save referral relationship

            if referred_by:


                inviter = cursor.execute("""

                SELECT id

                FROM users

                WHERE referral_code=?

                """,
                (referred_by,)).fetchone()



                if inviter:


                    cursor.execute("""
                    INSERT INTO referrals
                    (
                    user_id,
                    referred_user_id,
                    level
                    )

                    VALUES(?,?,?)

                    """,
                    (
                    inviter["id"],
                    user_id,
                    1
                    ))





            db.commit()


            return redirect("/login")



        except sqlite3.IntegrityError:


            return "Username or phone already exists"




    return render_template(
        "register.html",
        invite_code=invite_code
    )







# LOGIN

@app.route("/login", methods=["GET","POST"])
def login():


    if request.method == "POST":


        phone = request.form["phone"]

        password = request.form["password"]



        db = get_db()



        user = db.execute("""
        SELECT *

        FROM users

        WHERE phone=?

        """,
        (phone,)).fetchone()



        if user:


            if check_password_hash(
                user["login_password"],
                password
            ):


                session["user_id"] = user["id"]


                return redirect("/dashboard")



        return "Invalid login details"




    return render_template("login.html")







# DASHBOARD

@app.route("/dashboard")
def dashboard():


    if "user_id" not in session:

        return redirect("/login")



    db = get_db()



    user = db.execute("""

    SELECT *

    FROM users

    WHERE id=?

    """,
    (session["user_id"],)).fetchone()



    accounts = db.execute("""

    SELECT *

    FROM accounts

    WHERE user_id=?

    """,
    (session["user_id"],)).fetchone()



    return render_template(
        "dashboard.html",
        user=user,
        accounts=accounts
    )







# PROFILE

@app.route("/profile")
def profile():


    if "user_id" not in session:

        return redirect("/login")



    db = get_db()



    user = db.execute("""

    SELECT *

    FROM users

    WHERE id=?

    """,
    (session["user_id"],)).fetchone()



    accounts = db.execute("""

    SELECT *

    FROM accounts

    WHERE user_id=?

    """,
    (session["user_id"],)).fetchone()



    return render_template(
        "profile.html",
        user=user,
        accounts=accounts
    )







# LOGOUT

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")







if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
