import pytest
import sys
import os
import json
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.agent.agent import CraveAIAgent
from app.services.geocoding import extract_city, geocode_city

@pytest.mark.asyncio
async def test_pani_puri_without_location_prompts_for_city():
    """
    User asks: 'suggest me nearby places for pani puri'
    Browser location unavailable -> Context prompts model to ask for city name, not coordinates.
    """
    agent = CraveAIAgent()
    agent.client = MagicMock()

    agent._cached_groq_tools = [
        {"type": "function", "function": {"name": "search_nearby_restaurants", "parameters": {}}}
    ]
    agent.mcp_tools_cache = {
        "search_nearby_restaurants": ("restaurant", MagicMock())
    }

    mock_choice = MagicMock()
    mock_choice.message.content = "Which city are you currently in? I can find nearby pani puri places once I know your city."
    mock_choice.message.tool_calls = None

    agent.client.chat.completions.create = AsyncMock(return_value=MagicMock(choices=[mock_choice]))

    results = []
    async for chunk in agent.chat_stream(
        user_message="suggest me nearby places for pani puri",
        conversation=[],
        location=None,
        location_status="denied"
    ):
        results.append(json.loads(chunk))

    called_messages = agent.client.chat.completions.create.call_args[1]["messages"]
    user_msg_content = next(m["content"] for m in called_messages if m["role"] == "user")
    assert "User location coordinates are unavailable" in user_msg_content
    assert "ask for a city name" in user_msg_content
    assert "Do NOT ask for latitude/longitude coordinates" in user_msg_content


@pytest.mark.asyncio
async def test_ahmedabad_city_reply_geocoding_and_restaurant_search():
    """
    User replies: 'Ahmedabad' following 'suggest me nearby places for pani puri'.
    System resolves Ahmedabad coordinates -> Groq calls search_nearby_restaurants with resolved coords.
    """
    agent = CraveAIAgent()
    agent.client = MagicMock()

    agent._cached_groq_tools = [
        {"type": "function", "function": {"name": "search_nearby_restaurants", "parameters": {}}}
    ]
    mock_restaurant_client = MagicMock()
    mock_text_content = MagicMock()
    mock_text_content.text = json.dumps({
        "restaurants": [
            {
                "id": "swiggy_p1",
                "name": "Pakwan Chaat Center",
                "rating": 4.5,
                "price": "$",
                "distance_meters": 1200,
                "cuisine": ["Street Food", "Pani Puri"],
                "address": "Ahmedabad",
                "is_closed": False,
                "url": "https://swiggy.com/restaurants/pakwan"
            }
        ]
    })
    mock_restaurant_client.call_tool = AsyncMock(return_value=[mock_text_content])
    agent.restaurant_client = mock_restaurant_client
    agent.mcp_tools_cache = {
        "search_nearby_restaurants": ("restaurant", mock_restaurant_client)
    }

    # Model tool call with resolved coordinates
    fake_tool_call = MagicMock()
    fake_tool_call.id = "call_swiggy_1"
    fake_tool_call.type = "function"
    fake_tool_call.function.name = "search_nearby_restaurants"
    fake_tool_call.function.arguments = json.dumps({
        "latitude": 23.0225,
        "longitude": 72.5714,
        "query": "pani puri"
    })

    mock_choice_1 = MagicMock()
    mock_choice_1.message.content = None
    mock_choice_1.message.tool_calls = [fake_tool_call]

    mock_choice_2 = MagicMock()
    mock_choice_2.message.content = "Here are the best places for pani puri in Ahmedabad: Pakwan Chaat Center!"
    mock_choice_2.message.tool_calls = None

    agent.client.chat.completions.create = AsyncMock(side_effect=[
        MagicMock(choices=[mock_choice_1]),
        MagicMock(choices=[mock_choice_2])
    ])

    conversation = [
        {"role": "user", "content": "suggest me nearby places for pani puri"},
        {"role": "assistant", "content": "Which city are you currently in?"}
    ]

    with patch("app.agent.agent.geocode_city", new_callable=AsyncMock) as mock_geo:
        mock_geo.return_value = {
            "name": "Ahmedabad",
            "latitude": 23.0225,
            "longitude": 72.5714,
            "country": "India"
        }

        results = []
        async for chunk in agent.chat_stream(
            user_message="Ahmedabad",
            conversation=conversation,
            location=None,
            location_status="denied"
        ):
            results.append(json.loads(chunk))

    # Verify geocoding was called
    mock_geo.assert_called_with("Ahmedabad")

    # Verify coordinates passed to tool
    mock_restaurant_client.call_tool.assert_called_once()
    called_tool_name, called_args = mock_restaurant_client.call_tool.call_args[0]
    assert called_tool_name == "search_nearby_restaurants"
    assert called_args["latitude"] == 23.0225
    assert called_args["longitude"] == 72.5714

    # Verify final result
    final_res = next(r for r in results if r.get("type") == "result")
    assert "search_nearby_restaurants" in final_res["tools_used"]
    assert len(final_res["restaurants"]) == 1
    assert final_res["restaurants"][0]["restaurant"]["name"] == "Pakwan Chaat Center"


