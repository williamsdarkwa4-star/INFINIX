from flask import Flask, render_template
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

app = Flask(__name__)
app.secret_key = "your_secret_key"


conn = sqlite3.connect("database.db")
cursor = conn.cursor()
def get_db_connection():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?",
           (username,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]

            flash("Login successful!")
            return redirect(url_for("dashboard"))

        flash("Invalid username or password.")
        return redirect(url_for("login"))

    return render_template("login.html")
    
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        hashed_password = generate_password_hash(password)

        conn = get_db_connection()

        try:
            conn.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, hashed_password)
            )
            conn.commit()
            flash("Registration successful! Please log in.")
            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash("This user already exists.")

        finally:
            conn.close()

    return render_template("register.html")

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    return render_template("dashboard.html")

@app.route("/lessons")
def lessons():
	return render_template("lessons.html")

@app.route("/mathematics")
def mathematics():
	return render_template("mathematics.html")
@app.route("/math_quiz")
def math_quiz():
    return render_template("math_quiz.html")


@app.route("/math_result", methods=["POST"])
def math_result():

    score = 0

    answers = {
        "q1": "B",
        "q2": "D",
        "q3": "C",
        "q4": "A",
        "q5": "B"
    }

    for question, correct_answer in answers.items():
        if request.form.get(question) == correct_answer:
            score += 1

    return render_template(
        "math_result.html",
        score=score,
        total=len(answers)
    )

@app.route("/science")
def science():
	return render_template("science.html")

@app.route("/english_language")
def english_language():
	return render_template("english_language.html")

@app.route("/english_quiz")
def english_quiz():
    return render_template("english_quiz.html")

@app.route("/english_result", methods=["POST"])
def english_result():

    score = 0

    answers = {
        "q1": "A",
        "q2": "A",
        "q3": "B",
        "q4": "D",
        "q5": "A"
    }

    for question, correct_answer in answers.items():
        if request.form.get(question) == correct_answer:
            score += 1

    return render_template(
        "english_result.html",
        score=score,
        total=len(answers)
    )

@app.route("/ict")
def ict():
	return render_template("ict.html")

@app.route("/social_studies")
def social_studies():
	return render_template("social_studies.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
