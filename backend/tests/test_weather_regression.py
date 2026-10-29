import pytest
import sys
import os
import json
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.agent.agent import CraveAIAgent

import importlib.util

weather_server_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "mcp_servers", "weather", "server.py")
spec = importlib.util.spec_from_file_location("weather_server_module", weather_server_path)
weather_server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(weather_server)
normalize_weather = weather_server.normalize_weather
WMO_CODES = weather_server.WMO_CODES


# 1. A clear/sunny Open-Meteo response is classified correctly
def test_clear_sunny_weather_classification():
    # WMO code 0 is Clear sky, 1 is Mainly clear
    assert WMO_CODES[0] == "Clear sky"
    assert WMO_CODES[1] == "Mainly clear"

    # Mild sunny/clear temperature
    assert normalize_weather(0, 24) == "clear"
    # Hot sunny/clear temperature
    assert normalize_weather(0, 34) == "hot"
    assert normalize_weather(1, 31) == "hot"

    # None of these should ever be classified as rainy
    assert normalize_weather(0, 24) != "rainy"
    assert normalize_weather(1, 24) != "rainy"


# 2. A rainy response is classified correctly
def test_rainy_weather_classification():
    # Drizzle, rain, showers
    assert normalize_weather(51, 20) == "rainy"  # Light drizzle
    assert normalize_weather(61, 22) == "rainy"  # Slight rain
    assert normalize_weather(63, 19) == "rainy"  # Moderate rain
    assert normalize_weather(65, 18) == "rainy"  # Heavy rain
    assert normalize_weather(80, 21) == "rainy"  # Rain showers
    assert normalize_weather(81, 23) == "rainy"  # Moderate rain showers


# 3. Cloudy conditions are not incorrectly classified as rain
def test_cloudy_weather_not_classified_as_rain():
    # Overcast, Fog
    assert normalize_weather(3, 22) == "cloudy"
    assert normalize_weather(45, 18) == "cloudy"
    assert normalize_weather(48, 16) == "cloudy"
    assert normalize_weather(3, 22) != "rainy"
    assert normalize_weather(45, 18) != "rainy"


# 4. Missing location is handled correctly (asks user for city name; error handled cleanly without crash or fabricated rain)
@pytest.mark.asyncio
async def test_missing_location_asks_for_city():
    agent = CraveAIAgent()
    agent.client = MagicMock()
    agent._cached_groq_tools = [
        {"type": "function", "function": {"name": "get_current_weather", "parameters": {}}}
    ]
    agent.mcp_tools_cache = {
        "get_current_weather": ("weather", MagicMock())
    }

    mock_choice = MagicMock()
    mock_choice.message.content = "To recommend food for your weather, could you tell me which city you are located in?"
    mock_choice.message.tool_calls = None
    agent.client.chat.completions.create = AsyncMock(return_value=MagicMock(choices=[mock_choice]))

    results = []
    async for chunk in agent.chat_stream(
        user_message="What food do you recommend for today's weather?",
        conversation=[],
        location=None,
        location_status="unavailable"
    ):
        results.append(json.loads(chunk))

    # Verify context warns that coordinates are unavailable and instructs asking for city
    called_messages = agent.client.chat.completions.create.call_args[1]["messages"]
    user_msg_content = next(m["content"] for m in called_messages if m["role"] == "user")
    assert "User location coordinates are unavailable" in user_msg_content
    assert "ask for a city name" in user_msg_content

    final_res = next(r for r in results if r.get("type") == "result")
    assert "city" in final_res["response"].lower()
    # Does not fabricate rain
    assert "raining" not in final_res["response"].lower()


