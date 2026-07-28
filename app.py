import os
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
from datetime import datetime, timedelta


app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "tesla-demo-secret-key"
)


# Upload settings

UPLOAD_FOLDER = "static/uploads"

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


ALLOWED_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg"
}




# Render PostgreSQL Database

DATABASE_URL = os.environ.get("DATABASE_URL")



def get_db():

    conn = psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor
    )

    return conn





# Tesla VIP Plans

PLANS = [

    {
        "id":1,
        "name":"TESLA VIP 1",
        "investment":100,
        "daily":20,
        "duration":100,
        "image":"https://images.unsplash.com/photo-1560958089-b8a1929cea89"
    },


    {
        "id":2,
        "name":"TESLA VIP 2",
        "investment":300,
        "daily":40,
        "duration":100,
        "image":"https://images.unsplash.com/photo-1617788138017-80ad40651399"
    },


    {
        "id":3,
        "name":"TESLA VIP 3",
        "investment":500,
        "daily":60,
        "duration":100,
        "image":"https://images.unsplash.com/photo-1542362567-b07e54358753"
    },


    {
        "id":4,
        "name":"TESLA VIP 4",
        "investment":700,
        "daily":80,
        "duration":100,
        "image":"https://images.unsplash.com/photo-1606664515524-ed2f786a0bd6"
    },


    {
        "id":5,
        "name":"TESLA VIP 5",
        "investment":850,
        "daily":166,
        "duration":100,
        "image":"https://images.unsplash.com/photo-1492144534655-ae79c964c9d7"
    },


    {
        "id"6,
        "name":"TESLA VIP 6",
        "investment":1500,
        "daily":280,
        "duration":100,
        "image":"https://images.unsplash.com/photo-1560958089-b8a1929cea89"
    }

]





def allowed_file(filename):

    return (
        "." in filename and
        filename.rsplit(".",1)[1].lower()
        in ALLOWED_EXTENSIONS
    )





# Home redirect

@app.route("/")
def home():

    return redirect(
        url_for("login")
    )
# =========================
# USER AUTH ROUTES
# =========================


@app.route("/register", methods=["GET","POST"])
def register():

    if request.method == "POST":

        phone = request.form["phone"]
        password = request.form["password"]
        confirm = request.form["confirm_password"]
        withdraw_password = request.form["withdraw_password"]
        invite = request.form.get("invite_code")


        if password != confirm:
            flash("Passwords do not match")
            return redirect("/register")


        hashed_password = generate_password_hash(password)
        hashed_withdraw_password = generate_password_hash(
        withdraw_password
        )

        conn = get_db()
        cur = conn.cursor()


        cur.execute(
            """
            SELECT * FROM users
            WHERE phone=%s
            """,
            (phone,)
        )

        existing = cur.fetchone()


        if existing:
            flash("Phone already registered")
            conn.close()
            return redirect("/register")



        cur.execute(
            """
            INSERT INTO users
            (
            phone,
            password,
            withdraw_password,
            invite_code,
            balance
            )
            VALUES
            (%s,%s,%s,%s,%s)
            """,
            (
            phone,
            hashed_password,
            hashed_withdraw_password,
            invite,
            10
            )
        )


        conn.commit()
        conn.close()


        flash("Registration successful. GHS 10 gift added.")

        return redirect("/login")



    return render_template(
        "register.html"
    )






@app.route("/login", methods=["GET","POST"])
def login():


    if request.method=="POST":


        phone=request.form["phone"]
        password=request.form["password"]



        conn=get_db()
        cur=conn.cursor()


        cur.execute(
            """
            SELECT * FROM users
            WHERE phone=%s
            """,
            (phone,)
        )


        user=cur.fetchone()


        conn.close()



        if user and check_password_hash(
            user["password"],
            password
        ):


            session["user_id"]=user["id"]


            return redirect(
                "/dashboard"
            )


        flash("Invalid login")



    return render_template(
        "login.html"
    )







