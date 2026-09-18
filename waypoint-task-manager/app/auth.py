from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app import db
from app.models import THEMES, User

bp = Blueprint("auth", __name__)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        if not name or not email or len(password) < 8:
            flash("Name, email, and an 8+ character password are required.")
            return redirect(url_for("auth.register"))
        if User.query.filter_by(email=email).first():
            flash("That email is already registered.")
            return redirect(url_for("auth.register"))
        user = User(name=name, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for("main.dashboard"))
    return render_template("auth.html", mode="register")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash("Email or password did not match.")
            return redirect(url_for("auth.login"))
        login_user(user, remember=True)
        return redirect(url_for("main.dashboard"))
    return render_template("auth.html", mode="login")


@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        theme = request.form.get("theme")
        if not name:
            flash("Name cannot be empty.")
            return redirect(url_for("auth.settings"))
        current_user.name = name[:80]
        if theme in THEMES:
            current_user.theme = theme
        password = request.form.get("password") or ""
        if password:
            if len(password) < 8:
                flash("New password must be at least 8 characters.")
                return redirect(url_for("auth.settings"))
            current_user.set_password(password)
        db.session.commit()
        flash("Settings saved.")
        return redirect(url_for("auth.settings"))
    return render_template("settings.html")


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.landing"))
