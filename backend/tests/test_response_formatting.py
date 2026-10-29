import sys
import os
import pytest

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.agent.prompts import SYSTEM_PROMPT

def test_system_prompt_forbids_markdown_tables():
    """Ensure the system prompt strictly bans markdown tables."""
    assert "NEVER generate Markdown tables under any circumstance" in SYSTEM_PROMPT
    assert "Do not use '|' table syntax" in SYSTEM_PROMPT

def test_system_prompt_prevents_duplicate_restaurant_listings():
    """Ensure prompt instructs model not to repeat restaurant lists since cards are rendered."""
    assert "DO NOT repeat full restaurant lists, tables, addresses, ratings, or prices in the assistant's text response" in SYSTEM_PROMPT
    assert "The frontend UI automatically renders structured, interactive restaurant cards" in SYSTEM_PROMPT

def test_system_prompt_defines_concise_weather_recommendation_structure():
    """Ensure prompt prescribes concise, bulleted weather food recommendation format."""
    assert "Weather-Based Food Recommendations Format" in SYSTEM_PROMPT
    assert "**Dish Name** — Brief 1-sentence explanation" in SYSTEM_PROMPT
    assert "Always use actual live weather and food suggestions returned by tools" in SYSTEM_PROMPT

def test_system_prompt_preserves_authenticity_and_verification():
    """Ensure menu verification rules are intact."""
    assert "NEVER make unsupported claims like calling an unverified place 'the best option for authentic Rajasthani-style kachori'" in SYSTEM_PROMPT
    assert "ONLY claim a restaurant serves the dish if `match_category` is 'confirmed'" in SYSTEM_PROMPT
    assert "If NO confirmed matches are found, explicitly say that the available provider results do not verify the requested dish" in SYSTEM_PROMPT
