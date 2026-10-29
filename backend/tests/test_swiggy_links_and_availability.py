import pytest
import sys
import os
import json
import urllib.parse
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure app and mcp_servers can be imported
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "mcp_servers", "restaurants"))

from providers.swiggy import SwiggyRestaurantProvider, clean_restaurant_name
from app.recommendation.scorer import DeterministicScorer
from app.recommendation.engine import RecommendationEngine
from app.agent.agent import CraveAIAgent


class FakeTool:
    def __init__(self, name, inputSchema=None):
        self.name = name
        self.inputSchema = inputSchema or {"type": "object", "properties": {}}


class FakeSession:
    def __init__(self, tools, call_map):
        self.tools = tools
        self.call_map = call_map

    async def list_tools(self):
        res = MagicMock()
        res.tools = self.tools
        return res

    async def call_tool(self, name, args):
        if name in self.call_map:
            handler = self.call_map[name]
            if callable(handler):
                data = handler(args)
            else:
                data = handler
            res = MagicMock()
            content = MagicMock()
            content.text = json.dumps(data) if not isinstance(data, str) else data
            res.content = [content]
            return res
        raise ValueError(f"Unexpected tool call: {name}")


def mock_session_execution(provider, session):
    async def side_effect(cb):
        return await cb(session)
    return patch.object(provider, "_run_with_session", side_effect=side_effect)


@pytest.fixture
def mock_swiggy_provider(tmp_path):
    token_file = tmp_path / ".swiggy_token.json"
    token_file.write_text(json.dumps({"access_token": "valid_token_abc"}))
    p = SwiggyRestaurantProvider()
    p.token_path = str(token_file)
    return p


# ==============================================================================
# 1. Canonical URL Preservation vs Search Fallback
# ==============================================================================

@pytest.mark.asyncio
async def test_canonical_url_preserved_when_supplied_by_provider(mock_swiggy_provider):
    """Requirement 1: An official canonical URL returned by Swiggy is preserved without alteration."""
    canonical_url = "https://www.swiggy.com/restaurants/gwalia-sweets-ahmedabad-12345"
    session = FakeSession(
        tools=[FakeTool("search_restaurants"), FakeTool("search_menu")],
        call_map={
            "search_restaurants": {
                "restaurants": [
                    {
                        "id": "rest_1",
                        "name": "Gwalia Sweets",
                        "rating": 4.3,
                        "url": canonical_url
                    }
                ]
            },
            "search_menu": {"items": []}
        }
    )

    with mock_session_execution(mock_swiggy_provider, session):
        results = await mock_swiggy_provider.search_nearby_restaurants(23.0225, 72.5714, query="pani puri")

    assert len(results) == 1
    assert results[0]["url"] == canonical_url
    assert results[0]["url_type"] == "canonical"


@pytest.mark.asyncio
async def test_search_fallback_url_encoded_with_restaurant_name_and_dish(mock_swiggy_provider):
    """Requirement 2: Search fallback URLs combine restaurant name and requested dish with proper encoding."""
    session = FakeSession(
        tools=[FakeTool("search_restaurants"), FakeTool("search_menu")],
        call_map={
            "search_restaurants": {
                "restaurants": [
                    {
                        "id": "rest_ad",
                        "name": "Gwalia Sweets & Fast Food (Ad)",
                        "rating": 4.1
                    },
                    {
                        "id": "rest_apos",
                        "name": "Radhika's Authentic South Indian Food",
                        "rating": 4.4
                    }
                ]
            },
            "search_menu": {"items": []}
        }
    )

    with mock_session_execution(mock_swiggy_provider, session):
        results = await mock_swiggy_provider.search_nearby_restaurants(23.0225, 72.5714, query="pani puri")

    assert len(results) == 2

    # Check 1: Gwalia Sweets & Fast Food (Ad) with requested dish pani puri
    gwalia = results[0]
    assert gwalia["name"] == "Gwalia Sweets & Fast Food"
    assert "(Ad)" not in gwalia["name"]
    assert gwalia["url_type"] == "search"
    # Encodes %26 for ampersand, + for spaces, and appends the requested dish
    assert gwalia["url"] == "https://www.swiggy.com/search?query=Gwalia+Sweets+%26+Fast+Food+pani+puri"

    # Check 2: Radhika's with requested dish pani puri
    radhika = results[1]
    assert radhika["name"] == "Radhika's Authentic South Indian Food"
    assert radhika["url_type"] == "search"
    # %27 for apostrophe, + for spaces
    assert radhika["url"] == "https://www.swiggy.com/search?query=Radhika%27s+Authentic+South+Indian+Food+pani+puri"


