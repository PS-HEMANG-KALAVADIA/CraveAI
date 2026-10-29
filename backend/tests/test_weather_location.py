import pytest
import sys
import os
import json
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.services.geocoding import extract_city, geocode_city
from app.agent.agent import CraveAIAgent

# Unit tests for city extraction
def test_extract_city():
    # Explicit city in query
    assert extract_city("What's the weather in Ahmedabad?") == "Ahmedabad"
    assert extract_city("Will it rain tomorrow in Ahmedabad?") == "Ahmedabad"
    assert extract_city("Ahmedabad weather") == "Ahmedabad"
    assert extract_city("Weather for Jaipur") == "Jaipur"
    assert extract_city("Can you tell me the weather in Mumbai tomorrow?") == "Mumbai"
    assert extract_city("Ahmedabad") == "Ahmedabad"

    # Queries without explicit cities should return None
    assert extract_city("What's the weather today?") is None
    assert extract_city("How is the weather right now?") is None
    assert extract_city("Will it rain today?") is None
    assert extract_city("Find me food nearby") is None
    assert extract_city("I want spicy food") is None


@pytest.mark.asyncio
async def test_geocode_city_success():
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "name": "Ahmedabad",
                    "latitude": 23.02579,
                    "longitude": 72.58727,
                    "country": "India"
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        geo = await geocode_city("Ahmedabad")
        assert geo is not None
        assert geo["name"] == "Ahmedabad"
        assert geo["latitude"] == 23.02579
        assert geo["longitude"] == 72.58727


@pytest.mark.asyncio
async def test_geocode_city_not_found():
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        geo = await geocode_city("NonExistentCityXYZ123")
        assert geo is None  # Never fabricate coordinates


