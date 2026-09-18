from flask import Flask
from flask_login import LoginManager, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy import inspect, text

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()


def _ensure_columns() -> None:
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    if "user" not in tables:
        return
    cols = {column["name"] for column in inspector.get_columns("user")}
    if "theme" not in cols:
        db.session.execute(text("ALTER TABLE user ADD COLUMN theme VARCHAR(20) DEFAULT 'dark'"))
        db.session.commit()


def create_app() -> Flask:
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.config.from_object("app.config.Config")

    from pathlib import Path

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Sign in to open your boards."

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))

    from app.auth import bp as auth_bp
    from app.routes import bp as main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    @app.context_processor
    def inject_shell():
        inbox_count = 0
        if current_user.is_authenticated:
            from app.routes import assigned_open_query

            inbox_count = assigned_open_query().count()
        return {"inbox_count": inbox_count}

    with app.app_context():
        db.create_all()
        _ensure_columns()

    return app