# ==============================================================================
# 2. Direct Restaurant URL Is Never Fabricated from Name Alone
# ==============================================================================

@pytest.mark.asyncio
async def test_direct_restaurant_url_never_fabricated(mock_swiggy_provider):
    """Requirement 3: Never invent deep links like /restaurants/{id} or /city/slug when not provided."""
    session = FakeSession(
        tools=[FakeTool("search_restaurants"), FakeTool("search_menu")],
        call_map={
            "search_restaurants": {
                "restaurants": [
                    {"id": "tea_post_999", "name": "Tea Post (Ad)", "rating": 4.0}
                ]
            },
            "search_menu": {"items": []}
        }
    )

    with mock_session_execution(mock_swiggy_provider, session):
        results = await mock_swiggy_provider.search_nearby_restaurants(23.0225, 72.5714, query="chaat")

    assert len(results) == 1
    # Should not fabricate swiggy.com/restaurants/tea-post-999
    assert "/restaurants/" not in results[0]["url"]
    assert results[0]["url_type"] == "search"
    assert results[0]["url"] == "https://www.swiggy.com/search?query=Tea+Post+chaat"


# ==============================================================================
# 3. Association Between Name and URL Stays Intact
# ==============================================================================

@pytest.mark.asyncio
async def test_restaurant_name_and_url_remain_associated(mock_swiggy_provider):
    """Requirement 4: Names and URLs remain paired with the respective restaurant throughout."""
    session = FakeSession(
        tools=[FakeTool("search_restaurants"), FakeTool("search_menu")],
        call_map={
            "search_restaurants": {
                "restaurants": [
                    {"id": "r1", "name": "Shreeji Krupa Bombay Vadapav", "rating": 4.5},
                    {"id": "r2", "name": "Das Khaman Outlet", "rating": 4.2}
                ]
            },
            "search_menu": {"items": []}
        }
    )

    with mock_session_execution(mock_swiggy_provider, session):
        results = await mock_swiggy_provider.search_nearby_restaurants(23.0225, 72.5714, query="vadapav")

    engine = RecommendationEngine()
    ranked = engine.rank(results, user_message="vadapav", tool_args={"query": "vadapav"})

    for r in ranked:
        rest = r.restaurant
        encoded_name = urllib.parse.quote_plus(rest["name"], safe="")
        assert encoded_name in rest["url"]


# ==============================================================================
# 4. Waffle Request with Confirmed Waffle Menu Items
# ==============================================================================

@pytest.mark.asyncio
async def test_waffle_request_with_confirmed_waffle_menu_items(mock_swiggy_provider):
    """Requirement 5: 'I wanna have waffles' extracts waffle, retrieves menu, and generates restaurant+dish search URL."""
    session = FakeSession(
        tools=[FakeTool("search_restaurants"), FakeTool("search_menu")],
        call_map={
            "search_restaurants": {
                "restaurants": [
                    {
                        "id": "belgian_waffle_1",
                        "name": "The Belgian Waffle Co. (Ad)",
                        "rating": 4.6,
                        "cuisines": ["Desserts", "Waffles", "Bakery"]
                    }
                ]
            },
            "search_menu": {
                "items": [
                    {
                        "restaurantId": "belgian_waffle_1",
                        "restaurantName": "The Belgian Waffle Co.",
                        "name": "chocolate waffle",
                        "price": 160,
                        "rating": 4.7,
                        "inStock": True
                    }
                ]
            }
        }
    )

    with mock_session_execution(mock_swiggy_provider, session):
        results = await mock_swiggy_provider.search_nearby_restaurants(23.0225, 72.5714, query="I wanna have waffles")

    assert len(results) == 1
    waffle_rest = results[0]
    assert waffle_rest["name"] == "The Belgian Waffle Co."
    assert waffle_rest["match_category"] == "confirmed"
    assert waffle_rest["dish_availability"] == "confirmed"
    assert len(waffle_rest["matched_items"]) == 1
    assert waffle_rest["matched_items"][0]["name"] == "chocolate waffle"

    # Search URL combines restaurant name and verified dish item
    assert waffle_rest["url"] == "https://www.swiggy.com/search?query=The+Belgian+Waffle+Co.+chocolate+waffle"
    assert waffle_rest["url_type"] == "search"


