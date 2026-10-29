from pydantic import BaseModel
from typing import List, Dict, Any

class ScoreBreakdown(BaseModel):
    food_match: float = 0.0
    rating: float = 0.0
    distance: float = 0.0
    budget_fit: float = 0.0
    total_score: float = 0.0

class RankedRestaurant(BaseModel):
    restaurant: Dict[str, Any]
    score: float
    score_breakdown: ScoreBreakdown
    match_category: str = "unverified"  # "confirmed" | "possible" | "unverified"
    matched_items: List[Dict[str, Any]] = []
    match_reason: str = ""
    dish_availability: str = "unverified"  # "confirmed" | "not_found" | "unavailable" | "unverified"

class RankingWeights(BaseModel):
    food_match: float = 0.40
    rating: float = 0.25
    distance: float = 0.20
    budget_fit: float = 0.15
