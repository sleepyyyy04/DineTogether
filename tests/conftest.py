import os
import tempfile

import pytest

from app import create_app
from app.db import get_db


@pytest.fixture
def app():
    db_fd, db_path = tempfile.mkstemp()
    application = create_app(
        {
            "TESTING": True,
            "DATABASE": db_path,
            # Keep the real 10/min limit active in most tests; a
            # dedicated test overrides this to check the limiter itself.
            # CSRF tokens are a browser-form concern; functional tests
            # post form data directly, so disable the check here (the
            # standard Flask-WTF testing pattern) rather than having
            # every test fetch and thread through a token.
            "WTF_CSRF_ENABLED": False,
        }
    )

    yield application

    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    with app.app_context():
        yield get_db()


@pytest.fixture
def user_repo(db):
    from app.repositories.user_repository import UserRepository

    return UserRepository(db)


@pytest.fixture
def make_user(user_repo):
    """Factory fixture: persist a user account directly through the
    repository, for tests that need a real User object without going
    through the HTTP registration flow. Each call needs its own
    username (UNIQUE constraint), so auto-generate one unless given."""
    from werkzeug.security import generate_password_hash

    counter = {"n": 0}

    def _make(display_name="Alex", username=None, password="password123"):
        counter["n"] += 1
        username = username or f"user{counter['n']}"
        return user_repo.create(
            username=username, password_hash=generate_password_hash(password), display_name=display_name
        )

    return _make


@pytest.fixture
def user(make_user):
    return make_user(display_name="Alex", username="alex")