# ==============================================================================
# 5. Successfully Retrieved Menu without Requested Dish -> Unavailable
# ==============================================================================

@pytest.mark.asyncio
async def test_successfully_retrieved_menu_without_requested_dish_is_unavailable(mock_swiggy_provider):
    """Requirement 6: When menu search succeeds but does not contain the dish, mark unavailable (not unverified)."""
    session = FakeSession(
        tools=[FakeTool("search_restaurants"), FakeTool("search_menu")],
        call_map={
            "search_restaurants": {
                "restaurants": [
                    {"id": "tea_post", "name": "Tea Post", "rating": 4.2}
                ]
            },
            "search_menu": {
                # Items returned for other places, none for Tea Post
                "items": [
                    {"restaurantId": "other_place", "name": "Pani Puri", "price": 50}
                ]
            }
        }
    )

    with mock_session_execution(mock_swiggy_provider, session):
        results = await mock_swiggy_provider.search_nearby_restaurants(23.0225, 72.5714, query="pani puri")

    assert len(results) >= 1
    tea_post = next(r for r in results if r["id"] == "tea_post")
    assert tea_post["match_category"] == "unverified"
    assert tea_post["dish_availability"] == "unavailable"
    assert tea_post["matched_items"] == []


# ==============================================================================
# 6. Restaurant Whose Menu Is Unavailable (API Failure) -> Unverified
# ==============================================================================

@pytest.mark.asyncio
async def test_menu_api_failure_leaves_dish_unverified_not_unavailable(mock_swiggy_provider):
    """Requirement 7: Menu API failure must NOT mark the dish unavailable; it remains unverified."""
    def fail_menu(args):
        raise RuntimeError("Menu search endpoint timed out")

    session = FakeSession(
        tools=[FakeTool("search_restaurants"), FakeTool("search_menu")],
        call_map={
            "search_restaurants": {
                "restaurants": [
                    {"id": "r1", "name": "Gwalia Sweets", "rating": 4.3}
                ]
            },
            "search_menu": fail_menu
        }
    )

    with mock_session_execution(mock_swiggy_provider, session):
        results = await mock_swiggy_provider.search_nearby_restaurants(23.0225, 72.5714, query="dhokla")

    assert len(results) == 1
    # Must be unverified, NOT marked unavailable
    assert results[0]["dish_availability"] == "unverified"
    assert results[0]["match_category"] == "unverified"
    assert "could not be verified" in results[0]["match_reason"].lower()


@pytest.mark.asyncio
async def test_explicitly_out_of_stock_item_marked_unavailable(mock_swiggy_provider):
    """An item marked out of stock by provider is flagged as unavailable."""
    session = FakeSession(
        tools=[FakeTool("search_restaurants"), FakeTool("search_menu")],
        call_map={
            "search_restaurants": {
                "restaurants": [
                    {"id": "rest_oos", "name": "Chaat Express", "rating": 4.1}
                ]
            },
            "search_menu": {
                "items": [
                    {
                        "restaurantId": "rest_oos",
                        "restaurantName": "Chaat Express",
                        "name": "Sev Puri Chaat",
                        "price": 80,
                        "inStock": False,
                        "description": "Currently out of stock"
                    }
                ]
            }
        }
    )

    with mock_session_execution(mock_swiggy_provider, session):
        results = await mock_swiggy_provider.search_nearby_restaurants(23.0225, 72.5714, query="chaat")

    assert len(results) == 1
    assert results[0]["dish_availability"] == "unavailable"
    assert len(results[0]["matched_items"]) == 1
    assert results[0]["matched_items"][0]["is_available"] is False


# ==============================================================================
# 7. Ranking Engine: Confirmed vs Unverified
# ==============================================================================