# =========================
# USER DASHBOARD
# =========================


@app.route("/dashboard")
def dashboard():


    if "user_id" not in session:
        return redirect("/login")



    conn=get_db()
    cur=conn.cursor()



    cur.execute(
        """
        SELECT *
        FROM users
        WHERE id=%s
        """,
        (session["user_id"],)
    )


    user=cur.fetchone()


    conn.close()



    return render_template(
        "dashboard.html",
        user=user,
        plans=PLANS
    )









# =========================
# TEAM PAGE
# =========================


@app.route("/team")
def team():


    if "user_id" not in session:
        return redirect("/login")


    user_id=session["user_id"]


    conn=get_db()
    cur=conn.cursor()



    cur.execute(
        """
        SELECT COUNT(*) 
        FROM users
        WHERE invite_code IN
        (
        SELECT invite_code
        FROM users
        WHERE id=%s
        )
        """,
        (user_id,)
    )


    result=cur.fetchone()


    conn.close()



    return render_template(
        "team.html",
        direct_team=result["count"],
        total_team=result["count"],
        team_income=0,
        commission=0,
        level1_members=result["count"],
        level1_income=0,
        level2_members=0,
        level2_income=0,
        level3_members=0,
        level3_income=0,
        referral_link=""
    )







# =========================
# SERVICE
# =========================


@app.route("/service")
def service():


    return render_template(
        "service.html"
    )







# =========================
# PROFILE
# =========================


@app.route("/profile")
def profile():


    if "user_id" not in session:
        return redirect("/login")



    conn=get_db()
    cur=conn.cursor()


    cur.execute(
        """
        SELECT *
        FROM users
        WHERE id=%s
        """,
        (session["user_id"],)
    )


    user=cur.fetchone()


    conn.close()



    return render_template(
        "profile.html",
        user=user
    )







# =========================
# LOGOUT
# =========================


@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")
# =========================
# MY PLAN PAGE
# =========================


@app.route("/my_plan")
def my_plan():

    if "user_id" not in session:
        return redirect("/login")


    conn = get_db()
    cur = conn.cursor()


    cur.execute(
        """
        SELECT *
        FROM user_plans
        WHERE user_id=%s
        """,
        (session["user_id"],)
    )


    plans = cur.fetchall()


    conn.close()


    return render_template(
        "my_plan.html",
        plans=plans
    )







# =========================
# BUY TESLA PLAN
# =========================


@app.route("/buy_plan/<int:plan_id>")
def buy_plan(plan_id):


    if "user_id" not in session:
        return redirect("/login")



    plan = None


    for p in PLANS:

        if p["id"] == plan_id:
            plan = p



    if not plan:

        flash("Plan not found")
        return redirect("/dashboard")




    conn=get_db()
    cur=conn.cursor()



    cur.execute(
        """
        SELECT balance
        FROM users
        WHERE id=%s
        """,
        (session["user_id"],)
    )


    user=cur.fetchone()



    if user["balance"] < plan["investment"]:

        conn.close()

        flash(
        "Insufficient balance. Please deposit first."
        )

        return redirect("/deposit")





    cur.execute(
        """
        UPDATE users
        SET balance = balance - %s
        WHERE id=%s
        """,
        (
        plan["investment"],
        session["user_id"]
        )
    )





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
        plan["name"],
        plan["investment"],
        plan["daily"],
        plan["duration"],
        "Active"
        )
    )

# Referral commission 20%

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

        commission = plan["investment"] * 0.20


        cur.execute(
            """
            UPDATE users
            SET income = income + %s
            WHERE id=%s
            """,
            (
            commission,
            referrer["id"]
            )
        )

    conn.commit()
    conn.close()



    flash(
    "TESLA plan activated successfully"
    )


    return redirect("/my_plan")
# =========================
# DEPOSIT
# =========================