# 5. API failure does not produce fabricated weather
@pytest.mark.asyncio
async def test_weather_api_failure_handled_truthfully():
    agent = CraveAIAgent()
    agent.client = MagicMock()
    agent._cached_groq_tools = [
        {"type": "function", "function": {"name": "get_current_weather", "parameters": {}}}
    ]
    agent.mcp_tools_cache = {
        "get_current_weather": ("weather", MagicMock())
    }

    # Simulate tool call to get_current_weather
    fake_tool_call = MagicMock()
    fake_tool_call.id = "call_weather_fail"
    fake_tool_call.type = "function"
    fake_tool_call.function.name = "get_current_weather"
    fake_tool_call.function.arguments = json.dumps({"latitude": 23.02, "longitude": 72.57})

    mock_choice_1 = MagicMock()
    mock_choice_1.message.content = None
    mock_choice_1.message.tool_calls = [fake_tool_call]

    mock_choice_2 = MagicMock()
    mock_choice_2.message.content = "I could not retrieve the live weather right now, but here are some classic food recommendations."
    mock_choice_2.message.tool_calls = None

    agent.client.chat.completions.create = AsyncMock(side_effect=[
        MagicMock(choices=[mock_choice_1]),
        MagicMock(choices=[mock_choice_2])
    ])

    with patch.object(agent, "execute_tool", new_callable=AsyncMock) as mock_exec:
        # Simulate API failure returning an error
        mock_exec.return_value = {"error": "Weather service returned 500 Internal Server Error"}

        results = []
        async for chunk in agent.chat_stream(
            user_message="What food do you recommend for today's weather?",
            conversation=[],
            location={"latitude": 23.02, "longitude": 72.57}
        ):
            results.append(json.loads(chunk))

        final_res = next(r for r in results if r.get("type") == "result")
        # Truthful failure recorded in activity trace
        assert any(t.startswith("get_current_weather_failed") for t in final_res["tools_used"])
        # Does not report successful weather check
        assert "get_current_weather" not in final_res["tools_used"]
        # Does not falsely claim rain
        assert "it is raining" not in final_res["response"].lower()


# 6. The agent uses the actual weather tool result to select get_food_for_weather
# 7. Sunny conditions do not invoke the rainy-food guide
@pytest.mark.asyncio
async def test_sunny_weather_selects_sunny_food_not_rainy():
    agent = CraveAIAgent()
    agent.client = MagicMock()
    agent._cached_groq_tools = [
        {"type": "function", "function": {"name": "get_current_weather", "parameters": {}}},
        {"type": "function", "function": {"name": "get_food_for_weather", "parameters": {}}}
    ]
    agent.mcp_tools_cache = {
        "get_current_weather": ("weather", MagicMock()),
        "get_food_for_weather": ("food", MagicMock())
    }

    # Turn 1: model calls get_current_weather
    call_1 = MagicMock()
    call_1.id = "call_w_1"
    call_1.type = "function"
    call_1.function.name = "get_current_weather"
    call_1.function.arguments = json.dumps({"latitude": 23.02, "longitude": 72.57})

    choice_1 = MagicMock()
    choice_1.message.content = None
    choice_1.message.tool_calls = [call_1]

    # Turn 2: model sees "Clear sky" (29°C) and calls get_food_for_weather with "clear"
    call_2 = MagicMock()
    call_2.id = "call_f_1"
    call_2.type = "function"
    call_2.function.name = "get_food_for_weather"
    call_2.function.arguments = json.dumps({"weather_condition": "clear"})

    choice_2 = MagicMock()
    choice_2.message.content = None
    choice_2.message.tool_calls = [call_2]

    # Turn 3: model synthesizes final response
    choice_3 = MagicMock()
    choice_3.message.content = "It's clear and sunny outside (29°C). For this weather, I recommend Pani Puri, Chaat, and Dhokla."
    choice_3.message.tool_calls = None

    agent.client.chat.completions.create = AsyncMock(side_effect=[
        MagicMock(choices=[choice_1]),
        MagicMock(choices=[choice_2]),
        MagicMock(choices=[choice_3])
    ])

    executed_tools = []
    async def mock_tool_exec(name, args):
        executed_tools.append((name, args))
        if name == "get_current_weather":
            return {
                "temperature": 29.0,
                "weather_condition": "Clear sky",
                "normalized_condition": "clear"
            }
        elif name == "get_food_for_weather":
            return {
                "pani_puri": {"name": "Pani Puri"},
                "chaat": {"name": "Chaat"},
                "dhokla": {"name": "Dhokla"}
            }
        return {}

    with patch.object(agent, "execute_tool", side_effect=mock_tool_exec):
        results = []
        async for chunk in agent.chat_stream(
            user_message="What food do you recommend for today's weather?",
            conversation=[],
            location={"latitude": 23.02, "longitude": 72.57}
        ):
            results.append(json.loads(chunk))

        final_res = next(r for r in results if r.get("type") == "result")

        # Verify get_food_for_weather was called with sunny/clear, NEVER rainy
        weather_calls = [args for (name, args) in executed_tools if name == "get_food_for_weather"]
        assert len(weather_calls) == 1
        condition_arg = weather_calls[0].get("weather_condition", "").lower()
        assert condition_arg in ("clear", "sunny", "clear sky", "hot", "pleasant")
        assert condition_arg != "rainy"

        # Verify activity trace recorded clear weather truthfully
        assert any("get_current_weather: Clear, 29°C" in t for t in final_res["tools_used"])
        # Verify response mentions sunny/clear recommendations
        assert "pani puri" in final_res["response"].lower()
        # Verify no rainy food suggestions
        assert "pyaaz kachori" not in final_res["response"].lower()
        assert "mirchi bada" not in final_res["response"].lower()