def test_unrelated_restaurant_with_high_rating_cannot_outrank_confirmed_dish_match():
    """Unrelated café with high rating must not outrank a confirmed dish match."""
    engine = RecommendationEngine()

    restaurants = [
        {
            "id": "unverified_cafe",
            "name": "Starbucks Coffee",
            "rating": 4.9,
            "distance_meters": 500,
            "match_category": "unverified",
            "dish_availability": "unavailable",
            "matched_items": []
        },
        {
            "id": "confirmed_place",
            "name": "Pakwan Pani Puri Center",
            "rating": 4.1,
            "distance_meters": 2000,
            "match_category": "confirmed",
            "dish_availability": "confirmed",
            "matched_items": [{"name": "Pani Puri Plate", "price": 50, "rating": 4.2}]
        }
    ]

    ranked = engine.rank(
        restaurants=restaurants,
        user_message="where can I get pani puri nearby?",
        tool_args={"query": "pani puri"}
    )

    # Confirmed dish match must be #1
    assert ranked[0].restaurant["id"] == "confirmed_place"
    assert ranked[0].match_category == "confirmed"
    assert ranked[0].score > ranked[1].score

    # Unverified café's final score must be capped
    assert ranked[1].score <= 35.0
    assert ranked[1].match_category == "unverified"


def test_no_verified_matches_capped_honestly():
    """When all results are unavailable/unverified, scores reflect unverified status honestly."""
    engine = RecommendationEngine()

    restaurants = [
        {
            "id": "r1",
            "name": "Tea Post",
            "rating": 4.0,
            "distance_meters": 800,
            "match_category": "unverified",
            "dish_availability": "unavailable",
            "matched_items": []
        }
    ]

    ranked = engine.rank(
        restaurants=restaurants,
        user_message="dhokla",
        tool_args={"query": "dhokla"}
    )

    assert ranked[0].match_category == "unverified"
    assert ranked[0].dish_availability == "unavailable"
    assert ranked[0].score <= 35.0


# ==============================================================================
# 8. Multi-Dish Query Extraction & Cross-Menu Matching
# ==============================================================================

@pytest.mark.asyncio
async def test_multi_dish_query_searches_multiple_menu_items(mock_swiggy_provider):
    """Multi-dish prompt 'Pani Puri, Chaat, and Dhokla' searches distinct items across menus."""
    menu_searches = []

    def handle_menu_search(args):
        q = args.get("query", "").lower()
        menu_searches.append(q)
        if "pani puri" in q:
            return {
                "items": [
                    {"restaurantId": "r_pani", "restaurantName": "Pani Puri Place", "name": "Pani Puri", "price": 40}
                ]
            }
        elif "dhokla" in q:
            return {
                "items": [
                    {"restaurantId": "r_dhokla", "restaurantName": "Das Khaman Dhokla", "name": "Khaman Dhokla", "price": 60}
                ]
            }
        return {"items": []}

    session = FakeSession(
        tools=[FakeTool("search_restaurants"), FakeTool("search_menu")],
        call_map={
            "search_restaurants": {
                "restaurants": [
                    {"id": "r_pani", "name": "Pani Puri Place", "rating": 4.3}
                ]
            },
            "search_menu": handle_menu_search
        }
    )

    with mock_session_execution(mock_swiggy_provider, session):
        results = await mock_swiggy_provider.search_nearby_restaurants(
            23.0225, 72.5714, query="Pani Puri, Chaat, and Dhokla"
        )

    # Verifies multiple menu search passes were executed for the separate dishes
    assert any("pani puri" in s for s in menu_searches)
    assert any("dhokla" in s for s in menu_searches)
    assert any("chaat" in s for s in menu_searches)

    # Both confirmed dishes from different restaurants are found
    rest_ids = [r["id"] for r in results]
    assert "r_pani" in rest_ids
    assert "r_dhokla" in rest_ids


# ==============================================================================
# 9. Pronoun Follow-Up Resolution in Agent
# ==============================================================================

