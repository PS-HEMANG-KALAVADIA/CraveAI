import asyncio
import httpx
from typing import List, Dict, Any, Optional
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
import json

app = Server("weather")

# Open-Meteo WMO Weather codes mapping
WMO_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}

def normalize_weather(wmo_code: int, temperature: float) -> str:
    """Normalize weather into basic context types for the food agent."""
    if wmo_code in [51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82]:
        return "rainy"
    elif wmo_code in [95, 96, 99]:
        return "stormy"
    elif wmo_code in [71, 73, 75, 77, 85, 86]:
        return "cold"
    elif wmo_code in [3, 45, 48]:
        return "cloudy"
    
    # For clear/partly cloudy, use temperature context
    if temperature >= 30:
        return "hot"
    elif temperature <= 15:
        return "cold"
    elif wmo_code == 0:
        return "clear"
    else:
        return "pleasant"

@app.list_tools()
async def list_tools() -> List[Tool]:
    return [
        Tool(
            name="get_current_weather",
            description="Get the current live weather for a specific latitude and longitude, or for a city name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "latitude": {"type": "number", "description": "Latitude of the location"},
                    "longitude": {"type": "number", "description": "Longitude of the location"},
                    "city": {"type": "string", "description": "Optional city name to resolve coordinates (e.g. 'Ahmedabad')"}
                }
            }
        ),
        Tool(
            name="get_weather_forecast",
            description="Get the weather forecast for the next 7 days for a specific latitude and longitude, or for a city name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "latitude": {"type": "number", "description": "Latitude of the location"},
                    "longitude": {"type": "number", "description": "Longitude of the location"},
                    "city": {"type": "string", "description": "Optional city name to resolve coordinates (e.g. 'Ahmedabad')"}
                }
            }
        )
    ]

async def geocode_city(city: str) -> Optional[tuple[float, float]]:
    url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=en&format=json"
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
        results = data.get("results")
        if results and len(results) > 0:
            return float(results[0]["latitude"]), float(results[0]["longitude"])
    return None

async def fetch_current_weather(lat: float, lon: float) -> Dict[str, Any]:
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m"
    max_retries = 2
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)
                if response.status_code == 503 and attempt < max_retries - 1:
                    await asyncio.sleep(0.3)
                    continue
                response.raise_for_status()
                data = response.json()
                
                current = data.get("current")
                if not current or "temperature_2m" not in current or "weather_code" not in current:
                    raise ValueError("Malformed response from weather service: missing current observations.")

                temp = float(current.get("temperature_2m", 0))
                code = int(current.get("weather_code", 0))
                original_condition = WMO_CODES.get(code, "Unknown")
                
                return {
                    "location": {"latitude": lat, "longitude": lon},
                    "temperature": temp,
                    "feels_like": current.get("apparent_temperature"),
                    "humidity": current.get("relative_humidity_2m"),
                    "precipitation": current.get("precipitation"),
                    "wind_speed": current.get("wind_speed_10m"),
                    "weather_condition": original_condition,
                    "normalized_condition": normalize_weather(code, temp),
                    "timestamp": current.get("time")
                }
        except (httpx.TimeoutException, httpx.ConnectError):
            if attempt < max_retries - 1:
                await asyncio.sleep(0.3)
                continue
            raise

async def fetch_weather_forecast(lat: float, lon: float) -> Dict[str, Any]:
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum&timezone=auto"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
        
        daily = data.get("daily", {})
        forecast_list = []
        
        if "time" in daily:
            for i in range(len(daily["time"])):
                code = daily["weather_code"][i]
                max_temp = daily["temperature_2m_max"][i]
                forecast_list.append({
                    "date": daily["time"][i],
                    "max_temperature": max_temp,
                    "min_temperature": daily["temperature_2m_min"][i],
                    "precipitation_probability": daily["precipitation_probability_max"][i],
                    "precipitation_amount": daily["precipitation_sum"][i],
                    "weather_condition": WMO_CODES.get(code, "Unknown"),
                    "normalized_condition": normalize_weather(code, max_temp)
                })
                
        return {
            "location": {"latitude": lat, "longitude": lon},
            "forecast": forecast_list
        }

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> List[TextContent]:
    try:
        if name in ["get_current_weather", "get_weather_forecast"]:
            if "latitude" in arguments and "longitude" in arguments and arguments["latitude"] is not None and arguments["longitude"] is not None:
                lat = float(arguments["latitude"])
                lon = float(arguments["longitude"])
            elif "city" in arguments or "location" in arguments:
                city = str(arguments.get("city") or arguments.get("location"))
                coords = await geocode_city(city)
                if not coords:
                    return [TextContent(type="text", text=json.dumps({"error": f"City '{city}' not found."}))]
                lat, lon = coords
            else:
                raise ValueError("Missing required arguments: latitude and longitude, or city")

            if name == "get_current_weather":
                result = await fetch_current_weather(lat, lon)
            else:
                result = await fetch_weather_forecast(lat, lon)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
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
