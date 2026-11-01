import asyncio
import sys
import os
import json

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Add backend to path so we can import the clients
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.mcp_client.client import get_food_knowledge_client, get_weather_client

async def run_integration():
    weather_client = get_weather_client()
    food_client = get_food_knowledge_client()
    
    await weather_client.connect()
    await food_client.connect()
    
    print("=== Step 1: Getting Weather for Latitude 23.0225, Longitude 72.5714 (Ahmedabad) ===")
    res = await weather_client.call_tool("get_current_weather", {"latitude": 23.0225, "longitude": 72.5714})
    weather_data = json.loads(res[0].text)
    normalized_condition = weather_data.get("normalized_condition")
    
    print(f"Original Condition: {weather_data.get('weather_condition')}")
    print(f"Temperature: {weather_data.get('temperature')} C")
    print(f"Normalized Condition: {normalized_condition}")
    
    print("\n=== Step 2: Querying Food Knowledge for the normalized condition ===")
    res = await food_client.call_tool("get_food_for_weather", {"weather_condition": normalized_condition})
    
    print(f"Food Recommendations for '{normalized_condition}' weather:")
    print(res[0].text)

    await weather_client.close()
    await food_client.close()

if __name__ == "__main__":
    asyncio.run(run_integration())