@pytest.mark.asyncio
async def test_agent_resolves_food_pronoun_followup_from_assistant_message():
    """Agent resolves 'suggest me places for this nearby' to dishes recommended in previous turn."""
    agent = CraveAIAgent()
    agent.client = MagicMock()

    agent._cached_groq_tools = [
        {"type": "function", "function": {"name": "search_nearby_restaurants", "parameters": {}}}
    ]
    agent.mcp_tools_cache = {
        "search_nearby_restaurants": ("restaurant", MagicMock())
    }

    mock_choice = MagicMock()
    mock_choice.message.content = "Here are places for Pani Puri, Chaat, and Dhokla."
    mock_choice.message.tool_calls = None
    agent.client.chat.completions.create = AsyncMock(return_value=MagicMock(choices=[mock_choice]))

    conversation = [
        {"role": "user", "content": "What food do you recommend for today's weather?"},
        {
            "role": "assistant",
            "content": (
                "Here are food recommendations for today:\n"
                "- **Pani Puri**: Crisp puris with mint water.\n"
                "- **Chaat**: Spicy street snack.\n"
                "- **Dhokla**: Steamed fermented cake."
            )
        }
    ]

    results = []
    async for chunk in agent.chat_stream(
        user_message="suggest me places for this nearby",
        conversation=conversation,
        location={"latitude": 23.0225, "longitude": 72.5714}
    ):
        results.append(json.loads(chunk))

    called_messages = agent.client.chat.completions.create.call_args[1]["messages"]
    current_user_msg = [m for m in called_messages if m["role"] == "user"][-1]["content"]

    # Injected context must specify the dishes from the previous turn
    assert "Pani Puri" in current_user_msg
    assert "Chaat" in current_user_msg
    assert "Dhokla" in current_user_msg
    assert "Do NOT search for generic food or the literal word 'this'" in current_user_msg


# ==============================================================================
# 10. Strict Restaurant ID Verification & Global Results
# ==============================================================================

@pytest.mark.asyncio
async def test_strict_restaurant_id_verification_prevents_cross_restaurant_match(mock_swiggy_provider):
    """Requirement 3: An item is only confirmed if item's restaurant_id strictly matches the restaurant card ID."""
    session = FakeSession(
        tools=[FakeTool("search_restaurants"), FakeTool("search_menu")],
        call_map={
            "search_restaurants": {
                "restaurants": [
                    # Restaurant with ID 937219
                    {"id": "937219", "name": "Hocco Eatery", "rating": 4.5}
                ]
            },
            # search_menu returns item belonging to a DIFFERENT restaurant ID (40837)
            "search_menu": {
                "items": [
                    {
                        "name": "Triple Chocomelt Waffle",
                        "price": 195,
                        "restaurantName": "Hocco Eatery",
                        "restaurantId": "40837",  # Mismatched ID!
                        "is_available": True
                    }
                ]
            }
        }
    )

    with mock_session_execution(mock_swiggy_provider, session):
        results = await mock_swiggy_provider.search_nearby_restaurants(23.0225, 72.5714, query="waffle")

    # The restaurant card for 937219 must NOT claim the item from restaurant 40837
    hocco_card = next(r for r in results if r["id"] == "937219")
    assert hocco_card["match_category"] != "confirmed"
    assert len(hocco_card["matched_items"]) == 0


@pytest.mark.asyncio
async def test_global_search_results_without_restaurant_id_are_not_confirmed(mock_swiggy_provider):
    """Requirement 3: If provider only returns global search results with no restaurant ID, do not claim restaurant verification."""
    session = FakeSession(
        tools=[FakeTool("search_restaurants"), FakeTool("search_menu")],
        call_map={
            "search_restaurants": {
                "restaurants": [
                    {"id": "rest_corner", "name": "Great Waffle Corner", "rating": 4.1}
                ]
            },
            "search_menu": {
                "items": [
                    {
                        "name": "Chocolate Waffle",
                        "price": 150,
                        "restaurantName": "",
                        "restaurantId": "",  # Missing restaurant ID!
                        "is_available": True
                    }
                ]
            }
        }
    )

    with mock_session_execution(mock_swiggy_provider, session):
        results = await mock_swiggy_provider.search_nearby_restaurants(23.0225, 72.5714, query="waffle")

    rest_card = next(r for r in results if r["id"] == "rest_corner")
    assert rest_card["match_category"] != "confirmed"
    assert rest_card["dish_availability"] != "confirmed"


# ==============================================================================
# 11. Packaged Products vs Freshly Prepared Food Relevance
# ==============================================================================

