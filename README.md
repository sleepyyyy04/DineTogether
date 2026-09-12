# DineTogether

DineTogether is the full MVP described in the SRS: **Account
Registration/Login**, **Create Event**, **Join Event**, **Preference
Submission**, **Restaurant Recommendation**, and **Voting & Result
Management** (FR-01 through FR-05), built as a Flask monolith with
SQLite, per ADR-0001.

**Live demo:** https://dinetogether-k2hz.onrender.com/

The organizer is added as a participant at creation time (so they can
also submit preferences and vote, per SRS 2.3). Restaurant data comes
from a real, static dataset of Greater LA businesses
(`app/data/Greater_LA_cleaned.csv`, 332 rows) imported into SQLite once,
the first time the app starts. Because it's real scraped data rather
than a hand-curated demo set, a handful of rows carry the source's own
category quirks (e.g. an occasional business tagged with the wrong
category) — that's the raw dataset, not application logic, and per
DC-03/DC-04 it's intentionally left unmodified.

## Project layout

```
dinetogether/
  app/
    __init__.py                    # application factory (session, CSRF, rate limiting)
    db.py                          # SQLite connection + schema + startup CSV import
    routes.py                      # HTTP routes (thin controllers)
    admin_routes.py                # operator-only DB export/import (see "Deployment" below)
    data/
      Greater_LA_cleaned.csv       # real Greater LA restaurant dataset (DC-03/DC-04)
    services/
      validators.py                # shared field validation
      auth_service.py              # account registration / login (password hashing)
      event_service.py             # FR-01/FR-02: create_event, join_event
      preference_service.py        # FR-03: submit_preferences
      recommendation_service.py    # FR-04: filter, rank, no-match fallback
      voting_service.py            # FR-05: cast_vote, finalize, get_results
      history_service.py           # a logged-in user's cross-event history
      restaurant_import.py         # loads the CSV into SQLite once
    repositories/
      user_repository.py           # accounts SQL
      event_repository.py          # events + participants SQL
      preference_repository.py     # preferences SQL
      restaurant_repository.py     # restaurants SQL (read-only)
      vote_repository.py           # votes + results SQL
    templates/                     # server-rendered HTML (base.html + one per page)
    static/
      style.css                    # shared styling (cards, buttons, restaurant list)
      app.js                       # small client-side enhancements (sort, dropdown behavior)
  tests/
    conftest.py
    test_auth.py
    test_event_creation.py
    test_event_joining.py
    test_preferences.py
    test_recommendations.py
    test_voting.py
    test_history.py
    test_admin_routes.py
    test_routes.py
  .github/workflows/ci.yml         # pytest, Flake8, Bandit, Semgrep
  requirements.txt
  wsgi.py                          # entry point
```

## 1. Prerequisites

- Python 3.10+ (`python3 --version`)
- pip

## 2. Set up the project (one-time)

```bash
# from the dinetogether/ folder
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

## 3. Configure the secret key

Never commit a secret key (NFR-04.8). Set it as an environment variable:

```bash
export DINETOGETHER_SECRET_KEY="change-this-to-something-random"   # Windows: set DINETOGETHER_SECRET_KEY=...
```

For local development you can skip this — `app/__init__.py` falls back
to a dev-only key — but always set a real one before any shared or
network-accessible deployment.

## 4. Initialize the database

The database file, its tables, and the restaurant dataset are all
created automatically the first time the app runs (see `init_db()` in
`app/db.py`, which also imports `app/data/Greater_LA_cleaned.csv` the
first time `restaurants` is empty), so you normally don't need a
separate step. `flask init-db` also exists as an explicit CLI command:

```bash
export FLASK_APP=wsgi.py
flask init-db
```

This creates `instance/dinetogether.sqlite`.

## 5. Run the app

```bash
export FLASK_APP=wsgi.py
flask run --debug
```

Visit `http://127.0.0.1:5000/`. You can:

- **Register / log in** with a username and password (accounts are
  required to create or join an event).
- **Create an event** as the organizer → get a 4-character invitation code.
- **Join an event** → enter the code + a display name.
- **Submit preferences** (cuisine, budget, dietary, max distance,
  optional minimum rating) — each participant, including the
  organizer, has one current preference set.
