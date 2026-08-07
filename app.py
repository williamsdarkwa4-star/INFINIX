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







# DASHBOARD - SHOW PLANS

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



    plans = db.execute("""
    SELECT *

    FROM plans

    WHERE status='Active'

    """).fetchall()



    return render_template(
        "dashboard.html",
        user=user,
        accounts=accounts,
        plans=plans
    )



# BUY PLAN

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
        return "Insufficient deposit balance"



    # Deduct amount

    db.execute("""
    UPDATE accounts

    SET deposit_account = deposit_account - ?

    WHERE user_id=?

    """,
    (
    plan["investment_amount"],
    session["user_id"]
    ))



    # Create active plan

    db.execute("""
    INSERT INTO user_plans

    (
    user_id,
    plan_id
    )

    VALUES(?,?)

    """,
    (
    session["user_id"],
    plan_id
    ))



    # Transaction record

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
    "Plan purchased",
    "Successful"
    ))



    db.commit()


    return redirect("/my_plan")







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



# DEPOSIT PAGE

@app.route("/deposit")
def deposit():

    if "user_id" not in session:
        return redirect("/login")


    return render_template("deposit.html")


# PAYSTACK SUCCESS

@app.route("/deposit_success")
def deposit_success():


    if "user_id" not in session:

        return redirect("/login")



    reference = request.args.get("reference")

    amount = request.args.get("amount")

    phone = request.args.get("phone")



    db = get_db()



    # Save deposit as pending

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



    # Add transaction history

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
    "Deposit payment submitted",
    "Pending"
    ))



    db.commit()



    return """
    <h2>
    Deposit submitted successfully
    </h2>

    <p>
    Your deposit is waiting for approval.
    </p>

    <a href="/dashboard">
    Back to Dashboard
    </a>
    """

# TEAM PAGE

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



    # Level 1

    level1 = db.execute("""
    SELECT *

    FROM users

    WHERE referred_by=?

    """,
    (user["referral_code"],)).fetchall()



    level1_count = len(level1)



    # Level 2

    level2 = []


    for member in level1:


        second = db.execute("""
        SELECT *

        FROM users

        WHERE referred_by=?

        """,
        (member["referral_code"],)).fetchall()



        level2.extend(second)




    level2_count = len(level2)





    # Level 3

    level3 = []


    for member in level2:


        third = db.execute("""
        SELECT *

        FROM users

        WHERE referred_by=?

        """,
        (member["referral_code"],)).fetchall()



        level3.extend(third)



    level3_count = len(level3)





    return render_template(
        "team.html",

        level1=level1,

        level2=level2,

        level3=level3,

        level1_count=level1_count,

        level2_count=level2_count,

        level3_count=level3_count

    )

    

# LOGOUT

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")



# SERVICE / SUPPORT