def test_product_type_classification():
    """Requirement 4: Packaged items and sides are categorized accurately."""
    p_pkg, l_pkg = SwiggyRestaurantProvider.classify_item_product_type("Chocolate Waffle Tubes (90g)", "waffle")
    assert p_pkg == "packaged"
    assert "Packaged" in l_pkg

    p_side, l_side = SwiggyRestaurantProvider.classify_item_product_type("Waffle Fries (100 Gm)", "waffle")
    assert p_side == "side"

    p_fresh, l_fresh = SwiggyRestaurantProvider.classify_item_product_type("Triple Chocomelt Waffle", "waffle")
    assert p_fresh == "prepared"

    p_unspec, l_unspec = SwiggyRestaurantProvider.classify_item_product_type("Mysterious Item", "waffle")
    assert p_unspec == "unspecified"


def test_packaged_products_do_not_rank_alongside_fresh_waffles():
    """Requirement 4: Packaged waffle tubes score significantly lower than freshly prepared waffles."""
    fresh_waffle_rest = {
        "id": "fresh_1",
        "name": "The Belgian Waffle Co.",
        "rating": 4.6,
        "match_category": "confirmed",
        "matched_items": [
            {"name": "Triple Chocomelt Waffle", "price": 195, "product_type": "prepared"}
        ]
    }

    packaged_tubes_rest = {
        "id": "pkg_1",
        "name": "Supermarket Bakery",
        "rating": 4.8,  # Higher rating
        "match_category": "confirmed",
        "matched_items": [
            {"name": "Chocolate Waffle Tubes (90g)", "price": 120, "product_type": "packaged"}
        ]
    }

    score_fresh = DeterministicScorer.score_food_match(fresh_waffle_rest, "waffle")
    score_pkg = DeterministicScorer.score_food_match(packaged_tubes_rest, "waffle")

    assert score_fresh >= 85.0
    assert score_pkg <= 40.0

    engine = RecommendationEngine()
    ranked = engine.rank([packaged_tubes_rest, fresh_waffle_rest], "I wanna have waffles", {"query": "waffle"})

    # Fresh waffle restaurant must rank #1 over packaged tubes restaurant
    assert ranked[0].restaurant["id"] == "fresh_1"
    assert ranked[1].restaurant["id"] == "pkg_1"
    assert ranked[0].score > ranked[1].score


# ==============================================================================
# 12. Search URL Clean Generation with Ampersands
# ==============================================================================

@pytest.mark.asyncio
async def test_search_url_cleans_ampersand_into_and(mock_swiggy_provider):
    """Requirement 2 & 5: Search URLs replace '&' with 'and' to prevent Swiggy query syntax errors."""
    session = FakeSession(
        tools=[FakeTool("search_restaurants"), FakeTool("search_menu")],
        call_map={
            "search_restaurants": {
                "restaurants": [
                    {
                        "id": "589130",
                        "name": "Oven The Bakery & Cafe",
                        "rating": 4.2
                    }
                ]
            },
            "search_menu": {
                "items": [
                    {
                        "name": "Nutella Waffle",
                        "price": 379,
                        "restaurantName": "Oven The Bakery & Cafe",
                        "restaurantId": "589130",
                        "is_available": True
                    }
                ]
            }
        }
    )

    with mock_session_execution(mock_swiggy_provider, session):
        results = await mock_swiggy_provider.search_nearby_restaurants(23.0225, 72.5714, query="waffle")

    oven = next(r for r in results if r["id"] == "589130")
    # Must correctly percent-encode '&' as '%26', spaces as '+', and include restaurant name and dish
    assert "%26" in oven["url"]
    assert "Oven+The+Bakery+%26+Cafe+Nutella+Waffle" in oven["url"]


# ==============================================================================
# 13. Search URL Fallback Strategies (Step 4 Requirements)
# ==============================================================================

