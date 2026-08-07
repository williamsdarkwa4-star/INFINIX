from flask import Flask, render_template, request, redirect, session
from database import get_db, create_tables
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import sqlite3
import secrets
from datetime import datetime, timedelta


app = Flask(__name__)

app.secret_key = "change_this_secret_key"


# CREATE DATABASE TABLES
create_tables()



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

    invite_code = request.args.get("ref","")


    if request.method == "POST":

        fullname = request.form["fullname"]
        username = request.form["username"]
        phone = request.form["phone"]

        password = request.form["password"]
        withdrawal_password = request.form["withdrawal_password"]

        referred_by = request.form.get("referred_by")



        login_hash = generate_password_hash(password)

        withdrawal_hash = generate_password_hash(
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
                login_hash,
                withdrawal_hash,
                referral_code,
                referred_by
            ))



            user_id = cursor.lastrowid



            # CREATE WALLET

            cursor.execute("""
            INSERT INTO accounts(user_id)

            VALUES(?)

            """,
            (user_id,))



            # SAVE REFERRAL

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





# =========================
# LOGIN
# =========================

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
# =========================
# USER DASHBOARD
# =========================

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



    account = db.execute("""
    SELECT *
    FROM accounts
    WHERE user_id=?
    """,
    (session["user_id"],)).fetchone()



    plans = db.execute("""
    SELECT *
    FROM plans
    WHERE status='Active'
    """).fetchall()



    return render_template(
        "dashboard.html",
        user=user,
        account=account,
        plans=plans
    )







# =========================
# BUY PLAN
# =========================

@app.route("/buy_plan/<int:plan_id>", methods=["POST"])
def buy_plan(plan_id):

    if "user_id" not in session:
        return redirect("/login")



    db = get_db()



    plan = db.execute("""
    SELECT *
    FROM plans
    WHERE id=?
    """,
    (plan_id,)).fetchone()



    if not plan:
        return "Plan not found"



    account = db.execute("""
    SELECT *
    FROM accounts
    WHERE user_id=?
    """,
    (session["user_id"],)).fetchone()



    if account["deposit_account"] < plan["investment_amount"]:

        return "Insufficient balance"





    # Deduct money

    db.execute("""
    UPDATE accounts

    SET deposit_account =
    deposit_account - ?

    WHERE user_id=?

    """,
    (
    plan["investment_amount"],
    session["user_id"]
    ))





    # Create user plan

    db.execute("""
    INSERT INTO user_plans
    (
    user_id,
    plan_id,
    status,
    last_claim_time
    )

    VALUES(?,?,?,?)

    """,
    (
    session["user_id"],
    plan_id,
    "Active",
    None
    ))





    # Save transaction

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
    "Plan Purchase",
    plan["investment_amount"],
    "Purchased "+plan["plan_name"],
    "Successful"
    ))



    db.commit()



    return redirect("/my_plan")







# =========================
# PROFILE
# =========================

@app.route("/profile")
def profile():

    if "user_id" not in session:
        return redirect("/login")



    db=get_db()



    user=db.execute("""
    SELECT *
    FROM users
    WHERE id=?
    """,
    (session["user_id"],)).fetchone()



    account=db.execute("""
    SELECT *
    FROM accounts
    WHERE user_id=?
    """,
    (session["user_id"],)).fetchone()



    return render_template(
        "profile.html",
        user=user,
        account=account
    )







# =========================
# BIND PAYMENT ACCOUNT
# =========================

@app.route("/bind_account", methods=["GET","POST"])
def bind_account():

    if "user_id" not in session:
        return redirect("/login")



    db=get_db()



    if request.method=="POST":


        account_name=request.form["account_name"]

        phone_number=request.form["phone_number"]

        network=request.form["network"]



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






    accounts=db.execute("""
    SELECT *
    FROM bind_accounts
    WHERE user_id=?
    """,
    (session["user_id"],)).fetchall()



    return render_template(
        "bind_account.html",
        accounts=accounts
    )







# =========================
# WITHDRAW
# =========================

@app.route("/withdraw", methods=["GET","POST"])
def withdraw():

    if "user_id" not in session:
        return redirect("/login")



    db=get_db()



    if request.method=="POST":


        amount=float(request.form["amount"])

        withdrawal_password=request.form["withdrawal_password"]

        account_id=request.form["account_id"]




        user=db.execute("""
        SELECT *
        FROM users
        WHERE id=?
        """,
        (session["user_id"],)).fetchone()



        if not check_password_hash(
            user["withdrawal_password"],
            withdrawal_password
        ):

            return "Wrong withdrawal password"






        if amount < 30:

            return "Minimum withdrawal is GHS 30"






        account=db.execute("""
        SELECT *
        FROM accounts
        WHERE user_id=?
        """,
        (session["user_id"],)).fetchone()



        if account["income_account"] < amount:

            return "Insufficient income balance"






        fee=amount * 0.16

        final_amount=amount-fee






        db.execute("""
        INSERT INTO withdrawals
        (
        user_id,
        amount,
        account_id,
        withdrawal_fee,
        status
        )

        VALUES(?,?,?,?,?)

        """,
        (
        session["user_id"],
        final_amount,
        account_id,
        fee,
        "Pending"
        ))





        db.commit()



        return redirect("/transaction_history")






    accounts=db.execute("""
    SELECT *
    FROM bind_accounts
    WHERE user_id=?
    """,
    (session["user_id"],)).fetchall()



    return render_template(
        "withdraw.html",
        accounts=accounts
    )
