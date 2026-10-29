import asyncio
import os
import json
import logging
from typing import List
from dotenv import load_dotenv

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from providers.base import RestaurantProvider
from providers.mock import MockRestaurantProvider
from providers.yelp import YelpRestaurantProvider
from providers.swiggy import SwiggyRestaurantProvider

# Ensure dot env is loaded so the Yelp API key is available if provided
load_dotenv()

app = Server("restaurants")

# Provider factory
def get_provider() -> RestaurantProvider:
    provider_name = os.getenv("RESTAURANT_PROVIDER", "swiggy").lower()
    
    if provider_name == "swiggy":
        return SwiggyRestaurantProvider()
    elif provider_name == "yelp":
        yelp_key = os.getenv("YELP_API_KEY")
        if yelp_key:
            return YelpRestaurantProvider(api_key=yelp_key)
        else:
            raise ValueError("YELP_API_KEY is not configured.")
    elif provider_name == "mock":
        return MockRestaurantProvider()
    else:
        raise ValueError(f"Unsupported RESTAURANT_PROVIDER: '{provider_name}'. Must be 'swiggy', 'yelp', or 'mock'.")

provider = None

def set_provider(p: RestaurantProvider):
    global provider
    provider = p

@app.list_tools()
async def list_tools() -> List[Tool]:
    return [
        Tool(
            name="search_nearby_restaurants",
            description="Search for nearby restaurants based on latitude, longitude, and optional filters like query (dish/cuisine/name) and price.",
            inputSchema={
                "type": "object",
                "properties": {
                    "latitude": {"type": "number", "description": "Latitude of the search center"},
                    "longitude": {"type": "number", "description": "Longitude of the search center"},
                    "query": {"type": "string", "description": "Optional search term, e.g., 'Gujarati', 'Kachori', 'Spicy'"},
                    "radius_meters": {"type": "integer", "description": "Optional search radius in meters (default 5000)"},
                    "price_tier": {"type": "string", "description": "Optional price tier (e.g., $, $$, $$$)"}
                },
                "required": ["latitude", "longitude"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> List[TextContent]:
    try:
        if name == "search_nearby_restaurants":
            if not arguments or "latitude" not in arguments or "longitude" not in arguments:
                return [TextContent(type="text", text=json.dumps({"error": "Missing required coordinates: latitude and longitude are required."}))]
            
            try:
                lat = float(arguments["latitude"])
                lon = float(arguments["longitude"])
            except (ValueError, TypeError):
                return [TextContent(type="text", text=json.dumps({"error": "Invalid latitude or longitude coordinate values."}))]

            query = arguments.get("query")
            radius = int(arguments.get("radius_meters", 5000))
            price_tier = arguments.get("price_tier")
            
            active_provider = provider if provider is not None else get_provider()
            results = await active_provider.search_nearby_restaurants(
                latitude=lat,
                longitude=lon,
                query=query,
                radius_meters=radius,
                price_tier=price_tier
            )
            
            if not results:
                return [TextContent(type="text", text=json.dumps({"message": "No restaurants found matching the criteria."}))]
                
            return [TextContent(type="text", text=json.dumps({"restaurants": results}, indent=2))]
        else:
            raise ValueError(f"Unknown tool: {name}")
            
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
