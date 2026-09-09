"""
DineTogether — Flask application factory.

Architecture (per ADR-0001, SRS Appendix C):
    routes (this file)  ->  services/  ->  repositories/  ->  SQLite

Routes never touch SQLite directly. Services never import Flask's
request/session objects — that keeps the business logic layer testable
without a running Flask app.
"""
from __future__ import annotations

import os
from datetime import timedelta

from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf import CSRFProtect

from app.db import init_db, close_db

limiter = Limiter(key_func=get_remote_address)
csrf = CSRFProtect()


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)

    # NFR-04.8: secret key and DB path come from environment / instance
    # config, never hard-coded or committed to source control.
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("DINETOGETHER_SECRET_KEY", "dev-only-change-me"),
        DATABASE=os.path.join(app.instance_path, "dinetogether.sqlite"),
        # NFR-04.5: session cookie hardening.
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
    )

    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)

    # In production behind HTTPS, also set SESSION_COOKIE_SECURE=True.
    # Defaults to False so local HTTP development (per SRS 2.1.3) still
    # works, but auto-enables on Render, which sets RENDER=true for
    # every deployed service.
    app.config.setdefault("SESSION_COOKIE_SECURE", os.environ.get("RENDER") == "true")

    app.teardown_appcontext(close_db)

    with app.app_context():
        init_db()

    limiter.init_app(app)
    csrf.init_app(app)

    from app.routes import bp as main_bp
    app.register_blueprint(main_bp)

    return app
