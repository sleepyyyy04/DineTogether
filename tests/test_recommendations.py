"""
FR-04 filtering/ranking/fallback logic, tested against small hand-built
restaurant/preference fixtures (fakes, not the real repositories) so
assertions are precise and independent of the CSV dataset's contents.
"""
from app.repositories.preference_repository import Preference
from app.repositories.restaurant_repository import Restaurant
from app.services.recommendation_service import get_recommendations


class FakePreferenceRepo:
    def __init__(self, prefs):
        self._prefs = prefs

    def list_for_event(self, event_id):
        return self._prefs


class FakeRestaurantRepo:
    def __init__(self, restaurants):
        self._restaurants = restaurants

    def list_all(self):
        return self._restaurants


def _pref(participant_id, cuisines, budget_levels, dietary, max_distance_mi, min_rating=None):
    return Preference(
        id=participant_id,
        event_id=1,
        participant_id=participant_id,
        cuisines=cuisines,
        budget_levels=budget_levels,
        dietary=dietary,
        max_distance_mi=max_distance_mi,
        min_rating=min_rating,
    )


def _restaurant(id, name, cuisine, price_level, dietary_tags, distance_mi, rating):
    return Restaurant(
        id=id,
        name=name,
        cuisine=cuisine,
        price_level=price_level,
        dietary_tags=dietary_tags,
        distance_mi=distance_mi,
        rating=rating,
    )


def test_no_preferences_yet_returns_empty_without_fallback():
    result = get_recommendations(FakePreferenceRepo([]), FakeRestaurantRepo([]), event_id=1)
    assert result.has_preferences is False
    assert result.restaurants == []
    assert result.is_fallback is False


def test_filter_removes_restaurants_that_conflict_with_budget_dietary_or_distance():
    restaurants = [
        _restaurant(1, "Cheap Italian", "Italian", price_level=2, dietary_tags=[], distance_mi=3.0, rating=4.5),
        _restaurant(2, "Pricey Thai", "Thai", price_level=4, dietary_tags=["vegetarian"], distance_mi=10.0, rating=4.0),
        _restaurant(3, "Budget Italian", "Italian", price_level=1, dietary_tags=["vegan"], distance_mi=1.0, rating=3.5),
        _restaurant(4, "Far Mexican", "Mexican", price_level=3, dietary_tags=[], distance_mi=20.0, rating=5.0),
    ]
    prefs = [
        _pref(1, cuisines=["Italian"], budget_levels=[1, 2], dietary=["none"], max_distance_mi=5.0),
        _pref(2, cuisines=["Thai"], budget_levels=[1, 2], dietary=["none"], max_distance_mi=5.0),
    ]

    result = get_recommendations(FakePreferenceRepo(prefs), FakeRestaurantRepo(restaurants), event_id=1)

    assert result.is_fallback is False
    survivor_ids = {r.id for r in result.restaurants}
    assert survivor_ids == {1, 3}  # #2 fails on budget, #4 fails on budget and distance


def test_budget_levels_accept_any_selected_price_level_not_just_a_ceiling():
    """Multi-select budget means the restaurant's price just needs to be
    one of the checked levels, not <= a single maximum."""
    restaurants = [
        _restaurant(1, "Cheap", "Italian", price_level=1, dietary_tags=[], distance_mi=1.0, rating=4.0),
        _restaurant(2, "Mid", "Italian", price_level=2, dietary_tags=[], distance_mi=1.0, rating=4.0),
        _restaurant(3, "Pricey", "Italian", price_level=4, dietary_tags=[], distance_mi=1.0, rating=4.0),
    ]
    # Selected $ and $$$$ but not $$ or $$$ — a non-contiguous set.
    prefs = [_pref(1, cuisines=["any"], budget_levels=[1, 4], dietary=["none"], max_distance_mi=25.0)]

    result = get_recommendations(FakePreferenceRepo(prefs), FakeRestaurantRepo(restaurants), event_id=1)

    assert {r.id for r in result.restaurants} == {1, 3}


def test_dietary_requirement_excludes_restaurants_without_the_tag():
    restaurants = [
        _restaurant(1, "No Veg Options", "Italian", price_level=2, dietary_tags=[], distance_mi=2.0, rating=4.5),
        _restaurant(2, "Veg Friendly", "Italian", price_level=2, dietary_tags=["vegetarian"], distance_mi=2.0, rating=4.0),
    ]
    prefs = [_pref(1, cuisines=["Italian"], budget_levels=[1, 2, 3, 4], dietary=["vegetarian"], max_distance_mi=25.0)]

    result = get_recommendations(FakePreferenceRepo(prefs), FakeRestaurantRepo(restaurants), event_id=1)

    assert [r.id for r in result.restaurants] == [2]