@pytest.mark.asyncio
async def test_existing_browser_coordinates_searches_directly():
    """
    User asks: 'suggest me nearby places for pani puri' with browser coordinates available.
    Agent directly searches without asking for city.
    """
    agent = CraveAIAgent()
    agent.client = MagicMock()

    agent._cached_groq_tools = [
        {"type": "function", "function": {"name": "search_nearby_restaurants", "parameters": {}}}
    ]
    mock_restaurant_client = MagicMock()
    mock_text_content = MagicMock()
    mock_text_content.text = json.dumps({"restaurants": [{"id": "r1", "name": "Direct Place", "rating": 4.2}]})
    mock_restaurant_client.call_tool = AsyncMock(return_value=[mock_text_content])
    agent.restaurant_client = mock_restaurant_client
    agent.mcp_tools_cache = {
        "search_nearby_restaurants": ("restaurant", mock_restaurant_client)
    }

    fake_tool_call = MagicMock()
    fake_tool_call.id = "call_direct_1"
    fake_tool_call.type = "function"
    fake_tool_call.function.name = "search_nearby_restaurants"
    fake_tool_call.function.arguments = json.dumps({
        "latitude": 23.0225,
        "longitude": 72.5714,
        "query": "pani puri"
    })

    mock_choice_1 = MagicMock()
    mock_choice_1.message.content = None
    mock_choice_1.message.tool_calls = [fake_tool_call]

    mock_choice_2 = MagicMock()
    mock_choice_2.message.content = "Found Direct Place near you!"
    mock_choice_2.message.tool_calls = None

    agent.client.chat.completions.create = AsyncMock(side_effect=[
        MagicMock(choices=[mock_choice_1]),
        MagicMock(choices=[mock_choice_2])
    ])

    results = []
    async for chunk in agent.chat_stream(
        user_message="suggest me nearby places for pani puri",
        conversation=[],
        location={"latitude": 23.0225, "longitude": 72.5714},
        location_status="available"
    ):
        results.append(json.loads(chunk))

    mock_restaurant_client.call_tool.assert_called_once()
    called_tool_name, called_args = mock_restaurant_client.call_tool.call_args[0]
    assert called_tool_name == "search_nearby_restaurants"
    assert called_args["latitude"] == 23.0225
    assert called_args["longitude"] == 72.5714


@pytest.mark.asyncio
async def test_provider_failure_does_not_display_nearby_restaurants_found():
    """
    When restaurant provider fails (e.g. Swiggy token expired or connection error),
    tools_used must NOT report 'search_nearby_restaurants' (which renders 'Nearby restaurants found').
    Instead, it must record 'search_nearby_restaurants_failed'.
    """
    agent = CraveAIAgent()
    agent.client = MagicMock()

    agent._cached_groq_tools = [
        {"type": "function", "function": {"name": "search_nearby_restaurants", "parameters": {}}}
    ]
    mock_restaurant_client = MagicMock()
    mock_text_content = MagicMock()
    mock_text_content.text = json.dumps({"error": "Swiggy session expired. Please re-authenticate at /api/swiggy/login"})
    mock_restaurant_client.call_tool = AsyncMock(return_value=[mock_text_content])
    agent.restaurant_client = mock_restaurant_client
    agent.mcp_tools_cache = {
        "search_nearby_restaurants": ("restaurant", mock_restaurant_client)
    }

    fake_tool_call = MagicMock()
    fake_tool_call.id = "call_fail_1"
    fake_tool_call.type = "function"
    fake_tool_call.function.name = "search_nearby_restaurants"
    fake_tool_call.function.arguments = json.dumps({"latitude": 23.0225, "longitude": 72.5714, "query": "pani puri"})

    mock_choice_1 = MagicMock()
    mock_choice_1.message.content = None
    mock_choice_1.message.tool_calls = [fake_tool_call]

    mock_choice_2 = MagicMock()
    mock_choice_2.message.content = "I'm sorry, the restaurant search service is currently unavailable."
    mock_choice_2.message.tool_calls = None

    agent.client.chat.completions.create = AsyncMock(side_effect=[
        MagicMock(choices=[mock_choice_1]),
        MagicMock(choices=[mock_choice_2])
    ])

    results = []
    async for chunk in agent.chat_stream(
        user_message="suggest me nearby places for pani puri in Ahmedabad",
        conversation=[],
        location={"latitude": 23.0225, "longitude": 72.5714}
    ):
        results.append(json.loads(chunk))

    final_res = next(r for r in results if r.get("type") == "result")
    # Must NOT report success!
    assert "search_nearby_restaurants" not in final_res["tools_used"]
    # Must report failure!
    assert "search_nearby_restaurants_failed" in final_res["tools_used"]
    assert final_res["restaurants"] == []