# 8. Rainy conditions can invoke the rainy-food guide
@pytest.mark.asyncio
async def test_rainy_weather_can_invoke_rainy_food():
    agent = CraveAIAgent()
    agent.client = MagicMock()
    agent._cached_groq_tools = [
        {"type": "function", "function": {"name": "get_current_weather", "parameters": {}}},
        {"type": "function", "function": {"name": "get_food_for_weather", "parameters": {}}}
    ]
    agent.mcp_tools_cache = {
        "get_current_weather": ("weather", MagicMock()),
        "get_food_for_weather": ("food", MagicMock())
    }

    call_1 = MagicMock()
    call_1.id = "call_w_rain"
    call_1.type = "function"
    call_1.function.name = "get_current_weather"
    call_1.function.arguments = json.dumps({"latitude": 23.02, "longitude": 72.57})

    choice_1 = MagicMock()
    choice_1.message.content = None
    choice_1.message.tool_calls = [call_1]

    call_2 = MagicMock()
    call_2.id = "call_f_rain"
    call_2.type = "function"
    call_2.function.name = "get_food_for_weather"
    call_2.function.arguments = json.dumps({"weather_condition": "rainy"})

    choice_2 = MagicMock()
    choice_2.message.content = None
    choice_2.message.tool_calls = [call_2]

    choice_3 = MagicMock()
    choice_3.message.content = "It's raining outside (22°C)! Fresh hot Pyaaz Kachori and Vada Pav are perfect."
    choice_3.message.tool_calls = None

    agent.client.chat.completions.create = AsyncMock(side_effect=[
        MagicMock(choices=[choice_1]),
        MagicMock(choices=[choice_2]),
        MagicMock(choices=[choice_3])
    ])

    executed_tools = []
    async def mock_tool_exec(name, args):
        executed_tools.append((name, args))
        if name == "get_current_weather":
            return {
                "temperature": 22.0,
                "weather_condition": "Moderate rain",
                "normalized_condition": "rainy"
            }
        elif name == "get_food_for_weather":
            return {
                "pyaaz_kachori": {"name": "Pyaaz Kachori"},
                "vada_pav": {"name": "Vada Pav"}
            }
        return {}

    with patch.object(agent, "execute_tool", side_effect=mock_tool_exec):
        results = []
        async for chunk in agent.chat_stream(
            user_message="What food do you recommend for today's weather?",
            conversation=[],
            location={"latitude": 23.02, "longitude": 72.57}
        ):
            results.append(json.loads(chunk))

        final_res = next(r for r in results if r.get("type") == "result")

        # Verify get_food_for_weather was called with rainy
        weather_calls = [args for (name, args) in executed_tools if name == "get_food_for_weather"]
        assert len(weather_calls) == 1
        assert weather_calls[0].get("weather_condition", "").lower() == "rainy"
        assert any("Moderate rain, 22°C" in t for t in final_res["tools_used"])


