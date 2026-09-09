"""
Routes for Event Creation & Joining. Thin controllers only: parse the
request, call EventService, shape the response. No SQL and no
business rules live here.
"""
from __future__ import annotations

import json

from flask import Blueprint, render_template, request, session, redirect, url_for, flash, abort

from app import limiter
from app.db import get_db
from app.repositories.event_repository import EventRepository
from app.repositories.preference_repository import PreferenceRepository
from app.repositories.restaurant_repository import RestaurantRepository
from app.repositories.user_repository import User, UserRepository
from app.repositories.vote_repository import VoteRepository
from app.services import (
    auth_service,
    event_service,
    history_service,
    preference_service,
    recommendation_service,
    voting_service,
)
from app.services.validators import (
    ALLOWED_BUDGETS,
    ALLOWED_CUISINES,
    ALLOWED_DIETARY,
    ValidationError,
)

bp = Blueprint("main", __name__)


# The real Greater LA dataset stores cuisine as a raw phrase (e.g.
# "Korean barbecue restaurant"), never the short label an image was
# drawn for, so lookup must be substring-based like every other
# cuisine match in this app (see Restaurant.matches_cuisine).
_CUISINE_IMAGES = {
    "chinese": "images/chinese.png",
    "japanese": "images/japanese.png",
    "korean": "images/korean.png",
    "italian": "images/italian.png",
    "mexican": "images/mexican.png",
    "thai": "images/thai.png",
    "american": "images/american.png",
    "mediterranean": "images/mediterranean.png",
    "seafood": "images/seafood.png",
}


@bp.app_template_filter("cuisine_image")
def cuisine_image(cuisine: str) -> str:
    cuisine_lower = (cuisine or "").lower()
    for key, path in _CUISINE_IMAGES.items():
        if key in cuisine_lower:
            return path
    return "images/default.png"


def _repo() -> EventRepository:
    return EventRepository(get_db())


def _user_repo() -> UserRepository:
    return UserRepository(get_db())


def _pref_repo() -> PreferenceRepository:
    return PreferenceRepository(get_db())


def _restaurant_repo() -> RestaurantRepository:
    return RestaurantRepository(get_db())


def _vote_repo() -> VoteRepository:
    return VoteRepository(get_db())


def _current_user() -> User | None:
    user_id = session.get("user_id")
    if user_id is None:
        return None
    return _user_repo().get_by_id(user_id)


@bp.app_context_processor
def _inject_current_user():
    # Lets every template reference `current_user` (e.g. the header's
    # History/Log out links) without every route threading it through.
    return {"current_user": _current_user()}


def _require_session_event(event_id: int):
    """Shared guard for every event-scoped route: the caller's
    session must be tied to this exact event (FR-02 access control),
    and the event must still exist. Returns the Event or aborts.

    A logged-in user revisiting an event from their History page
    won't have this event as their current session event (that's
    whichever event they most recently created/joined), so before
    rejecting we check whether they're actually a participant of the
    requested event and, if so, re-bind the session to it."""
    if session.get("event_id") != event_id:
        user = _current_user()
        participant = _repo().get_participant_for_user(event_id, user.id) if user else None
        if participant is None:
            abort(403)
        _start_session_for(event_id, participant.id, participant.display_name)

    event = _repo().get_event_by_id(event_id)
    if event is None:
        abort(404)
    return event


@bp.get("/")
def home():
    return render_template("home.html")


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def register():
    if request.method == "GET":
        return render_template("register.html")

    try:
        result = auth_service.register(
            _user_repo(),
            request.form.get("username"),
            request.form.get("password"),
            request.form.get("display_name"),
        )
    except ValidationError as err:
        flash(err.message, "error")
        return render_template("register.html", field_error=err.field), 400
    except auth_service.UsernameAlreadyRegisteredError:
        flash("That username is already taken.", "error")
        return render_template("register.html", field_error="username"), 400

    _login_session_for(result.user)
    flash(f"Welcome, {result.user.display_name}!", "success")
    return redirect(url_for("main.home"))


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")  # NFR-04.6-style throttle against credential guessing
def login():
    if request.method == "GET":
        return render_template("login.html")

    try:
        user = auth_service.login(_user_repo(), request.form.get("username"), request.form.get("password"))
    except auth_service.InvalidCredentialsError:
        flash("Incorrect username or password.", "error")
        return render_template("login.html", field_error="username"), 400

    _login_session_for(user)
    flash(f"Welcome back, {user.display_name}!", "success")
    return redirect(url_for("main.home"))


@bp.post("/logout")
def logout():
    session.clear()
    flash("You've been logged out.", "success")
    return redirect(url_for("main.home"))


@bp.get("/history")
def history():
    user = _current_user()
    if user is None:
        return redirect(url_for("main.login"))

    entries = history_service.get_history_for_user(_repo(), _vote_repo(), _restaurant_repo(), user.id)
    return render_template("history.html", entries=entries)