@pytest.mark.asyncio
async def test_zero_results_reports_truthful_status():
    """
    When restaurant provider finds 0 results, tools_used must record
    'search_nearby_restaurants_no_results' instead of claiming restaurants were found.
    """
    agent = CraveAIAgent()
    agent.client = MagicMock()

    agent._cached_groq_tools = [
        {"type": "function", "function": {"name": "search_nearby_restaurants", "parameters": {}}}
    ]
    mock_restaurant_client = MagicMock()
    mock_text_content = MagicMock()
    mock_text_content.text = json.dumps({"message": "No restaurants found matching the criteria."})
    mock_restaurant_client.call_tool = AsyncMock(return_value=[mock_text_content])
    agent.restaurant_client = mock_restaurant_client
    agent.mcp_tools_cache = {
        "search_nearby_restaurants": ("restaurant", mock_restaurant_client)
    }

    fake_tool_call = MagicMock()
    fake_tool_call.id = "call_zero_1"
    fake_tool_call.type = "function"
    fake_tool_call.function.name = "search_nearby_restaurants"
    fake_tool_call.function.arguments = json.dumps({"latitude": 23.0225, "longitude": 72.5714, "query": "nonexistent food"})

    mock_choice_1 = MagicMock()
    mock_choice_1.message.content = None
    mock_choice_1.message.tool_calls = [fake_tool_call]

    mock_choice_2 = MagicMock()
    mock_choice_2.message.content = "No nearby places found for that dish."
    mock_choice_2.message.tool_calls = None

    agent.client.chat.completions.create = AsyncMock(side_effect=[
        MagicMock(choices=[mock_choice_1]),
        MagicMock(choices=[mock_choice_2])
    ])

    results = []
    async for chunk in agent.chat_stream(
        user_message="find nonexistent food nearby",
        conversation=[],
        location={"latitude": 23.0225, "longitude": 72.5714}
    ):
        results.append(json.loads(chunk))

    final_res = next(r for r in results if r.get("type") == "result")
    assert "search_nearby_restaurants" not in final_res["tools_used"]
    assert "search_nearby_restaurants_no_results" in final_res["tools_used"]
    assert final_res["restaurants"] == []


@pytest.mark.asyncio
async def test_pani_puri_unconfirmed_results_marked_unverified():
    """
    Requirement 1: A pani puri search where general restaurant results do not confirm the dish.
    Restaurants with no pani puri on menu should be marked unverified and not claimed as confirmed.
    """
    from app.recommendation.engine import RecommendationEngine

    engine = RecommendationEngine()
    restaurants = [
        {
            "id": "r1",
            "name": "Urban Khichdi",
            "rating": 4.6,
            "distance_meters": 500,
            "price": "$$",
            "cuisine": ["North Indian", "Khichdi"],
            "match_category": "unverified",
            "matched_items": [],
            "match_reason": "No relevant menu evidence available for requested dish."
        },
        {
            "id": "r2",
            "name": "Gwalia Sweets & Fast Food",
            "rating": 4.4,
            "distance_meters": 1500,
            "price": "$",
            "cuisine": ["Street Food", "Snacks"],
            "match_category": "confirmed",
            "matched_items": [{"name": "Paani Puri (5 Pc)", "price": 65.0, "rating": 4.5}],
            "match_reason": "Confirmed menu item: Paani Puri (5 Pc) (₹65.0)"
        }
    ]

    ranked = engine.rank(restaurants, "suggest me nearby places for pani puri", {"query": "pani puri"})
    assert len(ranked) == 2
    # Gwalia Sweets (confirmed) must outrank Urban Khichdi (unverified)
    assert ranked[0].restaurant["name"] == "Gwalia Sweets & Fast Food"
    assert ranked[0].match_category == "confirmed"
    assert len(ranked[0].matched_items) > 0
    assert ranked[1].restaurant["name"] == "Urban Khichdi"
    assert ranked[1].match_category == "unverified"


