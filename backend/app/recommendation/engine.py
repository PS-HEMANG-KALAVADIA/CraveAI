from typing import List, Dict, Any
from .models import RankedRestaurant, ScoreBreakdown, RankingWeights
from .scorer import DeterministicScorer

class RecommendationEngine:
    """Intelligent intermediate layer to rank restaurants deterministically."""
    
    def __init__(self):
        self.scorer = DeterministicScorer()
        
    def _adjust_weights_from_intent(self, user_message: str) -> RankingWeights:
        """Adjust baseline weights dynamically based on user intent."""
        weights = RankingWeights() # Defaults
        
        msg = user_message.lower()
        
        # "Find the best..." -> increase rating/food match
        if "best" in msg or "top" in msg:
            weights.rating = 0.40
            weights.food_match = 0.40
            weights.distance = 0.10
            weights.budget_fit = 0.10
            
        # "Find something close..." -> increase distance weight
        elif "close" in msg or "nearby" in msg:
            weights.distance = 0.40
            weights.rating = 0.20
            weights.food_match = 0.30
            weights.budget_fit = 0.10
            
        # "cheap food" or "I have $X" -> increase budget fit
        elif "cheap" in msg or "budget" in msg or "₹" in msg or "rs" in msg:
            weights.budget_fit = 0.40
            weights.distance = 0.20
            weights.rating = 0.20
            weights.food_match = 0.20
            
        return weights

    def rank(
        self, 
        restaurants: List[Dict[str, Any]], 
        user_message: str, 
        tool_args: Dict[str, Any], 
        top_k: int = 5
    ) -> List[RankedRestaurant]:
        """Rank a list of raw restaurants."""
        
        weights = self._adjust_weights_from_intent(user_message)
        query = tool_args.get("query")
        price_tier = tool_args.get("price_tier")
        radius_arg = float(tool_args.get("radius_meters", 15000.0))
        max_dist_in_batch = max(
            (self.scorer.extract_distance_meters(r) or 0.0 for r in restaurants),
            default=0.0
        )
        effective_radius = max(radius_arg, 15000.0, max_dist_in_batch)
        
        ranked_list = []
        
        for r in restaurants:
            # Ensure distance_meters is properly extracted and normalized on restaurant dict
            dist_m = self.scorer.extract_distance_meters(r)
            if dist_m is not None:
                r["distance_meters"] = dist_m

            # Calculate raw scores
            food_score = self.scorer.score_food_match(r, query)
            rating_score = self.scorer.score_rating(r)
            dist_score = self.scorer.score_distance(r, effective_radius)
            budget_score = self.scorer.score_budget(r, price_tier)
            
            # Apply weights
            weighted_score = (
                (food_score * weights.food_match) +
                (rating_score * weights.rating) +
                (dist_score * weights.distance) +
                (budget_score * weights.budget_fit)
            )

            # Availability adjustment
            is_closed = r.get("is_closed", False)
            if is_closed:
                final_score = max(0.0, weighted_score - 20.0)
            else:
                final_score = weighted_score
            
            # Match category & metadata
            match_cat = r.get("match_category", "unverified")
            matched_items = r.get("matched_items", [])
            match_reason = r.get("match_reason", "")
            if not match_reason:
                if match_cat == "confirmed":
                    match_reason = "Confirmed menu match for requested dish."
                elif match_cat == "possible":
                    match_reason = "Possible match based on restaurant categories, but dish unverified on menu."
                else:
                    match_reason = "No relevant menu evidence available."

            dish_avail = r.get("dish_availability")
            if not dish_avail:
                if match_cat == "confirmed":
                    if matched_items and all(it.get("is_available") is False for it in matched_items):
                        dish_avail = "unavailable"
                    else:
                        dish_avail = "confirmed"
                elif match_cat == "possible":
                    dish_avail = "unavailable" if query else "unverified"
                else:
                    if "menu availability could not be verified" in match_reason.lower() or "unverified" in match_reason.lower():
                        dish_avail = "unverified"
                    else:
                        dish_avail = "unavailable"

            # If a specific food query was searched, unverified/possible restaurants must not display deceptively high scores
            if query and query.strip().lower() not in ("food", "restaurant", "restaurants") and match_cat in ("unverified", "possible"):
                final_score = round(min(final_score * 0.45, 35.0), 1)

            breakdown = ScoreBreakdown(
                food_match=round(food_score, 1),
                rating=round(rating_score, 1),
                distance=round(dist_score, 1),
                budget_fit=round(budget_score, 1),
                total_score=round(final_score, 1)
            )

            ranked_list.append(
                RankedRestaurant(
                    restaurant=r,
                    score=round(final_score, 1),
                    score_breakdown=breakdown,
                    match_category=match_cat,
                    matched_items=matched_items,
                    match_reason=match_reason,
                    dish_availability=dish_avail
                )
            )
            
        # Match category tier priority: Confirmed (3) > Possible (2) > Unverified (1)
        tier_priority = {
            "confirmed": 3,
            "possible": 2,
            "unverified": 1
        }
        # Sort primarily by match category tier, then open before closed, then weighted score
        ranked_list.sort(
            key=lambda x: (
                tier_priority.get(x.match_category, 1),
                0 if x.restaurant.get("is_closed", False) else 1,
                x.score
            ), 
            reverse=True
        )
        
        final_results = ranked_list[:top_k]
        
        # Observability logs
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Restaurant results received: {len(restaurants)}")
        logger.info(f"Restaurants scored: {len(ranked_list)}")
        logger.info(f"Top-K selected: {len(final_results)}")
        
        # Return top K
        return final_results