@bp.route("/events/new", methods=["GET", "POST"])
def create_event():
    user = _current_user()
    if user is None:
        return redirect(url_for("main.login"))

    if request.method == "GET":
        return render_template("create_event.html")

    try:
        result = event_service.create_event(_repo(), request.form.get("name"), user)
    except ValidationError as err:
        flash(err.message, "error")
        return render_template("create_event.html", field_error=err.field), 400

    _start_session_for(
        result.event.id, participant_id=result.participant.id, display_name=result.participant.display_name
    )
    return render_template("event_created.html", event=result.event)


@bp.route("/events/join", methods=["GET", "POST"])
@limiter.limit("10 per minute")  # NFR-04.6
def join_event():
    user = _current_user()
    if user is None:
        return redirect(url_for("main.login"))

    if request.method == "GET":
        return render_template("join_event.html")

    raw_code = request.form.get("code", "")

    try:
        result = event_service.join_event(_repo(), _vote_repo(), raw_code, user)
    except ValidationError as err:
        # FR-02.2 / NFR-02.2: identify the invalid field, but never
        # reveal *why* a code failed (malformed vs. unknown look the
        # same to the caller).
        flash(err.message, "error")
        return render_template("join_event.html", field_error=err.field), 400
    except event_service.EventNotFoundError:
        flash("That invitation code isn't valid.", "error")
        return render_template("join_event.html", field_error="code"), 404
    except event_service.InviteCodeExpiredError:
        flash("This invitation code has expired.", "error")
        return render_template("join_event.html", field_error="code"), 404
    except event_service.EventAlreadyFinalizedError:
        flash("This event is already closed and no longer accepting new participants.", "error")
        return render_template("join_event.html", field_error="code"), 404

    _start_session_for(
        result.event.id, participant_id=result.participant.id, display_name=result.participant.display_name
    )
    return redirect(url_for("main.event_home", event_id=result.event.id))


@bp.get("/events/<int:event_id>")
def event_home(event_id: int):
    event = _require_session_event(event_id)
    participants = _repo().list_participants(event_id)
    finalized = _vote_repo().is_finalized(event_id)
    return render_template(
        "event_home.html",
        event=event,
        participants=participants,
        display_name=session.get("display_name"),
        finalized=finalized,
    )


@bp.route("/events/<int:event_id>/preferences", methods=["GET", "POST"])
def preferences(event_id: int):
    event = _require_session_event(event_id)
    participant_id = session["participant_id"]
    vote_repo = _vote_repo()

    if vote_repo.is_finalized(event_id):
        flash("This event's final decision has already been saved; preferences are locked.", "error")
        return redirect(url_for("main.results", event_id=event_id))

    if vote_repo.get_votes_for_participant(event_id, participant_id):
        flash("You've already voted; preferences are locked until the event is finalized.", "error")
        return redirect(url_for("main.waiting", event_id=event_id))

    existing = _pref_repo().get_for_participant(participant_id)

    if request.method == "GET":
        return render_template(
            "preferences.html",
            event=event,
            preference=existing,
            cuisines=ALLOWED_CUISINES,
            budgets=ALLOWED_BUDGETS.keys(),
            budgets_by_symbol=ALLOWED_BUDGETS,
            dietary_options=ALLOWED_DIETARY,
        )

    try:
        preference_service.submit_preferences(
            _pref_repo(),
            _vote_repo(),
            event_id,
            participant_id,
            request.form.getlist("cuisine"),
            request.form.getlist("budget"),
            request.form.getlist("dietary"),
            request.form.get("max_distance"),
            request.form.get("min_rating"),
        )
    except ValidationError as err:
        flash(err.message, "error")
        return (
            render_template(
                "preferences.html",
                event=event,
                preference=existing,
                cuisines=ALLOWED_CUISINES,
                budgets=ALLOWED_BUDGETS.keys(),
                budgets_by_symbol=ALLOWED_BUDGETS,
                dietary_options=ALLOWED_DIETARY,
                field_error=err.field,
            ),
            400,
        )
    except preference_service.EventFinalizedError:
        flash("This event's final decision has already been saved; preferences are locked.", "error")
        return redirect(url_for("main.results", event_id=event_id))
    except preference_service.AlreadyVotedError:
        flash("You've already voted; preferences are locked until the event is finalized.", "error")
        return redirect(url_for("main.waiting", event_id=event_id))

    flash("Preferences saved.", "success")
    return redirect(url_for("main.recommendations", event_id=event_id))


@bp.get("/events/<int:event_id>/recommendations")
def recommendations(event_id: int):
    event = _require_session_event(event_id)
    vote_repo = _vote_repo()

    if vote_repo.is_finalized(event_id):
        return redirect(url_for("main.results", event_id=event_id))

    is_creator = _repo().is_creator(event_id, session["user_id"])
    my_votes = vote_repo.get_votes_for_participant(event_id, session["participant_id"])

    # Once a regular participant has voted there is nothing left for
    # them to do here — send them to the waiting page instead. The
    # host stays, since Finalize lives on this page regardless of
    # whether the host has personally voted.
    if my_votes and not is_creator:
        return redirect(url_for("main.waiting", event_id=event_id))

    result = recommendation_service.get_recommendations(_pref_repo(), _restaurant_repo(), event_id)
    return render_template(
        "recommendations.html",
        event=event,
        result=result,
        my_vote_ids={v.restaurant_id for v in my_votes},
        finalized=False,
        is_creator=is_creator,
    )