# =========================
# MY PLAN + DAILY CLAIM
# =========================

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

            last = datetime.fromisoformat(
                plan["last_claim_time"]
            )


            if datetime.now() >= last + timedelta(hours=24):

                can_claim = True


        else:

            can_claim = True





    if request.method == "POST":


        if not plan:

            return "No active plan"



        if not can_claim:

            return "Please wait 24 hours before claiming again"




        amount = plan["daily_income"]




        # Add income

        db.execute("""
        UPDATE accounts

        SET income_account =
        income_account + ?

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





        db.commit()


        return redirect("/my_plan")






    return render_template(
        "my_plan.html",
        plan=plan,
        can_claim=can_claim
    )







# =========================
# DEPOSIT
# =========================

@app.route("/deposit")
def deposit():

    if "user_id" not in session:

        return redirect("/login")


    return render_template(
        "deposit.html"
    )







# =========================
# DEPOSIT SUCCESS
# =========================

@app.route("/deposit_success")
def deposit_success():

    if "user_id" not in session:

        return redirect("/login")



    amount = request.args.get("amount")

    phone = request.args.get("phone")

    reference = request.args.get("reference")



    db = get_db()



    db.execute("""
    INSERT INTO deposits
    (
    user_id,
    amount,
    phone,
    payment_reference,
    payment_method,
    status
    )

    VALUES(?,?,?,?,?,?)

    """,
    (
    session["user_id"],
    float(amount),
    phone,
    reference,
    "Paystack",
    "Pending"
    ))





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
    "Deposit",
    float(amount),
    "Deposit waiting approval",
    "Pending"
    ))



    db.commit()



    return """
    <h2>Deposit submitted</h2>
    <p>Waiting for admin approval.</p>
    <a href="/dashboard">Dashboard</a>
    """






# =========================
# TEAM / REFERRAL
# =========================

@app.route("/team")
def team():

    if "user_id" not in session:

        return redirect("/login")



    db = get_db()



    user = db.execute("""
    SELECT *
    FROM users
    WHERE id=?
    """,
    (session["user_id"],)).fetchone()



    level1 = db.execute("""
    SELECT *
    FROM users
    WHERE referred_by=?
    """,
    (user["referral_code"],)).fetchall()



    level2=[]


    for member in level1:


        users = db.execute("""
        SELECT *
        FROM users
        WHERE referred_by=?
        """,
        (member["referral_code"],)).fetchall()


        level2.extend(users)




    level3=[]


    for member in level2:


        users = db.execute("""
        SELECT *
        FROM users
        WHERE referred_by=?
        """,
        (member["referral_code"],)).fetchall()


        level3.extend(users)





    return render_template(
        "team.html",
        level1=level1,
        level2=level2,
        level3=level3,
        level1_count=len(level1),
        level2_count=len(level2),
        level3_count=len(level3)
    )






# =========================
# SUPPORT
# =========================

@app.route("/support", methods=["GET","POST"])
def support():

    if "user_id" not in session:

        return redirect("/login")



    db = get_db()



    if request.method=="POST":


        message=request.form["message"]



        db.execute("""
        INSERT INTO support_messages
        (
        user_id,
        message
        )

        VALUES(?,?)

        """,
        (
        session["user_id"],
        message
        ))



        db.commit()



        return redirect("/support")





    messages=db.execute("""
    SELECT *
    FROM support_messages
    WHERE user_id=?
    ORDER BY id DESC

    """,
    (session["user_id"],)).fetchall()



    return render_template(
        "service.html",
        messages=messages
    )







# =========================
# TRANSACTION HISTORY
# =========================

@app.route("/transaction_history")
def transaction_history():

    if "user_id" not in session:

        return redirect("/login")



    db=get_db()



    transactions=db.execute("""
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






# =========================
# LOGOUT
# =========================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")
# =========================
# ADMIN SYSTEM
# =========================

from functools import wraps


# ADMIN LOGIN

@app.route("/admin/login", methods=["GET","POST"])
def admin_login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]


        db = get_db()


        admin = db.execute("""
        SELECT *
        FROM admins
        WHERE username=?
        """,
        (username,)).fetchone()



        if admin and check_password_hash(
            admin["password"],
            password
        ):

            session["admin_id"] = admin["id"]

            return redirect("/admin/dashboard")



        return "Invalid admin details"



    return render_template("admin_login.html")






