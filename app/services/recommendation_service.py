"""
Application-logic layer for Restaurant Recommendation (FR-04).

Filtering (FR-04.3) is an intersection of every participant's hard
constraints: a restaurant only survives if it satisfies EVERY
participant's accepted budget levels, dietary needs, distance
ceiling, and minimum rating (where set — it's optional).

Cuisine is deliberately NOT a hard filter. A group with mixed cuisine
preferences could otherwise easily end up with no restaurants.

Cuisine preferences are instead used for ranking. Cuisine and dietary
matching use case-insensitive substring detection because the real
Greater LA dataset contains category strings such as:

    "Chinese restaurant"
    "Mexican restaurant"
    "Vegan restaurant"

rather than the application's shorter preference values such as:

    "Chinese"
    "Mexican"
    "vegan"
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from app.repositories.preference_repository import (
    Preference,
    PreferenceRepository,
)
from app.repositories.restaurant_repository import (
    Restaurant,
    RestaurantRepository,
)


_FALLBACK_SIZE = 5


@dataclass
class RecommendationResult:
    restaurants: list[Restaurant]
    has_preferences: bool
    is_fallback: bool


def _satisfies_all(
    restaurant: Restaurant,
    prefs: list[Preference],
) -> bool:
    """
    Check every participant's hard constraints.

    A restaurant must satisfy:
    - accepted price level
    - maximum distance
    - every required dietary preference
    - minimum rating, for participants who set one (it's optional —
      a participant who didn't set one places no rating constraint)

    Cuisine is not a hard filter.
    """
    for pref in prefs:
        if restaurant.price_level not in pref.budget_levels:
            return False

        if restaurant.distance_mi > pref.max_distance_mi:
            return False

        if pref.min_rating is not None and restaurant.rating < pref.min_rating:
            return False

        for dietary in pref.dietary:
            if dietary == "none":
                continue

            if not restaurant.supports(dietary):
                return False

    return True


def _cuisine_match_score(
    restaurant: Restaurant,
    cuisine_votes: Counter,
) -> int:
    """
    Count how many participant cuisine votes match this restaurant.

    Matching is based on substring detection through
    Restaurant.matches_cuisine().

    Example:

        restaurant categories:
            "Chinese restaurant, Asian restaurant"

        participant preference:
            "Chinese"

    This counts as a match.
    """
    score = 0

    for cuisine, vote_count in cuisine_votes.items():
        if restaurant.matches_cuisine(cuisine):
            score += vote_count

    return score


def _rank_key(
    restaurant: Restaurant,
    cuisine_votes: Counter,
):
    """
    Deterministic recommendation ranking.

    Priority:
    1. Most cuisine preference matches
    2. Highest rating
    3. Closest to Sofia University
    4. Alphabetical name
    """
    cuisine_score = _cuisine_match_score(
        restaurant,
        cuisine_votes,
    )

    return (
        -cuisine_score,
        -restaurant.rating,
        restaurant.distance_mi,
        restaurant.name.lower(),
    )


def get_recommendations(
    pref_repo: PreferenceRepository,
    restaurant_repo: RestaurantRepository,
    event_id: int,
) -> RecommendationResult:
    prefs = pref_repo.list_for_event(event_id)

    if not prefs:
        return RecommendationResult(
            restaurants=[],
            has_preferences=False,
            is_fallback=False,
        )

    all_restaurants = restaurant_repo.list_all()

    cuisine_votes = Counter(
        cuisine
        for pref in prefs
        for cuisine in pref.cuisines
        if cuisine.lower() != "any"
    )

    survivors = [
        restaurant
        for restaurant in all_restaurants
        if _satisfies_all(restaurant, prefs)
    ]

    if survivors:
        ranked = sorted(
            survivors,
            key=lambda restaurant: _rank_key(
                restaurant,
                cuisine_votes,
            ),
        )

        return RecommendationResult(
            restaurants=ranked,
            has_preferences=True,
            is_fallback=False,
        )

    # FR-04.6 fallback:
    #
    # If every restaurant was eliminated by the group's hard
    # constraints, return the highest-rated nearby alternatives.
    #
    # Failed budget, dietary, and distance constraints are ignored in
    # fallback mode.
    fallback = sorted(
        all_restaurants,
        key=lambda restaurant: (
            -restaurant.rating,
            restaurant.distance_mi,
            restaurant.name.lower(),
        ),
    )[:_FALLBACK_SIZE]

    return RecommendationResult(
        restaurants=fallback,
        has_preferences=True,
        is_fallback=True,
    )
