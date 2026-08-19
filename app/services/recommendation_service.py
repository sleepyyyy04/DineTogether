"""
Application-logic layer for Restaurant Recommendation (FR-04).

Filtering (FR-04.3) is an intersection of every participant's hard
constraints: a restaurant only survives if it satisfies EVERY
participant's accepted budget levels, dietary needs, and distance
ceiling — those are the three criteria FR-04.3 names. Cuisine is
deliberately NOT a hard filter: a group with mixed cuisine tastes
would otherwise always end up with zero matches. Instead cuisine
preferences are tallied and used only to rank survivors (FR-04.4),
alongside rating and distance.

If nothing survives the filter, FR-04.6 (Should) allows showing a
clearly labeled fallback of the closest available options instead of
an empty list.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from app.repositories.preference_repository import Preference, PreferenceRepository
from app.repositories.restaurant_repository import Restaurant, RestaurantRepository

_FALLBACK_SIZE = 5
_SHORTLIST_SIZE = 20  # FR-05.1 calls this a "shortlist" — cap it to a votable size.


@dataclass
class RecommendationResult:
    restaurants: list[Restaurant]
    has_preferences: bool
    is_fallback: bool


def _satisfies_all(restaurant: Restaurant, prefs: list[Preference]) -> bool:
    for pref in prefs:
        if restaurant.price_level not in pref.budget_levels:
            return False
        if restaurant.distance_mi > pref.max_distance_mi:
            return False
        if any(d != "none" and not restaurant.supports(d) for d in pref.dietary):
            return False
    return True


def _rank_key(restaurant: Restaurant, cuisine_votes: Counter):
    # Deterministic, repeatable order (FR-04.4): best cuisine match
    # first, then highest rating, then closest, then alphabetical as
    # a final tie-break so the order never depends on DB row order.
    return (
        -cuisine_votes.get(restaurant.cuisine, 0),
        -restaurant.rating,
        restaurant.distance_mi,
        restaurant.name,
    )


def get_recommendations(
    pref_repo: PreferenceRepository,
    restaurant_repo: RestaurantRepository,
    event_id: int,
) -> RecommendationResult:
    prefs = pref_repo.list_for_event(event_id)
    if not prefs:
        return RecommendationResult(restaurants=[], has_preferences=False, is_fallback=False)

    all_restaurants = restaurant_repo.list_all()
    cuisine_votes = Counter(c for p in prefs for c in p.cuisines if c != "any")

    survivors = [r for r in all_restaurants if _satisfies_all(r, prefs)]

    if survivors:
        ranked = sorted(survivors, key=lambda r: _rank_key(r, cuisine_votes))[:_SHORTLIST_SIZE]
        return RecommendationResult(restaurants=ranked, has_preferences=True, is_fallback=False)

    # FR-04.6: no exact match — fall back to the closest available
    # options, clearly labeled by the caller, ignoring the failed
    # budget/dietary/distance constraints entirely.
    fallback = sorted(
        all_restaurants,
        key=lambda r: (-r.rating, r.distance_mi, r.name),
    )[:_FALLBACK_SIZE]
    return RecommendationResult(restaurants=fallback, has_preferences=True, is_fallback=True)
