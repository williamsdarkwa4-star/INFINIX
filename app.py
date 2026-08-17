import os
import json
import logging
from uuid import uuid4
from flask import (
    Flask,
    render_template,
    url_for,
    redirect,
    request,
    session,
    flash,
)
from werkzeug.routing import BuildError

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PLANS_FILE = os.environ.get("PLANS_FILE", "data/plans.json")
ADMIN_SECRET_ENV = os.environ.get("ADMIN_SECRET", None)


def _ensure_data_dir(path):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def load_plans():
    try:
        if not os.path.exists(PLANS_FILE):
            return []
        with open(PLANS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to load plans from %s", PLANS_FILE)
        return []


def save_plans(plans):
    try:
        _ensure_data_dir(PLANS_FILE)
        with open(PLANS_FILE, "w", encoding="utf-8") as f:
            json.dump(plans, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.exception("Failed to save plans to %s", PLANS_FILE)


def create_app(config_object=None):
    app = Flask(__name__)
    # SECRET_KEY required for session usage
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

    if config_object:
        app.config.from_object(config_object)

    # Helper: require admin session
    def admin_required(fn):
        def wrapper(*a, **kw):
            if not session.get("is_admin"):
                return redirect(url_for("admin_login") + "?next=" + request.path)
            return fn(*a, **kw)

        wrapper.__name__ = fn.__name__
        return wrapper

    # --- Routes ---------------------------------------------------------
    @app.route("/")
    def index():
        return redirect(url_for("dashboard"))

    @app.route("/dashboard")
    def dashboard():
        user = {"username": "example"}
        account = {"id": 1, "name": "Example Co"}

        # Load plans from file and pass to template
        plans = load_plans()

        # Resolve optional endpoints safely
        def safe_url(name, blueprint_try=None):
            try:
                return url_for(name)
            except BuildError:
                if blueprint_try:
                    try:
                        return url_for(blueprint_try)
                    except BuildError:
                        return None
                return None

        support_url = safe_url("support", "support_bp.support")
        deposit_url = safe_url("deposit", "deposit_bp.deposit")
        withdraw_url = safe_url("withdraw", "withdraw_bp.withdraw")

        return render_template(
            "dashboard.html",
            user=user,
            account=account,
            plans=plans,
            support_url=support_url,
            deposit_url=deposit_url,
            withdraw_url=withdraw_url,
        )

    # Support / Deposit / Withdraw placeholders (so templates can call url_for)
    @app.route("/support", endpoint="support")
    def support():
        try:
            return render_template("support.html")
        except Exception:
            return ("<h1>Support</h1><p>Create templates/support.html to customize this page.</p>"), 200

    @app.route("/deposit", endpoint="deposit")
    def deposit():
        try:
            return render_template("deposit.html")
        except Exception:
            return ("<h1>Deposit</h1><p>Create templates/deposit.html to customize this page.</p>"), 200

    @app.route("/withdraw", endpoint="withdraw")
    def withdraw():
        try:
            return render_template("withdraw.html")
        except Exception:
            return ("<h1>Withdraw</h1><p>Create templates/withdraw.html to customize this page.</p>"), 200

    # Admin login (sets session is_admin when ADMIN_SECRET matches)
    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        next_url = request.args.get("next") or url_for("admin_plans")
        if request.method == "POST":
            secret = request.form.get("secret")
            # If ADMIN_SECRET_ENV is set, require it; otherwise allow (dev convenience)
            if ADMIN_SECRET_ENV and secret != ADMIN_SECRET_ENV:
                flash("Invalid admin secret", "error")
                return redirect(url_for("admin_login"))
            session["is_admin"] = True
            return redirect(next_url)
        try:
            return render_template("admin_login.html", next=next_url)
        except Exception:
            # simple fallback form
            form_html = (
                f'<form method="post" action="{url_for("admin_login")}">'
                '<input name="secret" placeholder="Admin Secret">'
                '<button type="submit">Login</button>'
                "</form>"
            )
            return form_html

    @app.route("/admin/logout")
    def admin_logout():
        session.pop("is_admin", None)
        return redirect(url_for("index"))

    # Admin plans management (list, add, delete) - persists to PLANS_FILE
    @app.route("/admin/plans", methods=["GET", "POST"])
    @admin_required
    def admin_plans():
        if request.method == "POST":
            # Add plan
            title = request.form.get("title")
            price = request.form.get("price")
            if not title:
                flash("Title is required", "error")
                return redirect(url_for("admin_plans"))
            plans = load_plans()
            new_plan = {"id": str(uuid4()), "title": title, "price": price}
            plans.append(new_plan)
            save_plans(plans)
            flash("Plan added", "success")
            return redirect(url_for("admin_plans"))

        plans = load_plans()
        try:
            return render_template("admin_plans.html", plans=plans)
        except Exception:
            # fallback simple admin page
            items = "".join(
                f'<li>{p.get("title")} - {p.get("price")} '
                f'<form method="post" action="{url_for("admin_delete_plan")}" style="display:inline">'
                f'<input type="hidden" name="id" value="{p.get("id")}">'
                '<button>Delete</button></form></li>'
                for p in plans
            )
            fallback = (
                "<h1>Admin Plans</h1>"
                f"<ul>{items}</ul>"
                "<h2>Add Plan</h2>"
                f'<form method="post" action="{url_for("admin_plans")}">'
                '<input name="title" placeholder="Title">'
                '<input name="price" placeholder="Price">'
                '<button type="submit">Add</button>'
                "</form>"
            )
            return fallback

    @app.route("/admin/plans/delete", methods=["POST"])
    @admin_required
    def admin_delete_plan():
        plan_id = request.form.get("id")
        if not plan_id:
            flash("No id provided", "error")
            return redirect(url_for("admin_plans"))
        plans = load_plans()
        plans = [p for p in plans if p.get("id") != plan_id]
        save_plans(plans)
        flash("Plan deleted", "success")
        return redirect(url_for("admin_plans"))

    # Health check
    @app.route("/.well-known/health")
    def health():
        return "OK", 200

    # Diagnostic routes (remove or protect in production)
    @app.route("/_routes")
    def list_routes():
        output = []
        for rule in app.url_map.iter_rules():
            methods = ",".join(sorted(rule.methods - {"HEAD", "OPTIONS"}))
            output.append(f"{rule.endpoint}: {rule.rule} [{methods}]")
        return "<br>".join(sorted(output)), 200

    # Error handler
    @app.errorhandler(500)
    def server_error(e):
        logger.exception("Server error: %s", e)
        try:
            return render_template("500.html"), 500
        except Exception:
            return ("An internal error occurred."), 500

    # Log routes
    routes = sorted([r.endpoint for r in app.url_map.iter_rules()])
    logger.info("Registered routes: %s", routes)

    return app


# Module-level app so WSGI servers can import it
app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG", "0") == "1")