# 9. A previous rainy result is not reused for a new sunny request
@pytest.mark.asyncio
async def test_prior_rainy_turn_not_reused_for_new_sunny_request():
    agent = CraveAIAgent()
    agent.client = MagicMock()
    agent._cached_groq_tools = [
        {"type": "function", "function": {"name": "get_current_weather", "parameters": {}}},
        {"type": "function", "function": {"name": "get_food_for_weather", "parameters": {}}}
    ]
    agent.mcp_tools_cache = {
        "get_current_weather": ("weather", MagicMock()),
        "get_food_for_weather": ("food", MagicMock())
    }

    # Previous conversation had a rainy question
    prior_conversation = [
        {"role": "user", "content": "It was raining yesterday in Mumbai."},
        {"role": "assistant", "content": "Yes, I recommended rainy snacks like Pyaaz Kachori."}
    ]

    # Current turn has live browser location in sunny Ahmedabad
    call_1 = MagicMock()
    call_1.id = "call_w_fresh"
    call_1.type = "function"
    call_1.function.name = "get_current_weather"
    call_1.function.arguments = json.dumps({"latitude": 23.0225, "longitude": 72.5714})

    choice_1 = MagicMock()
    choice_1.message.content = None
    choice_1.message.tool_calls = [call_1]

    call_2 = MagicMock()
    call_2.id = "call_f_fresh"
    call_2.type = "function"
    call_2.function.name = "get_food_for_weather"
    call_2.function.arguments = json.dumps({"weather_condition": "clear"})

    choice_2 = MagicMock()
    choice_2.message.content = None
    choice_2.message.tool_calls = [call_2]

    choice_3 = MagicMock()
    choice_3.message.content = "Current weather is sunny and 30°C. Try refreshing Pani Puri or Chaat!"
    choice_3.message.tool_calls = None

    agent.client.chat.completions.create = AsyncMock(side_effect=[
        MagicMock(choices=[choice_1]),
        MagicMock(choices=[choice_2]),
        MagicMock(choices=[choice_3])
    ])

    executed_tools = []
    async def mock_tool_exec(name, args):
        executed_tools.append((name, args))
        if name == "get_current_weather":
            return {
                "temperature": 30.0,
                "weather_condition": "Clear sky",
                "normalized_condition": "hot"
            }
        elif name == "get_food_for_weather":
            return {"pani_puri": {"name": "Pani Puri"}}
        return {}

    with patch.object(agent, "execute_tool", side_effect=mock_tool_exec):
        results = []
        async for chunk in agent.chat_stream(
            user_message="What food do you recommend for today's weather?",
            conversation=prior_conversation,
            location={"latitude": 23.0225, "longitude": 72.5714}
        ):
            results.append(json.loads(chunk))

        final_res = next(r for r in results if r.get("type") == "result")

        # Ensured fresh weather check was executed
        assert executed_tools[0][0] == "get_current_weather"
        assert executed_tools[0][1]["latitude"] == 23.0225
        # Condition was clear, not rainy
        assert executed_tools[1][1]["weather_condition"] == "clear"
        assert "pyaaz kachori" not in final_res["response"].lower()


# 10. execute_tool returns the parsed weather dictionary (not None)
@pytest.mark.asyncio
async def test_execute_tool_returns_parsed_weather():
    agent = CraveAIAgent()
    agent.mcp_tools_cache = {
        "get_current_weather": ("weather", MagicMock())
    }
    
    expected_data = {
        "location": {"latitude": 23.0225, "longitude": 72.5714},
        "temperature": 34.0,
        "weather_condition": "Clear sky",
        "normalized_condition": "hot"
    }
    mock_mcp_content = MagicMock()
    mock_mcp_content.text = json.dumps(expected_data)
    agent.weather_client = MagicMock()
    agent.weather_client.call_tool = AsyncMock(return_value=[mock_mcp_content])

    result = await agent.execute_tool("get_current_weather", {"latitude": 23.0225, "longitude": 72.5714})
    assert result is not None
    assert isinstance(result, dict)
    assert result["temperature"] == 34.0
    assert result["weather_condition"] == "Clear sky"


# 11. execute_tool returns the parsed food knowledge dictionary (not None)
@pytest.mark.asyncio
async def test_execute_tool_returns_parsed_food():
    agent = CraveAIAgent()
    agent.mcp_tools_cache = {
        "get_food_for_weather": ("food", MagicMock())
    }

    expected_data = {
        "pani_puri": {"name": "Pani Puri"},
        "dhokla": {"name": "Dhokla"}
    }
    mock_mcp_content = MagicMock()
    mock_mcp_content.text = json.dumps(expected_data)
    agent.food_client = MagicMock()
    agent.food_client.call_tool = AsyncMock(return_value=[mock_mcp_content])

    result = await agent.execute_tool("get_food_for_weather", {"weather_condition": "clear"})
    assert result is not None
    assert isinstance(result, dict)
    assert "pani_puri" in result


# 12. execute_tool handles weather tool raw error string truthfully
@pytest.mark.asyncio
async def test_execute_tool_handles_raw_error_string():
    agent = CraveAIAgent()
    agent.mcp_tools_cache = {
        "get_current_weather": ("weather", MagicMock())
    }

    mock_mcp_content = MagicMock()
    mock_mcp_content.text = "Error executing tool get_current_weather: 500 Internal Server Error"
    agent.weather_client = MagicMock()
    agent.weather_client.call_tool = AsyncMock(return_value=[mock_mcp_content])

    result = await agent.execute_tool("get_current_weather", {"latitude": 23.0225, "longitude": 72.5714})
    assert result is not None
    assert isinstance(result, dict)
    assert "error" in result
    assert "500 Internal Server Error" in result["error"]