@app.route("/deposit", methods=["GET","POST"])
def deposit():

    if "user_id" not in session:
        return redirect("/login")


    if request.method == "POST":

        amount = float(request.form["amount"])


        if amount < 90 or amount > 1500:
            flash("Deposit must be between GHS 90 and GHS 1500")
            return redirect("/deposit")


        screenshot = request.files.get("screenshot")

        filename = ""


        if screenshot and allowed_file(screenshot.filename):

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


        flash("Deposit submitted. Wait 0-20 minutes.")

        return redirect("/deposit")



    return render_template(
        "deposit.html"
    )







# =========================
# SAVE WITHDRAW ACCOUNT
# =========================


@app.route("/save_account", methods=["POST"])
def save_account():


    if "user_id" not in session:
        return redirect("/login")



    account_name = request.form["account_name"]

    network = request.form["network"]

    number = request.form["account_number"]



    conn=get_db()
    cur=conn.cursor()



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
        number,
        session["user_id"]
        )
    )


    conn.commit()
    conn.close()



    flash("Account saved successfully")

    return redirect("/withdraw")








# =========================
# WITHDRAW
# =========================


# =========================
# WITHDRAW
# =========================

@app.route("/withdraw", methods=["GET", "POST"])
def withdraw():

    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM users WHERE id=%s",
        (session["user_id"],)
    )

    user = cur.fetchone()

    if not user:
        conn.close()
        session.clear()
        return redirect("/login")

    if request.method == "POST":

        try:
            amount = float(request.form["amount"])
        except ValueError:
            conn.close()
            flash("Enter a valid amount.")
            return redirect("/withdraw")

        withdraw_password = request.form["withdraw_password"]

        if amount < 30:
            conn.close()
            flash("Minimum withdrawal is GHS 30.")
            return redirect("/withdraw")

        if not user["withdraw_password"]:
            conn.close()
            flash("Please create a withdrawal password first.")
            return redirect("/profile")

        if not check_password_hash(
            user["withdraw_password"],
            withdraw_password
        ):
            conn.close()
            flash("Incorrect withdrawal password.")
            return redirect("/withdraw")

        if float(user["balance"]) < amount:
            conn.close()
            flash("Insufficient balance.")
            return redirect("/withdraw")

        if not user["account_number"] or not user["network"]:
            conn.close()
            flash("Please bind your withdrawal account first.")
            return redirect("/withdraw")

        fee = round(amount * 0.18, 2)
        receive_amount = round(amount - fee, 2)

        cur.execute(
            """
            UPDATE users
            SET balance = balance - %s
            WHERE id = %s
            """,
            (amount, session["user_id"])
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
            (%s, %s, %s, %s, %s)
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

        flash("Withdrawal request submitted successfully. Processing time is 0–34 minutes.")
        return redirect("/withdraw")

    conn.close()

    return render_template(
        "withdraw.html",
        user=user
    )

# =========================
# ADMIN LOGIN
# =========================


@app.route("/admin/login", methods=["GET","POST"])
def admin_login():


    if request.method=="POST":


        username=request.form["username"]

        password=request.form["password"]



        conn=get_db()
        cur=conn.cursor()



        cur.execute(
            """
            SELECT *
            FROM admins
            WHERE username=%s
            """,
            (username,)
        )


        admin=cur.fetchone()


        conn.close()



        if admin and check_password_hash(
            admin["password"],
            password
        ):


            session["admin_id"]=admin["id"]


            return redirect(
                "/admin/dashboard"
            )



        flash("Invalid admin login")



    return render_template(
        "admin_login.html"
    )







# =========================
# ADMIN DASHBOARD
# =========================


@app.route("/admin/dashboard")
def admin_dashboard():


    if "admin_id" not in session:
        return redirect("/admin/login")



    conn=get_db()
    cur=conn.cursor()



    cur.execute(
        "SELECT COUNT(*) FROM users"
    )

    total_users=cur.fetchone()["count"]



    cur.execute(
        """
        SELECT COALESCE(SUM(amount),0)
        FROM deposits
        WHERE status='Approved'
        """
    )

    total_deposits=cur.fetchone()["coalesce"]



    cur.execute(
        """
        SELECT COUNT(*)
        FROM deposits
        WHERE status='Processing'
        """
    )

    pending_deposits=cur.fetchone()["count"]




    cur.execute(
        """
        SELECT COUNT(*)
        FROM withdrawals
        WHERE status='Processing'
        """
    )

    pending_withdrawals=cur.fetchone()["count"]



    cur.execute(
        """
        SELECT COUNT(*)
        FROM user_plans
        """
    )

    total_plans=cur.fetchone()["count"]



    conn.close()



    return render_template(
        "admin_dashboard.html",
        total_users=total_users,
        total_deposits=total_deposits,
        pending_deposits=pending_deposits,
        pending_withdrawals=pending_withdrawals,
        total_plans=total_plans,
        total_balance=0
    )







# =========================
# ADMIN USERS
# =========================


@app.route("/admin/users")
def admin_users():


    if "admin_id" not in session:
        return redirect("/admin/login")



    conn=get_db()
    cur=conn.cursor()



    cur.execute(
        """
        SELECT *
        FROM users
        ORDER BY id DESC
        """
    )


    users=cur.fetchall()



    conn.close()



    return render_template(
        "admin_users.html",
        users=users
    )







# =========================
# ADMIN DEPOSITS
# =========================


@app.route("/admin/deposits")
def admin_deposits():

    if "admin_id" not in session:
        return redirect("/admin/login")

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT deposits.*, users.phone
        FROM deposits
        JOIN users
        ON deposits.user_id = users.id
        WHERE deposits.status = 'Processing'
        ORDER BY deposits.id DESC
        """
    )

    deposits = cur.fetchall()

    conn.close()

    return render_template(
        "admin_deposits.html",
        deposits=deposits
    )







@app.route("/admin/deposit/approve/<int:id>")
def approve_deposit(id):


    conn=get_db()
    cur=conn.cursor()



    cur.execute(
        """
        UPDATE deposits
        SET status='Approved'
        WHERE id=%s
        """,
        (id,)
    )


    conn.commit()

    conn.close()


    return redirect("/admin/deposits")








@app.route("/admin/deposit/reject/<int:id>")
def reject_deposit(id):


    conn=get_db()
    cur=conn.cursor()



    cur.execute(
        """
        UPDATE deposits
        SET status='Rejected'
        WHERE id=%s
        """,
        (id,)
    )


    conn.commit()

    conn.close()


    return redirect("/admin/deposits")







# =========================
# ADMIN WITHDRAWALS
# =========================


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
        WHERE withdrawals.status = 'Processing'
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


    conn=get_db()
    cur=conn.cursor()



    cur.execute(
        """
        UPDATE withdrawals
        SET status='Approved'
        WHERE id=%s
        """,
        (id,)
    )


    conn.commit()

    conn.close()


    return redirect("/admin/withdrawals")








@app.route("/admin/withdraw/reject/<int:id>")
def reject_withdraw(id):


    conn=get_db()
    cur=conn.cursor()



    cur.execute(
        """
        UPDATE withdrawals
        SET status='Rejected'
        WHERE id=%s
        """,
        (id,)
    )


    conn.commit()

    conn.close()


    return redirect("/admin/withdrawals")
# =========================
# ADMIN LOGOUT
# =========================

@app.route("/admin/logout")
def admin_logout():

    session.pop("admin_id", None)

    return redirect("/admin/login")





# =========================
# CREATE UPLOAD FOLDER
# =========================

if not os.path.exists(UPLOAD_FOLDER):

    os.makedirs(UPLOAD_FOLDER)





# =========================
# ERROR HANDLING
# =========================

@app.errorhandler(404)
def page_not_found(error):

    return "Page not found", 404






# =========================
# START APPLICATION
# =========================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
