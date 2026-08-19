# DineTogether

DineTogether is the full MVP described in the SRS: **Create Event**,
**Join Event**, **Preference Submission**, **Restaurant
Recommendation**, and **Voting & Result Management** (FR-01 through
FR-05), built as a Flask monolith with SQLite, per ADR-0001.

The organizer is added as a participant at creation time (so they can
also submit preferences and vote, per SRS 2.3), and restaurant data is
a static demo CSV (`app/data/restaurants.csv`, 120 rows across 10
cuisines) imported into SQLite once, the first time the app starts.

## Project layout

```
dinetogether/
  app/
    __init__.py                    # application factory (session, CSRF, rate limiting)
    db.py                          # SQLite connection + schema + startup CSV import
    routes.py                      # HTTP routes (thin controllers)
    data/
      restaurants.csv              # static demo dataset (DC-03/DC-04)
    services/
      validators.py                # shared field validation
      event_service.py             # FR-01/FR-02: create_event, join_event
      preference_service.py        # FR-03: submit_preferences
      recommendation_service.py    # FR-04: filter, rank, no-match fallback
      voting_service.py            # FR-05: cast_vote, finalize, get_results
      restaurant_import.py         # loads the CSV into SQLite once
    repositories/
      event_repository.py          # events + participants SQL
      preference_repository.py     # preferences SQL
      restaurant_repository.py     # restaurants SQL (read-only)
      vote_repository.py           # votes + results SQL
    templates/                     # server-rendered HTML (base.html + one per page)
    static/
      style.css                    # shared styling (cards, buttons, restaurant list)
  tests/
    conftest.py
    test_event_creation.py
    test_event_joining.py
    test_preferences.py
    test_recommendations.py
    test_voting.py
    test_routes.py
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
`app/db.py`, which also imports `app/data/restaurants.csv` the first
time `restaurants` is empty), so you normally don't need a separate
step. `flask init-db` also exists as an explicit CLI command:

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

- **Create an event** as the organizer → get a 4-character invitation code.
- **Join an event** → enter the code + a display name (no account).
- **Submit preferences** (cuisine, budget, dietary, max distance) — each
  participant, including the organizer, has one current preference set.
- **View recommendations** — a rule-based ranked shortlist filtered by
  the whole group's budget/dietary/distance constraints; if nothing
  satisfies everyone, a clearly labeled fallback of the closest
  available options is shown instead of an empty list.
- **Vote** for one restaurant on the shortlist (re-voting replaces your
  previous vote) and **finalize** once the group is ready.
- **View results** — the saved final restaurant and vote totals, or a
  tie notice if no restaurant has the most votes. Once finalized,
  preference edits and further votes are locked.

## 6. Run the tests

```bash
python -m pytest -v
```

All 43 tests should pass. They cover:

- valid create/join flows, plus organizer-as-participant behavior,
- FR-01.3 / FR-02.2 rejection of blank, over-length, malformed, and
  unknown input,
- the invitation-code collision fix (code-review Finding 1),
- session handling after join (Finding 3),
- the join-endpoint rate limit, 10 attempts/minute (NFR-04.6, Finding 2),
- FR-03 preference validation, edit-replaces-previous, and the
  lock-after-finalization boundary,
- FR-04 filtering (budget/dietary/distance intersection across the
  group), deterministic ranking, and the no-match fallback,
- FR-05 vote casting/replacement, tie vs. clear-winner finalization,
  and rejecting votes/edits once results are saved,
- a full create → join → preferences → recommendations → vote →
  finalize → results walkthrough over HTTP.

## Security notes

- All POST forms carry a CSRF token (Flask-WTF `CSRFProtect`, wired up
  in `app/__init__.py`). Functional tests disable this in their test
  config (`WTF_CSRF_ENABLED: False`) since they post form data
  directly rather than rendering a page first — the standard Flask-WTF
  testing pattern.
- Session cookies are `HttpOnly`/`SameSite=Lax` with a 30-minute
  lifetime (NFR-04.5); flip `SESSION_COOKIE_SECURE` on for any
  HTTPS deployment.
- All SQL is parameterized (NFR-04.4) — see `app/repositories/`.
