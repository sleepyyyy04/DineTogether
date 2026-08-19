def _register(client, username="alex", display_name="Alex", password="password123"):
    return client.post(
        "/register",
        data={"username": username, "display_name": display_name, "password": password},
        follow_redirects=True,
    )


def test_home_page_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"DineTogether" in resp.data


def test_create_event_requires_login(client):
    resp = client.post("/events/new", data={"name": "Friday Team Dinner"})
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_create_event_end_to_end(client):
    _register(client)
    resp = client.post("/events/new", data={"name": "Friday Team Dinner"})
    assert resp.status_code == 200
    assert b"Share this invitation code" in resp.data


def test_create_event_blank_name_returns_400(client):
    _register(client)
    resp = client.post("/events/new", data={"name": "   "})
    assert resp.status_code == 400


def test_join_event_unknown_code_returns_404(client):
    _register(client)
    resp = client.post("/events/join", data={"code": "ZZZZ"})
    assert resp.status_code == 404


def test_full_create_then_join_flow_sets_session_and_shows_event(client):
    _register(client, username="alex", display_name="Alex")
    create_resp = client.post("/events/new", data={"name": "Friday Team Dinner"})
    # Extract the invite code straight off the confirmation page.
    html = create_resp.get_data(as_text=True)
    code = html.split("<strong>")[2].split("</strong>")[0]

    with client.session_transaction() as sess:
        sess.clear()  # simulate a second browser joining, not the organizer's

    _register(client, username="ben", display_name="Ben")
    join_resp = client.post(
        "/events/join",
        data={"code": code},
        follow_redirects=True,
    )
    assert join_resp.status_code == 200
    assert b"Ben" in join_resp.data


def test_event_home_rejects_session_for_a_different_event(client):
    _register(client)
    client.post("/events/new", data={"name": "Event A"})
    with client.session_transaction() as sess:
        real_event_id = sess["event_id"]

    resp = client.get(f"/events/{real_event_id + 999}")
    assert resp.status_code == 403


def test_full_group_flow_preferences_recommendations_vote_and_finalize(client, db):
    """End-to-end walk through FR-03/04/05: two participants submit
    preferences, agree on the same restaurant, and finalize a
    non-tied result."""
    from app.repositories.event_repository import EventRepository
    from app.repositories.preference_repository import PreferenceRepository
    from app.repositories.restaurant_repository import RestaurantRepository
    from app.services.recommendation_service import get_recommendations

    _register(client, username="alex", display_name="Alex")
    create_resp = client.post("/events/new", data={"name": "Group Dinner"})
    assert create_resp.status_code == 200
    with client.session_transaction() as sess:
        event_id = sess["event_id"]
        organizer_participant_id = sess["participant_id"]

    invite_code = EventRepository(db).get_event_by_id(event_id).invite_code

    # Wide-open preferences so the group is guaranteed at least one match.
    pref_payload = {
        "cuisine": ["Italian"],
        "budget": ["$", "$$", "$$$", "$$$$"],
        "dietary": ["none"],
        "max_distance": "25",
    }

    resp = client.post(f"/events/{event_id}/preferences", data=pref_payload, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Preferences saved" in resp.data

    with client.session_transaction() as sess:
        sess.clear()  # simulate a second browser joining, not the organizer's

    _register(client, username="ben", display_name="Ben")
    join_resp = client.post("/events/join", data={"code": invite_code}, follow_redirects=True)
    assert join_resp.status_code == 200
    with client.session_transaction() as sess:
        ben_participant_id = sess["participant_id"]
        assert ben_participant_id != organizer_participant_id

    resp = client.post(f"/events/{event_id}/preferences", data=pref_payload, follow_redirects=True)
    assert resp.status_code == 200

    # Compute the deterministic top choice directly against the same DB.
    rec = get_recommendations(PreferenceRepository(db), RestaurantRepository(db), event_id)
    assert rec.restaurants, "wide-open preferences should always match something"
    top_choice = rec.restaurants[0]

    ben_vote = client.post(
        f"/events/{event_id}/vote", data={"restaurant_id": top_choice.id}, follow_redirects=True
    )
    assert ben_vote.status_code == 200
    assert b"vote has been recorded" in ben_vote.data

    # Switch back to the organizer's account to cast the second vote
    # (accounts are the source of identity now, so this means logging
    # back in as Alex rather than hand-editing the session).
    with client.session_transaction() as sess:
        sess.clear()
    client.post("/login", data={"username": "alex", "password": "password123"})
    with client.session_transaction() as sess:
        sess["event_id"] = event_id
        sess["participant_id"] = organizer_participant_id
        sess["display_name"] = "Alex"

    organizer_vote = client.post(
        f"/events/{event_id}/vote", data={"restaurant_id": top_choice.id}, follow_redirects=True
    )
    assert organizer_vote.status_code == 200

    finalize_resp = client.post(f"/events/{event_id}/finalize", follow_redirects=True)
    assert finalize_resp.status_code == 200

    results_resp = client.get(f"/events/{event_id}/results")
    assert results_resp.status_code == 200
    body = results_resp.get_data(as_text=True)
    assert top_choice.name in body
    assert "2 votes" in body

    # Preferences are now locked (FR-03.3 boundary).
    locked_resp = client.post(
        f"/events/{event_id}/preferences", data=pref_payload, follow_redirects=True
    )
    assert locked_resp.status_code == 200
    assert b"already been saved" in locked_resp.data


def test_join_endpoint_rate_limits_after_ten_attempts_per_minute(client):
    """NFR-04.6 / code-review Finding 2. The 11th attempt inside the
    same minute must be rejected regardless of whether the code is
    valid, since the point is to slow down code-guessing."""
    _register(client)
    for _ in range(10):
        resp = client.post("/events/join", data={"code": "ZZZZ"})
        assert resp.status_code in (404, 400)

    eleventh = client.post("/events/join", data={"code": "ZZZZ"})
    assert eleventh.status_code == 429