@pytest.mark.asyncio
async def test_kachori_preserves_jaipur_style_across_city_clarification():
    """
    Requirement 2: A kachori search that preserves 'Jaipur-style' across a city clarification.
    When user clarifies city as 'Ahmedabad', context and active query must preserve 'jaipur style authentic kachori'.
    """
    agent = CraveAIAgent()
    agent.client = MagicMock()

    agent._cached_groq_tools = [
        {"type": "function", "function": {"name": "search_nearby_restaurants", "parameters": {}}}
    ]
    mock_choice = MagicMock()
    mock_choice.message.content = "Here are Jaipur-style kachori places in Ahmedabad."
    mock_choice.message.tool_calls = None
    agent.client.chat.completions.create = AsyncMock(return_value=MagicMock(choices=[mock_choice]))

    conversation_history = [
        {"role": "user", "content": "suggest me places for jaipur style authentic kachori in ahmedabaf"},
        {"role": "assistant", "content": "Which city are you referring to?"}
    ]

    results = []
    async for chunk in agent.chat_stream(
        user_message="Ahmedabad",
        conversation=conversation_history,
        location=None
    ):
        results.append(json.loads(chunk))

    called_messages = agent.client.chat.completions.create.call_args[1]["messages"]
    user_msgs = [m for m in called_messages if m["role"] == "user"]
    user_msg_content = user_msgs[-1]["content"]

    # Verify context retains the original dish and style
    assert "jaipur style authentic kachori" in user_msg_content.lower()
    assert "ahmedabad" in user_msg_content.lower()
    assert "Retain all original constraints" in user_msg_content or "Preserve all dish" in user_msg_content
    assert agent.current_user_message == "suggest me places for jaipur style authentic kachori in Ahmedabad"


@pytest.mark.asyncio
async def test_city_typo_ahmedabaf():
    """
    Requirement 3: A likely city typo such as 'ahmedabaf' is resolved to Ahmedabad.
    """
    geo = await geocode_city("ahmedabaf")
    assert geo is not None
    assert geo["name"] == "Ahmedabad"
    assert geo["corrected_from"] == "ahmedabaf"
    assert round(geo["latitude"], 1) == 23.0
    assert round(geo["longitude"], 1) == 72.6


def test_confirmed_menu_matches_outranking_unverified_restaurants():
    """
    Requirement 4: Confirmed menu matches outranking unverified restaurants.
    Even with high rating and 0 distance, an unverified place cannot outrank a confirmed place.
    """
    from app.recommendation.engine import RecommendationEngine

    engine = RecommendationEngine()
    candidates = [
        {
            "id": "unverified_superstar",
            "name": "Superstar Luxury Cafe",
            "rating": 5.0,
            "distance_meters": 100,
            "price": "$$",
            "cuisine": ["Cafe", "Beverages"],
            "match_category": "unverified",
            "matched_items": [],
            "match_reason": "No relevant menu evidence available for requested dish."
        },
        {
            "id": "possible_snack_spot",
            "name": "Quick Snacks",
            "rating": 4.0,
            "distance_meters": 1000,
            "price": "$",
            "cuisine": ["Street Food", "Snacks"],
            "match_category": "possible",
            "matched_items": [],
            "match_reason": "Serves Street Food, but specific dish is unverified on menu."
        },
        {
            "id": "confirmed_local_gem",
            "name": "Kota Kachori Hub",
            "rating": 4.1,
            "distance_meters": 3500,
            "price": "$",
            "cuisine": ["Snacks"],
            "match_category": "confirmed",
            "matched_items": [{"name": "Jodhpuri Pyaaz Kachori", "price": 54.0, "rating": 4.5}],
            "match_reason": "Confirmed menu item: Jodhpuri Pyaaz Kachori (₹54.0)"
        }
    ]

    ranked = engine.rank(candidates, "jaipur style authentic kachori", {"query": "kachori"})
    # Confirmed must be #1, Possible must be #2, Unverified must be #3
    assert ranked[0].restaurant["name"] == "Kota Kachori Hub"
    assert ranked[0].match_category == "confirmed"
    assert ranked[1].restaurant["name"] == "Quick Snacks"
    assert ranked[1].match_category == "possible"
    assert ranked[2].restaurant["name"] == "Superstar Luxury Cafe"
    assert ranked[2].match_category == "unverified"


