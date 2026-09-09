"""
Operator-only database export/import.

Render (and most free-tier PaaS) run every deploy in a fresh
container with no persistent disk, so anything written to the SQLite
file at runtime — new events, votes, whatever a live demo generated —
is lost the moment you push a new commit and it redeploys. These two
routes let an operator pull the live database down before pushing,
and push it back up afterward, so a redeploy doesn't start from an
empty database.

Disabled unless DINETOGETHER_ADMIN_TOKEN is set in the environment —
with no token configured these routes 404 as if they don't exist, so
a default deployment gains no extra attack surface. Set a long random
token as a Render environment variable; never commit it.
"""
from __future__ import annotations

import os
import secrets
import shutil
import sqlite3
import tempfile

from flask import Blueprint, abort, after_this_request, current_app, jsonify, request, send_file

from app import csrf, limiter

bp = Blueprint("admin", __name__, url_prefix="/admin")

_SQLITE_HEADER = b"SQLite format 3\x00"


def _require_admin_token() -> None:
    expected = os.environ.get("DINETOGETHER_ADMIN_TOKEN")
    if not expected:
        abort(404)

    provided = request.values.get("token", "")
    if not secrets.compare_digest(provided, expected):
        abort(403)


@bp.get("/export-db")
@limiter.limit("5 per minute")
def export_db():
    _require_admin_token()

    fd, tmp_path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)

    # sqlite3's backup API takes a consistent snapshot even while the
    # live app has the database open — copying the raw file instead
    # could grab it mid-write and produce a corrupt export.
    source = sqlite3.connect(current_app.config["DATABASE"])
    snapshot = sqlite3.connect(tmp_path)
    with snapshot:
        source.backup(snapshot)
    source.close()
    snapshot.close()

    @after_this_request
    def _cleanup(response):
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return response

    return send_file(
        tmp_path,
        as_attachment=True,
        download_name="dinetogether-export.sqlite",
        mimetype="application/octet-stream",
    )


@bp.post("/import-db")
@csrf.exempt
@limiter.limit("5 per minute")
def import_db():
    _require_admin_token()

    uploaded = request.files.get("db_file")
    if uploaded is None or uploaded.filename == "":
        abort(400, description="No file uploaded under the 'db_file' field.")

    fd, tmp_path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    uploaded.save(tmp_path)

    with open(tmp_path, "rb") as f:
        header = f.read(len(_SQLITE_HEADER))
    if header != _SQLITE_HEADER:
        os.remove(tmp_path)
        abort(400, description="Uploaded file is not a SQLite database.")

    try:
        check = sqlite3.connect(tmp_path)
        check.execute("SELECT COUNT(*) FROM events")
        check.close()
    except sqlite3.DatabaseError:
        os.remove(tmp_path)
        abort(400, description="Uploaded file failed schema validation.")

    shutil.move(tmp_path, current_app.config["DATABASE"])

    return jsonify({"status": "ok", "message": "Database replaced."})
