import re
from typing import Dict, Any, Optional

class DeterministicScorer:
    """Calculates individual scores for a restaurant."""
    
    @staticmethod
    def extract_distance_meters(restaurant: Dict[str, Any]) -> Optional[float]:
        """Extracts distance in meters from restaurant dict, handling various units and field names."""
        if "distance_meters" in restaurant and restaurant["distance_meters"] is not None:
            try:
                return float(restaurant["distance_meters"])
            except (ValueError, TypeError):
                pass

        for km_field in ("distanceKm", "distance_km"):
            if km_field in restaurant and restaurant[km_field] is not None:
                try:
                    return float(restaurant[km_field]) * 1000.0
                except (ValueError, TypeError):
                    pass

        if "distance" in restaurant and restaurant["distance"] is not None:
            try:
                val = float(restaurant["distance"])
                if val < 50.0:
                    return val * 1000.0
                return val
            except (ValueError, TypeError):
                pass

        return None

    @staticmethod
    def score_food_match(restaurant: Dict[str, Any], query: Optional[str]) -> float:
        """Scores 0-100 based on how well the restaurant matches the query and verified menu data."""
        if not query:
            return 50.0 # Neutral if no specific food asked
            
        q = query.lower()
        match_cat = restaurant.get("match_category")
        
        # If explicit match_category is provided by provider/menu search:
        if match_cat == "confirmed":
            matched_items = restaurant.get("matched_items", [])
            has_prepared = any(it.get("product_type") == "prepared" for it in matched_items)
            has_packaged = any(it.get("product_type") == "packaged" for it in matched_items)
            has_side = any(it.get("product_type") == "side" for it in matched_items)
            has_unspec = any(it.get("product_type") == "unspecified" for it in matched_items)

            # If restaurant does not offer freshly prepared dishes (only packaged retail goods or potato sides):
            if matched_items and not has_prepared:
                if has_packaged:
                    # Packaged retail item (e.g. Chocolate Waffle Tubes (90g)) must not automatically rank alongside freshly prepared waffles
                    return 40.0
                elif has_side:
                    # Side / derivative cut (e.g. Waffle Fries)
                    return 35.0
                elif has_unspec:
                    return 50.0

            base_score = 85.0
            # Check style alignment (e.g. bombay/mumbai for bombay style vadapav, jaipur/rajasthani/pyaaz for jaipur kachori)
            style_keywords = [
                "jaipur", "rajasthan", "rajasthani", "jodhpur", "jodhpuri", "pyaz", "pyaaz", "onion",
                "bombay", "mumbai", "mumbaiya", "maharashtrian",
                "delhi", "amritsari", "kolkata", "bengali", "south indian", "hyderabadi", "lucknowi", "gujarati", "indori"
            ]
            has_style_in_query = any(k in q for k in style_keywords)
            if has_style_in_query:
                item_names = " ".join(it.get("name", "").lower() for it in matched_items)
                matched_style_in_items = any(k in item_names for k in style_keywords if k in q)
                if matched_style_in_items:
                    base_score = 100.0  # Exact confirmed style match on verified menu item
                else:
                    base_score = 85.0   # Generic dish match on menu, specific requested style unverified
            else:
                base_score = 90.0
            return min(base_score, 100.0)
            
        elif match_cat == "possible":
            return 30.0
        elif match_cat == "unverified":
            return 0.0

        # Fallback if match_category was not explicitly set (e.g. basic mock)
        score = 0.0
        if q in restaurant.get("name", "").lower():
            score += 50.0
        cuisines = restaurant.get("cuisine", [])
        if any(q in c.lower() for c in cuisines):
            score += 50.0
            
        return min(score, 100.0)
        
    @staticmethod
    def score_rating(restaurant: Dict[str, Any]) -> float:
        """Scores 0-100 based on rating."""
        rating = restaurant.get("rating", 0.0)
        # Assuming rating is out of 5
        return min((rating / 5.0) * 100.0, 100.0)
        
    @staticmethod
    def score_distance(restaurant: Dict[str, Any], max_distance_meters: float = 15000.0) -> float:
        """Scores 0-100 based on how close it is (0m = 100, max_distance_meters = 0)."""
        dist = DeterministicScorer.extract_distance_meters(restaurant)
        if dist is None:
            return 50.0 # Neutral if unknown
        if dist <= 0:
            return 100.0
        
        if max_distance_meters <= 0:
            return 0.0

        score = max(0.0, 100.0 * (1.0 - (dist / max_distance_meters)))
        return round(min(score, 100.0), 1)
        
    @staticmethod
    def score_budget(restaurant: Dict[str, Any], target_price_tier: Optional[str]) -> float:
        """Scores 0-100 based on price fit."""
        if not target_price_tier:
            return 50.0 # Neutral
            
        price = restaurant.get("price", "N/A")
        if price == "N/A":
            return 50.0 # Unknown
            
        if price == target_price_tier:
            return 100.0
            
        # Penalty if it's longer (more expensive) or shorter (cheaper but maybe lower quality)
        diff = abs(len(price) - len(target_price_tier))
        score = max(0.0, 100.0 - (diff * 33.3))
        return score
