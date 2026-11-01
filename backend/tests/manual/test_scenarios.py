import asyncio
import sys
import os

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Add backend to path so we can import the client
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.mcp_client.client import get_food_knowledge_client

async def run_scenarios():
    client = get_food_knowledge_client()
    await client.connect()
    
    print("=== Testing Scenario 1: 'It is raining. What should I eat?' ===")
    res = await client.call_tool("get_food_for_weather", {"weather_condition": "rainy"})
    print(res[0].text)
    
    print("\n=== Testing Scenario 2: 'I want to experience Jaipur food.' ===")
    res = await client.call_tool("get_city_food", {"city_id": "jaipur"})
    print(res[0].text)

    print("\n=== Testing Scenario 3: 'I want Gujarati food.' ===")
    res = await client.call_tool("get_cuisine_information", {"cuisine_id": "gujarati"})
    print(res[0].text)

    print("\n=== Testing Scenario 4: 'I want something spicy.' ===")
    res = await client.call_tool("get_food_for_mood", {"mood": "spicy"})
    print(res[0].text)
    
    print("\n=== Testing Resource Read: 'food://cities/delhi' ===")
    res = await client.read_resource("food://cities/delhi")
    print(res)

    await client.close()

if __name__ == "__main__":
    asyncio.run(run_scenarios())
