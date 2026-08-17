import os
import logging
from flask import Flask, render_template, url_for, redirect, request
from werkzeug.routing import BuildError

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app(config_object=None):
    app = Flask(__name__)
    if config_object:
        app.config.from_object(config_object)

    # Example: register optional blueprints safely
    # If you have blueprints in your project, import & register them here.
    # If they fail to import or register, we log the error instead of crashing.
    optional_blueprints = [
        # ("my_blueprint.module", "bp_instance", "/prefix"),
        # Example: ("app.support.views", "support_bp", None),
    ]
    for module_path, bp_name, url_prefix in optional_blueprints:
        try:
            module = __import__(module_path, fromlist=[bp_name])
            bp = getattr(module, bp_name)
            app.register_blueprint(bp, url_prefix=url_prefix)
            logger.info("Registered blueprint %s from %s", bp_name, module_path)
        except Exception as exc:
            logger.exception("Could not register blueprint %s from %s: %s", bp_name, module_path, exc)

    # --- Routes ---------------------------------------------------------

    @app.route("/")
    def index():
        # simple redirect to dashboard for convenience
        return redirect(url_for("dashboard"))

    @app.route("/dashboard")
    def dashboard():
        # Example: gather user/account info here
        user = {"username": "example"}  # replace with real lookup
        account = {"id": 1, "name": "Example Co"}
        PLANS = []  # replace with your actual plans

        # Build support_url safely so templates don't raise BuildError
        try:
            support_url = url_for("support")
        except BuildError:
            # Try blueprint-qualified name if you expect a blueprint
            try:
                support_url = url_for("support_bp.support")  # change if your blueprint name differs
            except BuildError:
                support_url = None
                logger.warning("No 'support' endpoint found; dashboard will render without a support link")

        return render_template(
            "dashboard.html",
            user=user,
            account=account,
            plans=PLANS,
            support_url=support_url,
        )

    # Provide a support route so url_for('support') works.
    # Replace the body with your real support UI or handler.
    @app.route("/support", endpoint="support")
    def support():
        # If you have a template for support, render it.
        # Keep the endpoint name as 'support' so templates calling url_for('support') succeed.
        return render_template("support.html")

    # Admin login route to avoid 404s seen in logs (define real logic)
    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if request.method == "POST":
            # implement real authentication
            return redirect(url_for("dashboard"))
        return render_template("admin_login.html")  # create this template or change as needed

    # Health check for platform (Render, Heroku, etc.)
    @app.route("/.well-known/health")
    def health():
        return "OK", 200

    # Temporary diagnostic route to list endpoints (remove or protect in production)
    @app.route("/_routes")
    def list_routes():
        output = []
        for rule in app.url_map.iter_rules():
            methods = ",".join(sorted(rule.methods - {"HEAD", "OPTIONS"}))
            output.append(f"{rule.endpoint}: {rule.rule} [{methods}]")
        return "<br>".join(sorted(output)), 200

    # Error handler to log exceptions
    @app.errorhandler(500)
    def server_error(e):
        logger.exception("Server error: %s", e)
        # Show generic page - avoid showing exception details in production
        return render_template("500.html"), 500

    # Log available routes once app context is ready
    @app.before_first_request
    def log_routes():
        routes = sorted([r.endpoint for r in app.url_map.iter_rules()])
        logger.info("Registered routes: %s", routes)

    return app

# If running stand-alone, create the app and run it. Platforms like Render set PORT env var.
if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 10000))  # Render often provides $PORT
    # In production, use a proper WSGI server; this is only for local/dev testing.
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG", "0") == "1")
