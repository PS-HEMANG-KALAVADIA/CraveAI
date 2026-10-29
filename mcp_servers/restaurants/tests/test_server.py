import pytest
import json
import sys
import os
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from providers.mock import MockRestaurantProvider
from providers.yelp import YelpRestaurantProvider
from providers.swiggy import SwiggyRestaurantProvider
from server import call_tool, set_provider, get_provider

@pytest.mark.asyncio
async def test_mock_provider_search():
    provider = MockRestaurantProvider()
    results = await provider.search_nearby_restaurants(latitude=23.0, longitude=72.0, radius_meters=5000)
    assert len(results) >= 3
    
    results_gujarati = await provider.search_nearby_restaurants(latitude=23.0, longitude=72.0, query="Gujarati")
    assert len(results_gujarati) == 1
    assert results_gujarati[0]["name"] == "Rajwada Thali"
    
    results_spicy = await provider.search_nearby_restaurants(latitude=23.0, longitude=72.0, query="Spicy")
    assert len(results_spicy) == 1
    assert results_spicy[0]["name"] == "Spicy Bite Cafe"

@pytest.mark.asyncio
async def test_yelp_provider_search():
    provider = YelpRestaurantProvider(api_key="test_key")
    
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "businesses": [
            {
                "id": "yelp_1",
                "name": "Real Yelp Restaurant",
                "rating": 4.5,
                "distance": 1200.5,
                "price": "$$",
                "categories": [{"title": "Gujarati"}],
                "location": {"display_address": ["Street 1"]},
                "is_closed": False,
                "url": "http://yelp.com"
            }
        ]
    }
    
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        results = await provider.search_nearby_restaurants(
            latitude=23.0, 
            longitude=72.0, 
            query="Gujarati", 
            radius_meters=5000, 
            price_tier="$$"
        )
        
        assert len(results) == 1
        assert results[0]["name"] == "Real Yelp Restaurant"
        assert results[0]["distance_meters"] == 1200

@pytest.mark.asyncio
async def test_no_mock_fallback_default_is_swiggy():
    """Verify that get_provider() defaults to swiggy and NEVER silently falls back to mock."""
    with patch.dict(os.environ, {}, clear=True):
        provider = get_provider()
        assert isinstance(provider, SwiggyRestaurantProvider)
        assert not isinstance(provider, MockRestaurantProvider)

@pytest.mark.asyncio
async def test_mcp_tool_search_nearby_with_mock():
    set_provider(MockRestaurantProvider())
    result = await call_tool("search_nearby_restaurants", {
        "latitude": 23.0,
        "longitude": 72.0,
        "query": "Kachori"
    })
    
    content = json.loads(result[0].text)
    assert "restaurants" in content
    assert len(content["restaurants"]) == 1
    assert content["restaurants"][0]["name"] == "The Grand Kachori House"

@pytest.mark.asyncio
async def test_mcp_tool_empty_results():
    set_provider(MockRestaurantProvider())
    result = await call_tool("search_nearby_restaurants", {
        "latitude": 23.0,
        "longitude": 72.0,
        "query": "NonExistentFood1234"
    })
    
    content = json.loads(result[0].text)
    assert "message" in content
    assert "No restaurants found" in content["message"]

@pytest.mark.asyncio
async def test_mcp_tool_missing_coordinates():
    set_provider(MockRestaurantProvider())
    result = await call_tool("search_nearby_restaurants", {
        "query": "Pani Puri"
    })
    content = json.loads(result[0].text)
    assert "error" in content
    assert "Missing required coordinates" in content["error"]

@pytest.mark.asyncio
async def test_mcp_tool_invalid_coordinates():
    set_provider(MockRestaurantProvider())
    result = await call_tool("search_nearby_restaurants", {
        "latitude": "not-a-number",
        "longitude": 72.0,
        "query": "Pani Puri"
    })
    content = json.loads(result[0].text)
    assert "error" in content
    assert "Invalid latitude or longitude" in content["error"]
