from flask import Flask, render_template, request, redirect, session
from database import get_db, create_tables
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import secrets
from datetime import datetime, timedelta

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







# BIND ACCOUNT

@app.route("/bind_account", methods=["GET","POST"])
def bind_account():

    if "user_id" not in session:

        return redirect("/login")


    db = get_db()


    if request.method == "POST":

        account_name = request.form["account_name"]

        phone_number = request.form["phone_number"]

        network = request.form["network"]



        db.execute("""
        INSERT INTO bind_accounts
        (
        user_id,
        account_name,
        phone_number,
        network
        )

        VALUES(?,?,?,?)

        """,
        (
        session["user_id"],
        account_name,
        phone_number,
        network
        ))



        db.commit()


        return redirect("/bind_account")




    accounts = db.execute("""
    SELECT *

    FROM bind_accounts

    WHERE user_id=?

    """,
    (session["user_id"],)).fetchall()



    return render_template(
        "bind_account.html",
        accounts=accounts
    )





# WITHDRAW

@app.route("/withdraw", methods=["GET","POST"])
def withdraw():

    if "user_id" not in session:

        return redirect("/login")


    db = get_db()



    if request.method == "POST":


        amount = float(request.form["amount"])

        withdrawal_password = request.form["withdrawal_password"]

        account_id = request.form["account_id"]




        user = db.execute("""
        SELECT *

        FROM users

        WHERE id=?

        """,
        (session["user_id"],)).fetchone()




        # Check withdrawal password

        if not check_password_hash(
            user["withdrawal_password"],
            withdrawal_password
        ):

            return "Invalid withdrawal password"





        # Minimum withdrawal check

        if amount < 30:

            return "Minimum withdrawal is GHS 30"





        account = db.execute("""
        SELECT *

        FROM accounts

        WHERE user_id=?

        """,
        (session["user_id"],)).fetchone()



        if account["income_account"] < amount:

            return "Insufficient balance"






        # Withdrawal fee 16%

        fee = amount * 0.16


        final_amount = amount - fee





        # Create withdrawal request

        db.execute("""
        INSERT INTO withdrawals

        (
        user_id,
        amount,
        account_id,
        withdrawal_fee
        )

        VALUES(?,?,?,?)

        """,
        (
        session["user_id"],
        final_amount,
        account_id,
        fee
        ))






        # Transaction history

        db.execute("""
        INSERT INTO transactions

        (
        user_id,
        transaction_type,
        amount,
        description,
        status
        )

        VALUES(?,?,?,?,?)

        """,
        (
        session["user_id"],
        "Withdrawal",
        final_amount,
        "Withdrawal request submitted",
        "Pending"
        ))





        db.commit()



        return "Withdrawal request submitted"







    accounts = db.execute("""
    SELECT *

    FROM bind_accounts

    WHERE user_id=?

    """,
    (session["user_id"],)).fetchall()




    return render_template(
        "withdraw.html",
        accounts=accounts
    )






# TRANSACTION HISTORY

@app.route("/transaction_history")
def transaction_history():

    if "user_id" not in session:

        return redirect("/login")


    db = get_db()


    transactions = db.execute("""

    SELECT *

    FROM transactions

    WHERE user_id=?

    ORDER BY id DESC

    """,
    (session["user_id"],)).fetchall()



    return render_template(
        "transaction_history.html",
        transactions=transactions
    )




# MY PLAN

@app.route("/my_plan", methods=["GET","POST"])
def my_plan():

    if "user_id" not in session:

        return redirect("/login")


    db = get_db()



    plan = db.execute("""

    SELECT 

    user_plans.*,

    plans.plan_name,

    plans.daily_income,

    plans.duration

    FROM user_plans

    JOIN plans

    ON user_plans.plan_id = plans.id

    WHERE user_plans.user_id=?

    AND user_plans.status='Active'

    """,
    (session["user_id"],)).fetchone()



    can_claim = False



    if plan:


        if plan["last_claim_time"]:


            last_claim = datetime.fromisoformat(
                plan["last_claim_time"]
            )


            if datetime.now() >= last_claim + timedelta(hours=24):

                can_claim = True



        else:

            can_claim = True





    if request.method == "POST":


        if not plan:

            return "No active plan"



        if can_claim is False:

            return "Please wait until your next claim time"





        amount = plan["daily_income"]




        # Add income to account

        db.execute("""
        UPDATE accounts

        SET income_account = income_account + ?

        WHERE user_id=?

        """,
        (
        amount,
        session["user_id"]
        ))





        # Update claim time

        db.execute("""
        UPDATE user_plans

        SET last_claim_time=?

        WHERE id=?

        """,
        (
        datetime.now(),
        plan["id"]
        ))





        # Claim history

        db.execute("""
        INSERT INTO claim_history

        (
        user_id,
        plan_id,
        amount
        )

        VALUES(?,?,?)

        """,
        (
        session["user_id"],
        plan["plan_id"],
        amount
        ))





        # Transaction history

        db.execute("""
        INSERT INTO transactions

        (
        user_id,
        transaction_type,
        amount,
        description,
        status
        )

        VALUES(?,?,?,?,?)

        """,
        (
        session["user_id"],
        "Income",
        amount,
        "Daily plan income claimed",
        "Successful"
        ))



        db.commit()



        return redirect("/my_plan")





    return render_template(
        "my_plan.html",
        plan=plan,
        can_claim=can_claim
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