@app.route("/support", methods=["GET","POST"])
def support():

    if "user_id" not in session:

        return redirect("/login")


    db = get_db()


    if request.method == "POST":

        message = request.form["message"]


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


        return redirect("/service")



    messages = db.execute("""
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



        if admin:


            if check_password_hash(
                admin["password"],
                password
            ):


                session["admin_id"] = admin["id"]

                return redirect("/admin/dashboard")



        return "Invalid admin username or password"



    return render_template("admin_login.html")






# ADMIN CHECK

def admin_required(route):

    @wraps(route)

    def check(*args, **kwargs):


        if "admin_id" not in session:

            return redirect("/admin/login")



        return route(*args, **kwargs)


    return check






# ADMIN DASHBOARD

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():


    db = get_db()



    total_users = db.execute("""
    SELECT COUNT(*) AS count

    FROM users

    """).fetchone()["count"]




    pending_deposits = db.execute("""
    SELECT COUNT(*) AS count

    FROM deposits

    WHERE status='Pending'

    """).fetchone()["count"]





    pending_withdrawals = db.execute("""
    SELECT COUNT(*) AS count

    FROM withdrawals

    WHERE status='Pending'

    """).fetchone()["count"]





    return render_template(

        "admin.html",

        total_users=total_users,

        pending_deposits=pending_deposits,

        pending_withdrawals=pending_withdrawals

    )


# =========================
# ADMIN WITHDRAWALS
# =========================


@app.route("/admin/withdrawals")
@admin_required
def admin_withdrawals():


    db = get_db()


    withdrawals = db.execute("""
    SELECT

    withdrawals.*,

    users.username,

    users.phone,

    bind_accounts.account_name,

    bind_accounts.phone_number,

    bind_accounts.network


    FROM withdrawals


    JOIN users

    ON withdrawals.user_id = users.id


    JOIN bind_accounts

    ON withdrawals.account_id = bind_accounts.id


    WHERE withdrawals.status='Pending'


    ORDER BY withdrawals.id DESC


    """).fetchall()



    return render_template(
        "admin_withdraw.html",
        withdrawals=withdrawals
    )







# APPROVE WITHDRAWAL


@app.route("/admin/withdraw/approve/<int:id>")
@admin_required
def approve_withdraw(id):


    db = get_db()


    withdrawal = db.execute("""
    SELECT *

    FROM withdrawals

    WHERE id=?

    """,
    (id,)).fetchone()



    if withdrawal:


        db.execute("""
        UPDATE withdrawals

        SET status='Approved'

        WHERE id=?

        """,
        (id,))



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
        withdrawal["user_id"],
        "Withdrawal",
        withdrawal["amount"],
        "Withdrawal approved",
        "Successful"
        ))



        db.commit()



    return redirect("/admin/withdrawals")







# REJECT WITHDRAWAL


@app.route("/admin/withdraw/reject/<int:id>")
@admin_required
def reject_withdraw(id):


    db = get_db()


    db.execute("""
    UPDATE withdrawals

    SET status='Rejected'

    WHERE id=?

    """,
    (id,))



    db.commit()



    return redirect("/admin/withdrawas")


# =========================
# ADMIN DEPOSITS
# =========================


@app.route("/admin/deposits")
@admin_required
def admin_deposits():


    db = get_db()


    deposits = db.execute("""
    SELECT

    deposits.*,

    users.username,

    users.phone


    FROM deposits


    JOIN users

    ON deposits.user_id = users.id


    WHERE deposits.status='Pending'


    ORDER BY deposits.id DESC


    """).fetchall()



    return render_template(
        "admin_deposit.html",
        deposits=deposits
    )







# APPROVE DEPOSIT


@app.route("/admin/deposit/approve/<int:id>")
@admin_required
def approve_deposit(id):


    db = get_db()



    deposit = db.execute("""
    SELECT *

    FROM deposits

    WHERE id=?

    """,
    (id,)).fetchone()



    if deposit:



        # Update deposit status

        db.execute("""
        UPDATE deposits

        SET status='Approved'

        WHERE id=?

        """,
        (id,))





        # Add money to user deposit account

        db.execute("""
        UPDATE accounts

        SET deposit_account = deposit_account + ?

        WHERE user_id=?

        """,
        (
        deposit["amount"],
        deposit["user_id"]
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
        deposit["user_id"],
        "Deposit",
        deposit["amount"],
        "Deposit approved",
        "Successful"
        ))





        db.commit()



    return redirect("/admin/deposits")









# REJECT DEPOSIT


@app.route("/admin/deposit/reject/<int:id>")
@admin_required
def reject_deposit(id):


    db = get_db()



    db.execute("""
    UPDATE deposits

    SET status='Rejected'

    WHERE id=?

    """,
    (id,))



    db.commit()



    return redirect("/admin/deposits")

# =========================
# ADMIN USERS
# =========================

@app.route("/admin/users")
@admin_required
def admin_users():

    db = get_db()

    search = request.args.get("search", "")


    users = db.execute("""
    SELECT *

    FROM users

    WHERE username LIKE ?

    OR phone LIKE ?

    ORDER BY id DESC

    """,
    (
    "%" + search + "%",
    "%" + search + "%"
    )).fetchall()



    return render_template(
        "admin_users.html",
        users=users,
        search=search
    )
    
# =========================
# ADMIN USER MANAGEMENT
# =========================


@app.route("/admin/users", methods=["GET","POST"])
@admin_required
def admin_users():


    db = get_db()


    search = request.args.get("search","")


    users = db.execute("""
    SELECT *

    FROM users

    WHERE username LIKE ?

    OR phone LIKE ?

    ORDER BY id DESC

    """,
    (
    "%" + search + "%",
    "%" + search + "%"
    )).fetchall()



    return render_template(
        "admin_users.html",
        users=users,
        search=search
    )







# ADD / DEDUCT USER FUNDS


@app.route("/admin/user/funds/<int:user_id>", methods=["POST"])
@admin_required
def manage_user_funds(user_id):


    db = get_db()


    amount = float(request.form["amount"])

    action = request.form["action"]



    if action == "add":

        db.execute("""
        UPDATE accounts

        SET deposit_account = deposit_account + ?

        WHERE user_id=?

        """,
        (amount,user_id))



    elif action == "deduct":

        db.execute("""
        UPDATE accounts

        SET deposit_account = deposit_account - ?

        WHERE user_id=?

        """,
        (amount,user_id))



    db.commit()



    return redirect("/admin/users")








# CHANGE PASSWORDS


@app.route("/admin/user/password/<int:user_id>", methods=["POST"])
@admin_required
def change_user_password(user_id):


    db=get_db()



    login_password = request.form.get("login_password")

    withdrawal_password = request.form.get("withdrawal_password")



    if login_password:


        db.execute("""
        UPDATE users

        SET login_password=?

        WHERE id=?

        """,
        (
        generate_password_hash(login_password),
        user_id
        ))





    if withdrawal_password:


        db.execute("""
        UPDATE users

        SET withdrawal_password=?

        WHERE id=?

        """,
        (
        generate_password_hash(withdrawal_password),
        user_id
        ))



    db.commit()



    return redirect("/admin/users")









# ADD / DEDUCT USER FUNDS


@app.route("/admin/user/funds/<int:user_id>", methods=["POST"])
@admin_required
def manage_user_funds(user_id):


    db = get_db()


    amount = float(request.form["amount"])

    action = request.form["action"]



    if action == "add":

        db.execute("""
        UPDATE accounts

        SET deposit_account = deposit_account + ?

        WHERE user_id=?

        """,
        (amount,user_id))



    elif action == "deduct":

        db.execute("""
        UPDATE accounts

        SET deposit_account = deposit_account - ?

        WHERE user_id=?

        """,
        (amount,user_id))



    db.commit()



    return redirect("/admin/users")








# CHANGE PASSWORDS


@app.route("/admin/user/password/<int:user_id>", methods=["POST"])
@admin_required
def change_user_password(user_id):


    db=get_db()



    login_password = request.form.get("login_password")

    withdrawal_password = request.form.get("withdrawal_password")



    if login_password:


        db.execute("""
        UPDATE users

        SET login_password=?

        WHERE id=?

        """,
        (
        generate_password_hash(login_password),
        user_id
        ))





    if withdrawal_password:


        db.execute("""
        UPDATE users

        SET withdrawal_password=?

        WHERE id=?

        """,
        (
        generate_password_hash(withdrawal_password),
        user_id
        ))



    db.commit()



    return redirect("/admin/users")


# =========================
# ADMIN BIND ACCOUNTS
# =========================


@app.route("/admin/bind_accounts")
@admin_required
def admin_bind_accounts():


    db = get_db()


    accounts = db.execute("""
    SELECT

    bind_accounts.*,

    users.username,

    users.phone


    FROM bind_accounts


    JOIN users

    ON bind_accounts.user_id = users.id


    ORDER BY bind_accounts.id DESC


    """).fetchall()



    return render_template(
        "admin_bind_accounts.html",
        accounts=accounts
    )







# DELETE BIND ACCOUNT


@app.route("/admin/bind_account/delete/<int:id>")
@admin_required
def delete_bind_account(id):


    db = get_db()



    db.execute("""
    DELETE FROM bind_accounts

    WHERE id=?

    """,
    (id,))



    db.commit()



    return redirect("/admin/bind_accounts")




@app.route("/admin/logout")
def admin_logout():

    session.pop("admin_id", None)

    return redirect("/admin/login")


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