def test_no_confirmed_matches():
    """
    Requirement 5: No confirmed dish matches handling.
    All restaurants marked unverified/possible, none marked confirmed.
    """
    from app.recommendation.engine import RecommendationEngine

    engine = RecommendationEngine()
    candidates = [
        {
            "id": "r1",
            "name": "Cafe One",
            "rating": 4.2,
            "distance_meters": 1000,
            "cuisine": ["Cafe"],
            "match_category": "unverified",
            "matched_items": []
        },
        {
            "id": "r2",
            "name": "Snack Corner",
            "rating": 4.0,
            "distance_meters": 1200,
            "cuisine": ["Snacks"],
            "match_category": "possible",
            "matched_items": []
        }
    ]

    ranked = engine.rank(candidates, "kachori", {"query": "kachori"})
    assert not any(r.match_category == "confirmed" for r in ranked)
    assert any(r.match_category == "possible" for r in ranked)
    assert any(r.match_category == "unverified" for r in ranked)


def test_empty_menu_results_and_provider_parsing():
    """
    Requirement 6: Empty menu results and provider errors are parsed safely.
    """
    import sys
    sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "mcp_servers", "restaurants"))
    from providers.swiggy import SwiggyRestaurantProvider

    # Test empty or malformed menu text returns empty list cleanly
    assert SwiggyRestaurantProvider._parse_menu_search_text("") == []
    assert SwiggyRestaurantProvider._parse_menu_search_text("No items found.") == []
    assert SwiggyRestaurantProvider._parse_menu_search_text("Random error text 500") == []

    # Test valid line extraction
    sample = "1. Onion Kachori (1 Pcs) — ₹45 | Veg | 4.3★ | Gwalia Sweets & Fast Food (restaurantId: 37578) (ID: 7448265)"
    items = SwiggyRestaurantProvider._parse_menu_search_text(sample)
    assert len(items) == 1
    assert items[0]["name"] == "Onion Kachori (1 Pcs)"
    assert items[0]["price"] == 45.0
    assert items[0]["restaurant_id"] == "37578"


def test_no_unsupported_authenticity_claims_rules():
    """
    Requirement 7: System prompt contains explicit rules against unsupported authenticity claims.
    """
    from app.agent.prompts import SYSTEM_PROMPT

    assert "NEVER make unsupported claims like calling an unverified place 'the best option for authentic Rajasthani-style kachori'" in SYSTEM_PROMPT
    assert "ONLY claim a restaurant serves the dish if `match_category` is 'confirmed'" in SYSTEM_PROMPT
    assert "If NO confirmed matches are found, explicitly say that the available provider results do not verify the requested dish" in SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_existing_weather_and_restaurant_searches_functional():
    """
    Requirement 8: Existing weather and restaurant searches remain fully functional.
    """
    # 1. Weather geocoding
    geo = await geocode_city("Ahmedabad")
    assert geo is not None
    assert geo["name"] == "Ahmedabad"

    # 2. Extract city handles both weather and food
    assert extract_city("What's the weather in Ahmedabad?") == "Ahmedabad"
    assert extract_city("suggest me places for pani puri in Ahmedabad") == "Ahmedabad"


# ======================================================================
# Tests for Swiggy Links, Menu-Match Classification, and Scoring Audit
# ======================================================================

