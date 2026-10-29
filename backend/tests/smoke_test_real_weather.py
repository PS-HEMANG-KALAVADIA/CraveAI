import asyncio
import os
import sys
import json

# Ensure paths
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "mcp_servers", "weather"))

from server import fetch_current_weather
from app.mcp_client.client import get_weather_client
from app.agent.agent import CraveAIAgent

async def run_live_weather_smoke_test():
    print("=== SMOKE TEST: 1. Live Open-Meteo API Call ===")
    lat, lon = 23.0225, 72.5714
    live_result = await fetch_current_weather(lat, lon)
    print("Direct Open-Meteo API response:")
    print(json.dumps(live_result, indent=2))
    assert live_result is not None, "Live result is None"
    assert "temperature" in live_result, "Missing temperature"
    assert "weather_condition" in live_result, "Missing weather_condition"
    assert "normalized_condition" in live_result, "Missing normalized_condition"
    assert live_result["temperature"] is not None
    print(f"PASS: Live weather is {live_result['weather_condition']}, {live_result['temperature']}°C")

    print("\n=== SMOKE TEST: 2. Weather MCP Server Over Stdio Client ===")
    client = get_weather_client()
    try:
        await client.connect()
        mcp_res = await client.call_tool("get_current_weather", {"latitude": lat, "longitude": lon})
        assert mcp_res and len(mcp_res) > 0, "Empty MCP response"
        mcp_data = json.loads(mcp_res[0].text)
        print("MCP Server response:", json.dumps(mcp_data, indent=2))
        assert "temperature" in mcp_data, "Missing temperature in MCP response"
        print(f"PASS: MCP Server returned {mcp_data['weather_condition']}, {mcp_data['temperature']}°C")
    finally:
        await client.close()

    print("\n=== SMOKE TEST: 3. Agent execute_tool (Full MCP Conversion) ===")
    agent = CraveAIAgent()
    try:
        agent_res = await agent.execute_tool("get_current_weather", {"latitude": lat, "longitude": lon})
        print("Agent execute_tool response:", agent_res)
        assert agent_res is not None, "Agent execute_tool returned None!"
        assert isinstance(agent_res, dict), f"Expected dict, got {type(agent_res)}"
        assert "temperature" in agent_res, "Missing temperature in agent execute_tool result"
        print("PASS: Agent execute_tool successfully converted MCP result to dict")
    finally:
        await agent.close()

    print("\nALL LIVE WEATHER SMOKE TESTS PASSED!")

if __name__ == "__main__":
    asyncio.run(run_live_weather_smoke_test())
