import io
import sqlite3
import tempfile


def test_admin_routes_404_without_a_configured_token(client, monkeypatch):
    monkeypatch.delenv("DINETOGETHER_ADMIN_TOKEN", raising=False)
    assert client.get("/admin/export-db").status_code == 404
    assert client.post("/admin/import-db").status_code == 404


def test_export_db_rejects_a_wrong_token(client, monkeypatch):
    monkeypatch.setenv("DINETOGETHER_ADMIN_TOKEN", "correct-token")
    resp = client.get("/admin/export-db?token=wrong-token")
    assert resp.status_code == 403


def test_export_db_returns_a_snapshot_of_the_live_database(client, monkeypatch, app, db):
    monkeypatch.setenv("DINETOGETHER_ADMIN_TOKEN", "correct-token")
    client.post(
        "/register",
        data={"username": "exportcheck", "password": "password123", "display_name": "Export Check"},
        follow_redirects=True,
    )

    resp = client.get("/admin/export-db?token=correct-token")
    assert resp.status_code == 200
    assert resp.data.startswith(b"SQLite format 3\x00")

    with tempfile.NamedTemporaryFile(suffix=".sqlite") as tmp:
        tmp.write(resp.data)
        tmp.flush()
        con = sqlite3.connect(tmp.name)
        usernames = [row[0] for row in con.execute("SELECT username FROM users")]
        con.close()

    assert "exportcheck" in usernames


def test_import_db_replaces_the_live_database(client, monkeypatch, app):
    monkeypatch.setenv("DINETOGETHER_ADMIN_TOKEN", "correct-token")

    with tempfile.NamedTemporaryFile(suffix=".sqlite") as alt_file:
        alt_app = _make_app_with_seed_user(alt_file.name, "importeduser")
        with open(alt_file.name, "rb") as f:
            uploaded_bytes = f.read()

    resp = client.post(
        "/admin/import-db",
        data={"token": "correct-token", "db_file": (io.BytesIO(uploaded_bytes), "upload.sqlite")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200

    con = sqlite3.connect(app.config["DATABASE"])
    usernames = [row[0] for row in con.execute("SELECT username FROM users")]
    con.close()
    assert usernames == ["importeduser"]
    del alt_app


def test_import_db_rejects_a_non_sqlite_upload(client, monkeypatch):
    monkeypatch.setenv("DINETOGETHER_ADMIN_TOKEN", "correct-token")
    resp = client.post(
        "/admin/import-db",
        data={"token": "correct-token", "db_file": (io.BytesIO(b"not a database"), "bad.sqlite")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400


def _make_app_with_seed_user(db_path, username):
    from app import create_app

    alt_app = create_app({"DATABASE": db_path, "WTF_CSRF_ENABLED": False})
    alt_app.test_client().post(
        "/register",
        data={"username": username, "password": "password123", "display_name": username},
        follow_redirects=True,
    )
    return alt_app