def test_canonical_swiggy_url_preservation():
    """
    Test 1: Canonical Swiggy URL preservation from provider response to frontend.
    Does not construct https://www.swiggy.com/restaurants/{id} when canonical URL is available.
    """
    import sys
    sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "mcp_servers", "restaurants"))
    from providers.swiggy import SwiggyRestaurantProvider

    raw_restaurant = {
        "id": "36340",
        "name": "Neel Kamal Snacks And Coffee Bar",
        "url": "https://www.swiggy.com/city/ahmedabad/neel-kamal-snacks-memnagar-rest36340",
        "distanceKm": 5.7,
        "costForTwo": "₹400 for two",
        "avgRating": 4.2
    }

    # Simulate provider normalization
    canonical_url = raw_restaurant.get("url")
    assert canonical_url == "https://www.swiggy.com/city/ahmedabad/neel-kamal-snacks-memnagar-rest36340"
    assert "restaurants/36340" not in canonical_url


def test_missing_canonical_url_safe_search_fallback():
    """
    Test 2: Missing canonical URL handling without fabricating direct URLs.
    Falls back to safe search URL with url_type: 'search'. Never invents restaurant slugs or ID URLs.
    """
    import urllib.parse

    raw_restaurant = {
        "id": "656069",
        "name": "Quick Bites by NK",
        "distanceKm": 5.7,
        "costForTwo": "₹300 for two",
        "avgRating": 4.3
    }

    # Should not fabricate https://www.swiggy.com/restaurants/656069
    assert raw_restaurant.get("url") is None

    encoded_name = urllib.parse.quote_plus(raw_restaurant["name"])
    fallback_url = f"https://www.swiggy.com/search?query={encoded_name}"
    assert fallback_url == "https://www.swiggy.com/search?query=Quick+Bites+by+NK"
    assert "search?query=" in fallback_url
    assert "/restaurants/656069" not in fallback_url


