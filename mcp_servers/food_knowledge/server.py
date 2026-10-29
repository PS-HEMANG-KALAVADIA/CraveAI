import asyncio
from typing import List, Dict, Any, Optional
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
)
import urllib.parse
import json

from data import CITIES, CUISINES, DISHES, WEATHER_ASSOCIATIONS, MOOD_ASSOCIATIONS

app = Server("food-knowledge")

@app.list_resources()
async def list_resources() -> List[Resource]:
    resources = []
    for city_id in CITIES.keys():
        resources.append(
            Resource(
                uri=f"food://cities/{city_id}",
                name=f"City: {CITIES[city_id]['name']}",
                mimeType="application/json"
            )
        )
    for cuisine_id in CUISINES.keys():
        resources.append(
            Resource(
                uri=f"food://cuisines/{cuisine_id}",
                name=f"Cuisine: {CUISINES[cuisine_id]['name']}",
                mimeType="application/json"
            )
        )
    for dish_id in DISHES.keys():
        resources.append(
            Resource(
                uri=f"food://dishes/{dish_id}",
                name=f"Dish: {DISHES[dish_id]['name']}",
                mimeType="application/json"
            )
        )
    return resources

@app.read_resource()
async def read_resource(uri: Any | str) -> str:
    uri = str(uri)
    parsed = urllib.parse.urlparse(uri)
    if parsed.scheme != "food":
        raise ValueError(f"Unsupported scheme: {parsed.scheme}")
    
    parts = parsed.netloc.split('/') if parsed.netloc else parsed.path.strip('/').split('/')
    if len(parts) >= 2:
        resource_type = parts[0]
        resource_id = parts[1]
    else:
        # handle food://cities/jaipur where netloc is 'cities' and path is '/jaipur'
        resource_type = parsed.netloc
        resource_id = parsed.path.strip('/')

    if resource_type == "cities" and resource_id in CITIES:
        return json.dumps(CITIES[resource_id], indent=2)
    elif resource_type == "cuisines" and resource_id in CUISINES:
        return json.dumps(CUISINES[resource_id], indent=2)
    elif resource_type == "dishes" and resource_id in DISHES:
        return json.dumps(DISHES[resource_id], indent=2)
    
    raise ValueError(f"Resource not found: {uri}")

@app.list_tools()
async def list_tools() -> List[Tool]:
    return [
        Tool(
            name="search_food",
            description="Search for a dish by keyword in its name or description.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search term"}
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="get_dish_information",
            description="Get detailed information about a specific dish.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dish_id": {"type": "string", "description": "The ID of the dish (e.g., 'pyaaz_kachori')"}
                },
                "required": ["dish_id"]
            }
        ),
        Tool(
            name="get_cuisine_information",
            description="Get detailed information about a specific cuisine.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cuisine_id": {"type": "string", "description": "The ID of the cuisine (e.g., 'rajasthani')"}
                },
                "required": ["cuisine_id"]
            }
        ),
        Tool(
            name="get_city_food",
            description="Get food information for a specific city.",
            inputSchema={
                "type": "object",
                "properties": {
                    "city_id": {"type": "string", "description": "The ID of the city (e.g., 'jaipur')"}
                },
                "required": ["city_id"]
            }
        ),
        Tool(
            name="get_food_for_weather",
            description="Get a list of dishes recommended for a specific weather condition.",
            inputSchema={
                "type": "object",
                "properties": {
                    "weather_condition": {"type": "string", "description": "The weather condition (e.g., 'rainy', 'hot', 'cold')"}
                },
                "required": ["weather_condition"]
            }
        ),
        Tool(
            name="get_food_for_mood",
            description="Get a list of dishes recommended for a specific mood.",
            inputSchema={
                "type": "object",
                "properties": {
                    "mood": {"type": "string", "description": "The mood (e.g., 'comfort', 'spicy', 'light', 'healthy')"}
                },
                "required": ["mood"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> List[TextContent]:
    try:
        if name == "search_food":
            query = arguments["query"].lower()
            results = []
            for d_id, d_info in DISHES.items():
                if query in d_info["name"].lower() or query in d_info["description"].lower():
                    results.append({d_id: d_info})
            return [TextContent(type="text", text=json.dumps(results, indent=2))]
        
        elif name == "get_dish_information":
            dish_id = arguments["dish_id"]
            if dish_id in DISHES:
                return [TextContent(type="text", text=json.dumps(DISHES[dish_id], indent=2))]
            return [TextContent(type="text", text=f"Dish '{dish_id}' not found.")]
            
        elif name == "get_cuisine_information":
            cuisine_id = arguments["cuisine_id"]
            if cuisine_id in CUISINES:
                return [TextContent(type="text", text=json.dumps(CUISINES[cuisine_id], indent=2))]
            return [TextContent(type="text", text=f"Cuisine '{cuisine_id}' not found.")]
            
        elif name == "get_city_food":
            city_id = arguments["city_id"]
            if city_id in CITIES:
                return [TextContent(type="text", text=json.dumps(CITIES[city_id], indent=2))]
            return [TextContent(type="text", text=f"City '{city_id}' not found.")]
            
        elif name == "get_food_for_weather":
            weather = str(arguments.get("weather_condition", "")).lower().strip()
            alias_map = {
                "clear sky": "clear",
                "mainly clear": "clear",
                "partly cloudy": "pleasant",
                "sunny": "sunny",
                "rain": "rainy",
                "showers": "rainy",
                "drizzle": "rainy",
                "thunderstorm": "stormy",
                "snow": "cold",
                "freezing": "cold",
                "overcast": "cloudy",
                "fog": "cloudy"
            }
            normalized_key = alias_map.get(weather, weather)
            if normalized_key in WEATHER_ASSOCIATIONS:
                dishes = WEATHER_ASSOCIATIONS[normalized_key]
                results = {d: DISHES[d] for d in dishes if d in DISHES}
                return [TextContent(type="text", text=json.dumps(results, indent=2))]
            return [TextContent(type="text", text=f"No food recommendations for weather '{weather}'.")]
            
        elif name == "get_food_for_mood":
            mood = arguments["mood"].lower()
            if mood in MOOD_ASSOCIATIONS:
                dishes = MOOD_ASSOCIATIONS[mood]
                results = {d: DISHES[d] for d in dishes if d in DISHES}
                return [TextContent(type="text", text=json.dumps(results, indent=2))]
            return [TextContent(type="text", text=f"No food recommendations for mood '{mood}'.")]
        
        else:
            raise ValueError(f"Unknown tool: {name}")
    except Exception as e:
        return [TextContent(type="text", text=f"Error executing tool {name}: {str(e)}")]

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