@pytest.mark.asyncio
async def test_merged_restaurant_uses_dish_focused_fallback(mock_swiggy_provider):
    """Step 4.1 & 4.2: Merged restaurant not in local directory uses dish-focused search fallback."""
    session = FakeSession(
        tools=[FakeTool("search_restaurants"), FakeTool("search_menu")],
        call_map={
            # search_restaurants does NOT return Oven The Bakery & Cafe
            "search_restaurants": {
                "restaurants": [
                    {"id": "710033", "name": "The Belgian Waffle Co.", "rating": 4.6}
                ]
            },
            # search_menu returns Milk Waffle for Oven The Bakery & Cafe (restaurantId: 589130)
            "search_menu": {
                "items": [
                    {
                        "name": "Milk Waffle",
                        "price": 299,
                        "restaurantName": "Oven The Bakery & Cafe",
                        "restaurantId": "589130",
                        "is_available": True
                    }
                ]
            }
        }
    )

    with mock_session_execution(mock_swiggy_provider, session):
        results = await mock_swiggy_provider.search_nearby_restaurants(23.0225, 72.5714, query="Milk Waffle")

    oven = next(r for r in results if r["id"] == "589130")
    # Primary URL must use dish-focused fallback because combined query returns empty on storefront
    assert oven["url"] == "https://www.swiggy.com/search?query=Milk+Waffle"
    assert oven["url_type"] == "dish_fallback"
    # Secondary fallback provides restaurant name
    assert "Oven+The+Bakery+%26+Cafe" in oven["fallback_url"]
    assert oven["fallback_url_type"] == "restaurant_fallback"


def test_dish_only_fallback_build_search_urls():
    """Step 4.2: build_swiggy_search_urls generates dish-only fallback for non-local restaurants."""
    urls = SwiggyRestaurantProvider.build_swiggy_search_urls(
        rest_name="Oven The Bakery & Cafe",
        dish_name="Milk Waffle",
        is_local_restaurant=False
    )
    assert urls["url"] == "https://www.swiggy.com/search?query=Milk+Waffle"
    assert urls["url_type"] == "dish_fallback"
    assert urls["fallback_url"] == "https://www.swiggy.com/search?query=Oven+The+Bakery+%26+Cafe"
    assert urls["fallback_url_type"] == "restaurant_fallback"


def test_restaurant_only_search_fallback():
    """Step 4.3: build_swiggy_search_urls generates restaurant-only search when no dish is requested."""
    urls = SwiggyRestaurantProvider.build_swiggy_search_urls(
        rest_name="The Belgian Waffle Co.",
        dish_name="",
        is_local_restaurant=True
    )
    assert urls["url"] == "https://www.swiggy.com/search?query=The+Belgian+Waffle+Co."
    assert urls["url_type"] == "restaurant_search"


def test_url_encoding_special_characters():
    """Step 4.4: Correct percent encoding of ampersands, apostrophes, spaces, and parentheses."""
    urls = SwiggyRestaurantProvider.build_swiggy_search_urls(
        rest_name="Gwalia Sweets & Fast Food",
        dish_name="Kitkat Waffle (1 Pc)",
        is_local_restaurant=True
    )
    # RFC 3986 percent encoding: & -> %26, ( -> %28, ) -> %29, ' ' -> +
    assert "%26" in urls["url"]
    assert "%28" in urls["url"]
    assert "%29" in urls["url"]
    assert "Gwalia+Sweets+%26+Fast+Food+Kitkat+Waffle+%281+Pc%29" in urls["url"]


@pytest.mark.asyncio
async def test_dish_only_search_does_not_falsely_confirm_menu_availability(mock_swiggy_provider):
    """Step 3 & 4.5: Successful dish-only search does not mark an unrelated restaurant as confirmed."""
    session = FakeSession(
        tools=[FakeTool("search_restaurants"), FakeTool("search_menu")],
        call_map={
            "search_restaurants": {
                "restaurants": [
                    # A nearby restaurant with ID 999999
                    {"id": "999999", "name": "Corner Cafe", "rating": 4.0}
                ]
            },
            # search_menu returns Milk Waffle belonging to a completely different restaurant ID (589130)
            "search_menu": {
                "items": [
                    {
                        "name": "Milk Waffle",
                        "price": 299,
                        "restaurantName": "Oven The Bakery & Cafe",
                        "restaurantId": "589130",
                        "is_available": True
                    }
                ]
            }
        }
    )

    with mock_session_execution(mock_swiggy_provider, session):
        results = await mock_swiggy_provider.search_nearby_restaurants(23.0225, 72.5714, query="Milk Waffle")

    corner_cafe = next(r for r in results if r["id"] == "999999")
    # Menu availability MUST NOT be confirmed for 999999
    assert corner_cafe["match_category"] != "confirmed"
    assert corner_cafe["dish_availability"] != "confirmed"
    assert len(corner_cafe["matched_items"]) == 0