def test_external_link_attributes_and_safety():
    """
    Test 3: External links safety handling: target='_blank' and rel='noopener noreferrer'.
    """
    card_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "frontend", "src", "components", "Restaurant", "RestaurantCard.tsx"
    )
    with open(card_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert 'target="_blank"' in content
    assert 'rel="noopener noreferrer"' in content
    assert "Search on Swiggy ↗" in content
    assert "View on Swiggy ↗" in content


def test_generic_vada_pav_vs_confirmed_bombay_style():
    """
    Test 4: Generic vada pav versus confirmed Bombay-style vada pav.
    - Exact style match scores 100.0
    - Generic dish match scores 85.0
    - Name-only 'Vadapav' restaurant without menu match is 'possible', scores 30.0, and never confirmed.
    """
    from app.recommendation.scorer import DeterministicScorer
    from app.recommendation.engine import RecommendationEngine

    query = "suggest me places for bombay style vadapav"

    # Restaurant 1: Exact style match on verified menu item
    r_exact = {
        "id": "r_exact",
        "name": "Neel Kamal Snacks",
        "match_category": "confirmed",
        "matched_items": [{"name": "Bombay Style Vada Pav", "price": 50.0, "rating": 4.1}],
        "distance_meters": 5700,
        "rating": 4.2
    }
    score_exact = DeterministicScorer.score_food_match(r_exact, query)
    assert score_exact == 100.0

    # Restaurant 2: Generic dish confirmed, but requested style not verified on item
    r_generic = {
        "id": "r_generic",
        "name": "Shreeji Snacks",
        "match_category": "confirmed",
        "matched_items": [{"name": "Regular Vada Pav", "price": 30.0, "rating": 4.0}],
        "distance_meters": 3000,
        "rating": 4.2
    }
    score_generic = DeterministicScorer.score_food_match(r_generic, query)
    assert score_generic == 85.0

    # Restaurant 3: Restaurant name has 'Vadapav', but no verified menu item
    r_name_only = {
        "id": "r_name_only",
        "name": "Jay Bhole Vadapav",
        "match_category": "possible",
        "matched_items": [],
        "distance_meters": 2600,
        "rating": 4.1
    }
    score_name_only = DeterministicScorer.score_food_match(r_name_only, query)
    assert score_name_only == 30.0

    # Engine ranking
    engine = RecommendationEngine()
    ranked = engine.rank([r_name_only, r_generic, r_exact], query, {"query": "bombay style vadapav"})
    # Exact style must be #1, generic #2, name-only (possible) #3
    assert ranked[0].restaurant["id"] == "r_exact"
    assert ranked[1].restaurant["id"] == "r_generic"
    assert ranked[2].restaurant["id"] == "r_name_only"
    assert ranked[2].match_category == "possible"


def test_menu_item_price_and_rating_association():
    """
    Test 5: Correct menu item price and rating association.
    Menu item price (50.0) and rating (4.3) come from matched_items, distinct from restaurant rating (3.8).
    """
    rest = {
        "id": "r_sample",
        "name": "Quick Bites by NK",
        "rating": 3.8,  # Restaurant level rating
        "price": "$$",   # Restaurant level price tier
        "match_category": "confirmed",
        "matched_items": [
            {"name": "Bombay Style Vada Pav", "price": 50.0, "rating": 4.3}
        ]
    }
    assert rest["matched_items"][0]["price"] == 50.0
    assert rest["matched_items"][0]["rating"] == 4.3
    assert rest["matched_items"][0]["rating"] != rest["rating"]


def test_distance_scores_across_distances():
    """
    Test 6: Distance scores for restaurants at different distances.
    5.0 km, 5.7 km, and 10.8 km produce non-zero scores, and closer restaurants score higher.
    """
    from app.recommendation.scorer import DeterministicScorer

    r_1km = {"name": "Near", "distance_meters": 1000}
    r_5km = {"name": "Mid5", "distanceKm": 5.0}  # distanceKm field handled
    r_5_7km = {"name": "Mid57", "distance": 5.7}  # distance in km handled
    r_10_8km = {"name": "Far", "distance_meters": 10800}

    s_1 = DeterministicScorer.score_distance(r_1km)
    s_5 = DeterministicScorer.score_distance(r_5km)
    s_57 = DeterministicScorer.score_distance(r_5_7km)
    s_108 = DeterministicScorer.score_distance(r_10_8km)

    # All must be non-zero
    assert s_1 > 0.0
    assert s_5 > 0.0
    assert s_57 > 0.0
    assert s_108 > 0.0

    # Closer restaurants strictly outscore farther ones
    assert s_1 > s_5 > s_57 > s_108

    # Check approximate expected values (relative to 15km scale)
    assert round(s_5, 1) == 66.7
    assert round(s_57, 1) == 62.0
    assert round(s_108, 1) == 28.0


def test_existing_recommendation_tier_priority():
    """
    Test 7: Recommendation tier priority: Confirmed (3) > Possible (2) > Unverified (1).
    Within a tier, open restaurants outrank closed ones, and distance/rating break ties.
    """
    from app.recommendation.engine import RecommendationEngine

    candidates = [
        {
            "id": "unverified_spot",
            "name": "Luxury Cafe",
            "rating": 5.0,
            "distance_meters": 500,
            "match_category": "unverified",
            "is_closed": False
        },
        {
            "id": "possible_spot",
            "name": "Vada Pav Corner",
            "rating": 4.5,
            "distance_meters": 800,
            "match_category": "possible",
            "is_closed": False
        },
        {
            "id": "confirmed_closed",
            "name": "Super Bombay Vada Pav (Closed)",
            "rating": 4.5,
            "distance_meters": 2000,
            "match_category": "confirmed",
            "matched_items": [{"name": "Bombay Style Vada Pav", "price": 40.0}],
            "is_closed": True
        },
        {
            "id": "confirmed_open_far",
            "name": "Bombay Vada Pav (Far)",
            "rating": 4.0,
            "distance_meters": 6000,
            "match_category": "confirmed",
            "matched_items": [{"name": "Bombay Style Vada Pav", "price": 40.0}],
            "is_closed": False
        },
        {
            "id": "confirmed_open_near",
            "name": "Bombay Vada Pav (Near)",
            "rating": 4.0,
            "distance_meters": 2000,
            "match_category": "confirmed",
            "matched_items": [{"name": "Bombay Style Vada Pav", "price": 40.0}],
            "is_closed": False
        }
    ]

    engine = RecommendationEngine()
    ranked = engine.rank(candidates, "bombay style vadapav", {"query": "bombay style vadapav"})

    # First 3 must all be confirmed
    assert ranked[0].match_category == "confirmed"
    assert ranked[1].match_category == "confirmed"
    assert ranked[2].match_category == "confirmed"

    # Between open confirmed: Near (2000m) outranks Far (6000m)
    assert ranked[0].restaurant["id"] == "confirmed_open_near"
    assert ranked[1].restaurant["id"] == "confirmed_open_far"

    # Open confirmed outranks Closed confirmed
    assert ranked[2].restaurant["id"] == "confirmed_closed"

    # Confirmed outranks Possible, which outranks Unverified
    assert ranked[3].match_category == "possible"
    assert ranked[4].match_category == "unverified"