def test_multiple_dietary_requirements_must_all_be_supported():
    restaurants = [
        _restaurant(1, "Veg Only", "Italian", price_level=2, dietary_tags=["vegetarian"], distance_mi=2.0, rating=4.5),
        _restaurant(
            2, "Veg and Gluten Free", "Italian", price_level=2,
            dietary_tags=["vegetarian", "gluten_free"], distance_mi=2.0, rating=4.0,
        ),
    ]
    prefs = [
        _pref(
            1, cuisines=["Italian"], budget_levels=[1, 2, 3, 4],
            dietary=["vegetarian", "gluten_free"], max_distance_mi=25.0,
        )
    ]

    result = get_recommendations(FakePreferenceRepo(prefs), FakeRestaurantRepo(restaurants), event_id=1)

    assert [r.id for r in result.restaurants] == [2]


def test_min_rating_is_optional_and_excludes_restaurants_below_it_when_set():
    restaurants = [
        _restaurant(1, "Lower Rated", "Italian", price_level=2, dietary_tags=[], distance_mi=2.0, rating=3.5),
        _restaurant(2, "Higher Rated", "Italian", price_level=2, dietary_tags=[], distance_mi=2.0, rating=4.5),
    ]
    prefs = [
        _pref(
            1, cuisines=["Italian"], budget_levels=[1, 2, 3, 4],
            dietary=["none"], max_distance_mi=25.0, min_rating=4.0,
        )
    ]

    result = get_recommendations(FakePreferenceRepo(prefs), FakeRestaurantRepo(restaurants), event_id=1)

    assert [r.id for r in result.restaurants] == [2]


def test_min_rating_left_unset_places_no_constraint():
    restaurants = [
        _restaurant(1, "Lower Rated", "Italian", price_level=2, dietary_tags=[], distance_mi=2.0, rating=3.5),
        _restaurant(2, "Higher Rated", "Italian", price_level=2, dietary_tags=[], distance_mi=2.0, rating=4.5),
    ]
    prefs = [_pref(1, cuisines=["Italian"], budget_levels=[1, 2, 3, 4], dietary=["none"], max_distance_mi=25.0)]

    result = get_recommendations(FakePreferenceRepo(prefs), FakeRestaurantRepo(restaurants), event_id=1)

    assert {r.id for r in result.restaurants} == {1, 2}


def test_ranking_prefers_more_cuisine_matches_then_higher_rating_deterministically():
    restaurants = [
        _restaurant(1, "R1", "Italian", price_level=2, dietary_tags=[], distance_mi=3.0, rating=4.5),
        _restaurant(2, "R2", "Italian", price_level=2, dietary_tags=[], distance_mi=1.0, rating=3.5),
    ]
    prefs = [
        _pref(1, cuisines=["Italian"], budget_levels=[1, 2], dietary=["none"], max_distance_mi=5.0),
        _pref(2, cuisines=["Thai"], budget_levels=[1, 2], dietary=["none"], max_distance_mi=5.0),
    ]

    first_run = get_recommendations(FakePreferenceRepo(prefs), FakeRestaurantRepo(restaurants), event_id=1)
    second_run = get_recommendations(FakePreferenceRepo(prefs), FakeRestaurantRepo(restaurants), event_id=1)

    # Same cuisine-match count for both (1 vote each): higher rating breaks the tie.
    assert [r.id for r in first_run.restaurants] == [1, 2]
    assert [r.id for r in first_run.restaurants] == [r.id for r in second_run.restaurants]


def test_no_match_falls_back_to_closest_available_options():
    restaurants = [
        _restaurant(1, "Far Fancy", "Italian", price_level=4, dietary_tags=[], distance_mi=15.0, rating=4.8),
        _restaurant(2, "Closer Cheap", "Thai", price_level=1, dietary_tags=[], distance_mi=2.0, rating=3.9),
    ]
    # Impossibly tight budget: nothing can survive the filter.
    prefs = [_pref(1, cuisines=["Italian"], budget_levels=[1], dietary=["vegan"], max_distance_mi=1.0)]

    result = get_recommendations(FakePreferenceRepo(prefs), FakeRestaurantRepo(restaurants), event_id=1)

    assert result.is_fallback is True
    assert len(result.restaurants) == 2
    # Fallback ignores the failed constraints and ranks by rating/distance instead.
    assert result.restaurants[0].id == 1
