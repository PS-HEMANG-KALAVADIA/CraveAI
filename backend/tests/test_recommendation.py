import pytest
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from app.recommendation.scorer import DeterministicScorer
from app.recommendation.engine import RecommendationEngine

def test_scorer_food_match():
    scorer = DeterministicScorer()
    
    r1 = {"name": "Gujarati Thali", "cuisine": ["Indian"]}
    assert scorer.score_food_match(r1, "Gujarati") == 50.0  # Matches name
    
    r2 = {"name": "Spice House", "cuisine": ["Gujarati"]}
    assert scorer.score_food_match(r2, "Gujarati") == 50.0  # Matches cuisine
    
    r3 = {"name": "Gujarati Sweets", "cuisine": ["Gujarati"]}
    assert scorer.score_food_match(r3, "Gujarati") == 100.0 # Matches both
    
    r4 = {"name": "Pasta Place", "cuisine": ["Italian"]}
    assert scorer.score_food_match(r4, "Gujarati") == 0.0   # No match
    
    assert scorer.score_food_match(r4, None) == 50.0 # Neutral

def test_scorer_distance():
    scorer = DeterministicScorer()
    assert scorer.score_distance({"distance_meters": 0}) == 100.0
    assert scorer.score_distance({"distance_meters": 5000}, 5000.0) == 0.0
    assert scorer.score_distance({"distance_meters": 2500}, 5000.0) == 50.0

def test_scorer_budget():
    scorer = DeterministicScorer()
    assert scorer.score_budget({"price": "$$"}, "$$") == 100.0
    assert scorer.score_budget({"price": "$$$"}, "$") == max(0.0, 100.0 - (2 * 33.3))
    assert scorer.score_budget({}, "$") == 50.0

def test_engine_intent_weights():
    engine = RecommendationEngine()
    
    w_best = engine._adjust_weights_from_intent("I want the best food")
    assert w_best.rating == 0.40
    
    w_close = engine._adjust_weights_from_intent("Find something close by")
    assert w_close.distance == 0.40
    
    w_cheap = engine._adjust_weights_from_intent("cheap food")
    assert w_cheap.budget_fit == 0.40

def test_engine_ranking_order():
    engine = RecommendationEngine()
    
    restaurants = [
        {"id": "r1", "name": "Okay Place", "rating": 3.0, "distance_meters": 4000, "price": "$$$"},
        {"id": "r2", "name": "Perfect Match", "rating": 5.0, "distance_meters": 100, "price": "$$", "cuisine": ["Spicy"]},
        {"id": "r3", "name": "Close but bad", "rating": 1.0, "distance_meters": 50, "price": "$$"}
    ]
    
    # Generic query
    ranked = engine.rank(restaurants, user_message="Find me spicy food", tool_args={"query": "spicy", "price_tier": "$$"})
    
    assert len(ranked) == 3
    assert ranked[0].restaurant["name"] == "Perfect Match" # Highest score
    assert ranked[-1].restaurant["name"] == "Okay Place" # Lowest score

def test_engine_top_k():
    engine = RecommendationEngine()
    restaurants = [{"id": str(i)} for i in range(10)]
    
    ranked = engine.rank(restaurants, "", {}, top_k=3)
    assert len(ranked) == 3