- **View recommendations** — a rule-based ranked shortlist filtered by
  the whole group's budget/dietary/distance constraints, with a
  client-side sort control (recommended / rating / distance / name);
  if nothing satisfies everyone, a clearly labeled fallback of the
  closest available options is shown instead of an empty list.
- **Vote** for one or more restaurants on the shortlist (re-voting
  replaces your previous vote), then **wait** for the rest of the group
  — your own vote is shown with full restaurant detail, same as the
  recommendations list.
- **Finalize** (organizer only) once the group is ready, and **view
  results** — the winning restaurant (or every tied restaurant, each
  with full detail) plus the vote breakdown. Once finalized, preference
  edits and further votes are locked.
- **View history** — every event you've created or joined, what you
  voted for, and how it was decided.

## 6. Run the tests

```bash
python -m pytest -v
```

All 82 tests should pass. They cover:

- account registration/login, including duplicate-username and
  invalid-credential rejection,
- valid create/join flows, plus organizer-as-participant behavior,
- FR-01.3 / FR-02.2 rejection of blank, over-length, malformed, and
  unknown input,
- the invitation-code collision fix (code-review Finding 1),
- session handling after join (Finding 3) and after login,
- the join/register/login rate limits, 10 attempts/minute (NFR-04.6),
- FR-03 preference validation, edit-replaces-previous, and the
  lock-after-finalization boundary,
- FR-04 filtering (budget/dietary/distance intersection across the
  group), deterministic ranking, and the no-match fallback,
- FR-05 vote casting/replacement, tie vs. clear-winner finalization,
  and rejecting votes/edits once results are saved,
- cross-event history for a logged-in user,
- the admin export/import routes (token-gated, 404 when unset),
- a full register → login → create → join → preferences →
  recommendations → vote → finalize → results walkthrough over HTTP.

Statement coverage across `app/` is 91% (`coverage run -m pytest && coverage report --include="app/*"`).
Every push/PR also runs 4 automated CI checks (`.github/workflows/ci.yml`):
pytest, Flake8, Bandit, and Semgrep.

## Security notes

- Passwords are hashed with Werkzeug's `generate_password_hash` /
  `check_password_hash` (`app/services/auth_service.py`) — never stored
  or compared in plaintext.
- All POST forms carry a CSRF token (Flask-WTF `CSRFProtect`, wired up
  in `app/__init__.py`). Functional tests disable this in their test
  config (`WTF_CSRF_ENABLED: False`) since they post form data
  directly rather than rendering a page first — the standard Flask-WTF
  testing pattern.
- Session cookies are `HttpOnly`/`SameSite=Lax` with a 30-minute
  lifetime (NFR-04.5); `SESSION_COOKIE_SECURE` is auto-enabled when
  running on Render (or set it manually for any other HTTPS deployment).
- Register/login/join endpoints are rate-limited (10 attempts/minute,
  NFR-04.6) against credential guessing and invite-code brute-forcing.
- All SQL is parameterized (NFR-04.4) — see `app/repositories/`.
- The admin DB export/import routes (`app/admin_routes.py`) are
  disabled — and 404 as if they don't exist — unless
  `DINETOGETHER_ADMIN_TOKEN` is set in the environment.

## Deployment

The app is deployed on Render: https://dinetogether-k2hz.onrender.com/

Render's free tier runs each deploy in a fresh container with no
persistent disk, so anything written to `instance/dinetogether.sqlite`
at runtime — events, votes, whatever a live demo generates — is lost
on the next redeploy. The restaurant catalog is unaffected (it
re-imports automatically from the CSV on first boot), but any demo
data you want to keep across a redeploy needs to be pulled down first
and pushed back up after, using the admin routes:

```bash
# before pushing a new commit — save the live database
curl "https://dinetogether-k2hz.onrender.com/admin/export-db?token=$DINETOGETHER_ADMIN_TOKEN" -o backup.sqlite

# after the redeploy finishes — restore it
curl -X POST "https://dinetogether-k2hz.onrender.com/admin/import-db?token=$DINETOGETHER_ADMIN_TOKEN" \
  -F "db_file=@backup.sqlite"
```

`DINETOGETHER_ADMIN_TOKEN` must be set as a Render environment variable
(a long random value, never committed) for these routes to respond at
all.