@pytest.mark.asyncio
async def test_weather_today_with_browser_location():
    """
    Test: 'What's the weather today?' with browser location available
    -> automatically fetch weather using browser coordinates.
    """
    agent = CraveAIAgent()
    agent.client = MagicMock()

    # Mock cached tools
    agent._cached_groq_tools = [
        {"type": "function", "function": {"name": "get_current_weather", "parameters": {}}}
    ]
    agent.mcp_tools_cache = {
        "get_current_weather": ("weather", MagicMock())
    }

    # Simulate Groq calling get_current_weather with browser location coordinates
    fake_tool_call = MagicMock()
    fake_tool_call.id = "call_weather_1"
    fake_tool_call.type = "function"
    fake_tool_call.function.name = "get_current_weather"
    fake_tool_call.function.arguments = json.dumps({"latitude": 23.0225, "longitude": 72.5714})

    mock_choice_1 = MagicMock()
    mock_choice_1.message.content = None
    mock_choice_1.message.tool_calls = [fake_tool_call]

    mock_choice_2 = MagicMock()
    mock_choice_2.message.content = "The current weather is 32°C and sunny."
    mock_choice_2.message.tool_calls = None

    agent.client.chat.completions.create = AsyncMock(side_effect=[
        MagicMock(choices=[mock_choice_1]),
        MagicMock(choices=[mock_choice_2])
    ])

    with patch.object(agent, "execute_tool", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {
            "temperature": 32,
            "weather_condition": "Clear sky",
            "normalized_condition": "hot"
        }

        results = []
        async for chunk in agent.chat_stream(
            user_message="What's the weather today?",
            conversation=[],
            location={"latitude": 23.0225, "longitude": 72.5714}
        ):
            results.append(json.loads(chunk))

        # Verify tool was called
        mock_exec.assert_called_once_with(
            "get_current_weather",
            {"latitude": 23.0225, "longitude": 72.5714}
        )

        final_res = next(r for r in results if r.get("type") == "result")
        assert any(t.startswith("get_current_weather") for t in final_res["tools_used"])
        assert "search_nearby_restaurants" not in final_res["tools_used"]


@pytest.mark.asyncio
async def test_weather_in_city():
    """
    Test: 'What's the weather in Ahmedabad?'
    -> resolve the city via geocoding and fetch weather.
    """
    agent = CraveAIAgent()
    agent.client = MagicMock()

    agent._cached_groq_tools = [
        {"type": "function", "function": {"name": "get_current_weather", "parameters": {}}}
    ]
    agent.mcp_tools_cache = {
        "get_current_weather": ("weather", MagicMock())
    }

    fake_tool_call = MagicMock()
    fake_tool_call.id = "call_weather_2"
    fake_tool_call.type = "function"
    fake_tool_call.function.name = "get_current_weather"
    fake_tool_call.function.arguments = json.dumps({"latitude": 23.02579, "longitude": 72.58727})

    mock_choice_1 = MagicMock()
    mock_choice_1.message.content = None
    mock_choice_1.message.tool_calls = [fake_tool_call]

    mock_choice_2 = MagicMock()
    mock_choice_2.message.content = "In Ahmedabad, the weather is 30°C."
    mock_choice_2.message.tool_calls = None

    agent.client.chat.completions.create = AsyncMock(side_effect=[
        MagicMock(choices=[mock_choice_1]),
        MagicMock(choices=[mock_choice_2])
    ])

    with patch("app.agent.agent.geocode_city", new_callable=AsyncMock) as mock_geo, \
         patch.object(agent, "execute_tool", new_callable=AsyncMock) as mock_exec:

        mock_geo.return_value = {
            "name": "Ahmedabad",
            "latitude": 23.02579,
            "longitude": 72.58727
        }
        mock_exec.return_value = {
            "temperature": 30,
            "weather_condition": "Clear sky",
            "normalized_condition": "pleasant"
        }

        results = []
        async for chunk in agent.chat_stream(
            user_message="What's the weather in Ahmedabad?",
            conversation=[],
            location=None
        ):
            results.append(json.loads(chunk))

        mock_geo.assert_called_once_with("Ahmedabad")
        mock_exec.assert_called_once_with(
            "get_current_weather",
            {"latitude": 23.02579, "longitude": 72.58727}
        )

        final_res = next(r for r in results if r.get("type") == "result")
        assert any(t.startswith("get_current_weather") for t in final_res["tools_used"])
        assert "search_nearby_restaurants" not in final_res["tools_used"]


@pytest.mark.asyncio
async def test_weather_permission_denied_asks_for_city():
    """
    Test: 'What's the weather today?' with location permission denied
    -> ask for a city name, not coordinates.
    """
    agent = CraveAIAgent()
    agent.client = MagicMock()

    agent._cached_groq_tools = [
        {"type": "function", "function": {"name": "get_current_weather", "parameters": {}}}
    ]
    agent.mcp_tools_cache = {
        "get_current_weather": ("weather", MagicMock())
    }

    # Model asks user for city name directly without calling any tools
    mock_choice = MagicMock()
    mock_choice.message.content = "Could you please tell me which city you would like the weather for?"
    mock_choice.message.tool_calls = None

    agent.client.chat.completions.create = AsyncMock(return_value=MagicMock(choices=[mock_choice]))

    results = []
    async for chunk in agent.chat_stream(
        user_message="What's the weather today?",
        conversation=[],
        location=None,
        location_status="denied"
    ):
        results.append(json.loads(chunk))

    # Verify context passed to Groq instructs asking for city name and forbids asking for coordinates
    called_messages = agent.client.chat.completions.create.call_args[1]["messages"]
    user_msg_content = next(m["content"] for m in called_messages if m["role"] == "user")
    assert "User location coordinates are unavailable" in user_msg_content
    assert "ask for a city name" in user_msg_content
    assert "Do NOT ask for latitude/longitude" in user_msg_content

    final_res = next(r for r in results if r.get("type") == "result")
    assert len(final_res["tools_used"]) == 0
    assert "city" in final_res["response"].lower()
    assert "latitude" not in final_res["response"].lower()
    assert "longitude" not in final_res["response"].lower()


@pytest.mark.asyncio
async def test_rain_tomorrow_forecast_tool():
    """
    Test: 'Will it rain tomorrow in Ahmedabad?'
    -> call the forecast tool (get_weather_forecast).
    """
    agent = CraveAIAgent()
    agent.client = MagicMock()

    agent._cached_groq_tools = [
        {"type": "function", "function": {"name": "get_weather_forecast", "parameters": {}}}
    ]
    agent.mcp_tools_cache = {
        "get_weather_forecast": ("weather", MagicMock())
    }

    fake_tool_call = MagicMock()
    fake_tool_call.id = "call_forecast_1"
    fake_tool_call.type = "function"
    fake_tool_call.function.name = "get_weather_forecast"
    fake_tool_call.function.arguments = json.dumps({"latitude": 23.02579, "longitude": 72.58727})

    mock_choice_1 = MagicMock()
    mock_choice_1.message.content = None
    mock_choice_1.message.tool_calls = [fake_tool_call]

    mock_choice_2 = MagicMock()
    mock_choice_2.message.content = "There is a 75% chance of rain tomorrow in Ahmedabad."
    mock_choice_2.message.tool_calls = None

    agent.client.chat.completions.create = AsyncMock(side_effect=[
        MagicMock(choices=[mock_choice_1]),
        MagicMock(choices=[mock_choice_2])
    ])

    with patch("app.agent.agent.geocode_city", new_callable=AsyncMock) as mock_geo, \
         patch.object(agent, "execute_tool", new_callable=AsyncMock) as mock_exec:

        mock_geo.return_value = {
            "name": "Ahmedabad",
            "latitude": 23.02579,
            "longitude": 72.58727
        }
        mock_exec.return_value = {
            "forecast": [
                {"date": "2026-10-15", "precipitation_probability": 75, "weather_condition": "Moderate rain"}
            ]
        }

        results = []
        async for chunk in agent.chat_stream(
            user_message="Will it rain tomorrow in Ahmedabad?",
            conversation=[],
            location=None
        ):
            results.append(json.loads(chunk))

        mock_exec.assert_called_once_with(
            "get_weather_forecast",
            {"latitude": 23.02579, "longitude": 72.58727}
        )

        final_res = next(r for r in results if r.get("type") == "result")
        assert "get_weather_forecast" in final_res["tools_used"]
        assert "search_nearby_restaurants" not in final_res["tools_used"]