@bp.route("/events/<int:event_id>/vote", methods=["GET", "POST"])
def vote(event_id: int):
    _require_session_event(event_id)
    pref_repo, restaurant_repo, vote_repo = _pref_repo(), _restaurant_repo(), _vote_repo()

    if request.method == "GET":
        # Voting now happens inline on the recommendations page.
        return redirect(url_for("main.recommendations", event_id=event_id))

    raw_restaurant_ids = request.form.getlist("restaurant_id")
    try:
        restaurant_ids = [int(raw_id) for raw_id in raw_restaurant_ids]
        voting_service.cast_votes(
            pref_repo, restaurant_repo, vote_repo, event_id, session["participant_id"], restaurant_ids
        )
    except (ValueError, voting_service.RestaurantNotOnShortlistError):
        flash("Choose at least one of the listed restaurants to vote for.", "error")
        return redirect(url_for("main.recommendations", event_id=event_id))
    except voting_service.EventFinalizedError:
        flash("Voting is closed; the final decision has already been saved.", "error")
        return redirect(url_for("main.results", event_id=event_id))

    flash("Your vote has been recorded.", "success")
    # The host stays on the recommendations page (Finalize lives
    # there); everyone else has nothing left to do but wait.
    if _repo().is_creator(event_id, session["user_id"]):
        return redirect(url_for("main.recommendations", event_id=event_id))
    return redirect(url_for("main.waiting", event_id=event_id))


@bp.get("/events/<int:event_id>/waiting")
def waiting(event_id: int):
    event = _require_session_event(event_id)
    vote_repo = _vote_repo()

    if vote_repo.is_finalized(event_id):
        return redirect(url_for("main.results", event_id=event_id))

    participant_id = session["participant_id"]
    is_creator = _repo().is_creator(event_id, session["user_id"])
    my_votes = vote_repo.get_votes_for_participant(event_id, participant_id)

    # Nothing to wait for yet — send a participant who hasn't voted
    # back to actually vote. The host may still land here to finalize.
    if not my_votes and not is_creator:
        return redirect(url_for("main.recommendations", event_id=event_id))

    restaurant_repo = _restaurant_repo()
    my_restaurants = [restaurant_repo.get_by_id(v.restaurant_id) for v in my_votes]

    return render_template(
        "waiting.html",
        event=event,
        preference=_pref_repo().get_for_participant(participant_id),
        my_restaurants=my_restaurants,
        is_creator=is_creator,
        budgets_by_symbol=ALLOWED_BUDGETS,
    )


@bp.post("/events/<int:event_id>/finalize")
def finalize(event_id: int):
    _require_session_event(event_id)
    if not _repo().is_creator(event_id, session["user_id"]):
        abort(403)

    pref_repo, restaurant_repo, vote_repo = _pref_repo(), _restaurant_repo(), _vote_repo()

    try:
        voting_service.finalize(pref_repo, restaurant_repo, vote_repo, event_id)
    except voting_service.NoShortlistError:
        flash("At least one vote is needed before results can be finalized.", "error")
        return redirect(url_for("main.recommendations", event_id=event_id))

    return redirect(url_for("main.results", event_id=event_id))


@bp.get("/events/<int:event_id>/results")
def results(event_id: int):
    event = _require_session_event(event_id)
    restaurant_repo, vote_repo = _restaurant_repo(), _vote_repo()
    result = voting_service.get_results(vote_repo, event_id)

    top_choices = []
    vote_totals = {}
    if result:
        vote_totals = json.loads(result.vote_totals)
        if vote_totals:
            top_count = max(vote_totals.values())
            restaurants_by_name = {r.name: r for r in restaurant_repo.list_all()}
            # Every restaurant tied for the most votes (usually just
            # one) — vote_totals already carries every restaurant's
            # count, so no separate winners table is needed.
            top_choices = [
                (restaurants_by_name[name], count)
                for name, count in vote_totals.items()
                if count == top_count and name in restaurants_by_name
            ]

    return render_template(
        "results.html", event=event, result=result, top_choices=top_choices, vote_totals=vote_totals
    )


def _login_session_for(user: User) -> None:
    """This is the point where session privilege actually changes
    (anonymous -> authenticated): clear and repopulate so a pre-login
    session id is never reused post-login (session fixation) — the
    same fix previously applied at event-join time (code-review
    Finding 3), now applied at the boundary that actually matters
    now that accounts exist."""
    session.clear()
    session.permanent = True
    session["user_id"] = user.id
    session["username"] = user.username
    session["user_display_name"] = user.display_name


def _start_session_for(event_id: int, participant_id: int, display_name: str) -> None:
    """Attaches event-scoped state to the caller's already-authenticated
    session. Must not clear the session — that would log the user out
    of their account mid-flow."""
    session.permanent = True
    session["event_id"] = event_id
    session["participant_id"] = participant_id
    session["display_name"] = display_name