# ADMIN PROTECTION

def admin_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if "admin_id" not in session:

            return redirect("/admin/login")


        return function(*args, **kwargs)


    return wrapper







# ADMIN DASHBOARD

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():

    db=get_db()


    users=db.execute("""
    SELECT COUNT(*) AS total
    FROM users
    """).fetchone()["total"]



    deposits=db.execute("""
    SELECT COUNT(*) AS total
    FROM deposits
    WHERE status='Pending'
    """).fetchone()["total"]



    withdrawals=db.execute("""
    SELECT COUNT(*) AS total
    FROM withdrawals
    WHERE status='Pending'
    """).fetchone()["total"]



    return render_template(
        "admin.html",
        users=users,
        deposits=deposits,
        withdrawals=withdrawals
    )






# =========================
# ADMIN DEPOSITS
# =========================


@app.route("/admin/deposits")
@admin_required
def admin_deposits():

    db=get_db()


    deposits=db.execute("""
    SELECT

    deposits.*,

    users.username,

    users.phone


    FROM deposits


    JOIN users

    ON deposits.user_id=users.id


    WHERE deposits.status='Pending'


    ORDER BY deposits.id DESC

    """).fetchall()



    return render_template(
        "admin_deposit.html",
        deposits=deposits
    )







@app.route("/admin/deposit/approve/<int:id>")
@admin_required
def approve_deposit(id):

    db=get_db()



    deposit=db.execute("""
    SELECT *
    FROM deposits
    WHERE id=?
    """,
    (id,)).fetchone()



    if deposit:


        db.execute("""
        UPDATE deposits
        SET status='Approved'
        WHERE id=?
        """,
        (id,))



        db.execute("""
        UPDATE accounts

        SET deposit_account =
        deposit_account + ?

        WHERE user_id=?

        """,
        (
        deposit["amount"],
        deposit["user_id"]
        ))



        db.commit()



    return redirect("/admin/deposits")







@app.route("/admin/deposit/reject/<int:id>")
@admin_required
def reject_deposit(id):

    db=get_db()


    db.execute("""
    UPDATE deposits
    SET status='Rejected'
    WHERE id=?
    """,
    (id,))


    db.commit()


    return redirect("/admin/deposits")








# =========================
# ADMIN WITHDRAWALS
# =========================


@app.route("/admin/withdrawals")
@admin_required
def admin_withdrawals():

    db=get_db()


    withdrawals=db.execute("""
    SELECT

    withdrawals.*,

    users.username,

    users.phone


    FROM withdrawals


    JOIN users

    ON withdrawals.user_id=users.id


    WHERE withdrawals.status='Pending'


    ORDER BY withdrawals.id DESC

    """).fetchall()



    return render_template(
        "admin_withdraw.html",
        withdrawals=withdrawals
    )







@app.route("/admin/withdraw/approve/<int:id>")
@admin_required
def approve_withdraw(id):

    db=get_db()


    db.execute("""
    UPDATE withdrawals

    SET status='Approved'

    WHERE id=?

    """,
    (id,))


    db.commit()


    return redirect("/admin/withdrawals")







@app.route("/admin/withdraw/reject/<int:id>")
@admin_required
def reject_withdraw(id):

    db=get_db()


    db.execute("""
    UPDATE withdrawals

    SET status='Rejected'

    WHERE id=?

    """,
    (id,))


    db.commit()


    return redirect("/admin/withdrawals")








# =========================
# ADMIN USERS
# =========================

@app.route("/admin/users")
@admin_required
def admin_users():

    db=get_db()


    search=request.args.get("search","")



    users=db.execute("""
    SELECT *

    FROM users

    WHERE username LIKE ?

    OR phone LIKE ?

    ORDER BY id DESC

    """,
    (
    "%"+search+"%",
    "%"+search+"%"
    )).fetchall()



    return render_template(
        "admin_users.html",
        users=users
    )








# =========================
# ADMIN BIND ACCOUNTS
# =========================


@app.route("/admin/bind_accounts")
@admin_required
def admin_bind_accounts():

    db=get_db()


    accounts=db.execute("""
    SELECT

    bind_accounts.*,

    users.username


    FROM bind_accounts


    JOIN users

    ON bind_accounts.user_id=users.id


    ORDER BY bind_accounts.id DESC

    """).fetchall()



    return render_template(
        "admin_bind_accounts.html",
        accounts=accounts
    )







@app.route("/admin/bind_account/delete/<int:id>")
@admin_required
def delete_bind_account(id):

    db=get_db()


    db.execute("""
    DELETE FROM bind_accounts
    WHERE id=?
    """,
    (id,))


    db.commit()


    return redirect("/admin/bind_accounts")







# ADMIN LOGOUT

@app.route("/admin/logout")
def admin_logout():

    session.pop("admin_id",None)

    return redirect("/admin/login")
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
