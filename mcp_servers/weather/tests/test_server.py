import pytest
import json
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from server import call_tool, normalize_weather

def test_weather_normalization():
    # Rainy conditions
    assert normalize_weather(61, 20) == "rainy"
    assert normalize_weather(65, 10) == "rainy"
    
    # Stormy conditions
    assert normalize_weather(95, 25) == "stormy"
    
    # Cold conditions
    assert normalize_weather(71, 0) == "cold"  # Snow
    assert normalize_weather(0, 10) == "cold"  # Clear but cold
    
    # Hot conditions
    assert normalize_weather(0, 35) == "hot"   # Clear and hot
    assert normalize_weather(1, 32) == "hot"   # Mainly clear and hot
    
    # Cloudy
    assert normalize_weather(3, 20) == "cloudy"
    
    # Pleasant (Partly cloudy but mild temp)
    assert normalize_weather(1, 22) == "pleasant"

@pytest.mark.asyncio
async def test_get_current_weather(httpx_mock):
    httpx_mock.add_response(
        url="https://api.open-meteo.com/v1/forecast?latitude=23.0225&longitude=72.5714&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
        json={
            "current": {
                "temperature_2m": 35,
                "weather_code": 0,
                "relative_humidity_2m": 45,
                "apparent_temperature": 38,
                "precipitation": 0,
                "wind_speed_10m": 12,
                "time": "2023-10-27T10:00"
            }
        }
    )
    
    result = await call_tool("get_current_weather", {"latitude": 23.0225, "longitude": 72.5714})
    content = json.loads(result[0].text)
    
    assert content["temperature"] == 35
    assert content["weather_condition"] == "Clear sky"
    assert content["normalized_condition"] == "hot"

@pytest.mark.asyncio
async def test_get_weather_forecast(httpx_mock):
    httpx_mock.add_response(
        url="https://api.open-meteo.com/v1/forecast?latitude=23.0225&longitude=72.5714&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum&timezone=auto",
        json={
            "daily": {
                "time": ["2023-10-27", "2023-10-28"],
                "weather_code": [61, 3],
                "temperature_2m_max": [25, 28],
                "temperature_2m_min": [20, 22],
                "precipitation_probability_max": [80, 10],
                "precipitation_sum": [15.5, 0.0]
            }
        }
    )
    
    result = await call_tool("get_weather_forecast", {"latitude": 23.0225, "longitude": 72.5714})
    content = json.loads(result[0].text)
    
    assert len(content["forecast"]) == 2
    assert content["forecast"][0]["normalized_condition"] == "rainy"
    assert content["forecast"][1]["normalized_condition"] == "cloudy"

@pytest.mark.asyncio
async def test_get_current_weather_api_failure(httpx_mock):
    httpx_mock.add_response(status_code=500)
    result = await call_tool("get_current_weather", {"latitude": 23.0225, "longitude": 72.5714})
    assert "Error executing tool" in result[0].text
    assert "500 Internal Server Error" in result[0].text

@pytest.mark.asyncio
async def test_get_current_weather_with_city(httpx_mock):
    # Mock geocoding response
    httpx_mock.add_response(
        url="https://geocoding-api.open-meteo.com/v1/search?name=Ahmedabad&count=1&language=en&format=json",
        json={"results": [{"name": "Ahmedabad", "latitude": 23.0225, "longitude": 72.5714}]}
    )
    # Mock weather response
    httpx_mock.add_response(
        url="https://api.open-meteo.com/v1/forecast?latitude=23.0225&longitude=72.5714&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
        json={
            "current": {
                "temperature_2m": 31,
                "weather_code": 0,
                "relative_humidity_2m": 50,
                "apparent_temperature": 33,
                "precipitation": 0,
                "wind_speed_10m": 10,
                "time": "2023-10-27T10:00"
            }
        }
    )
    result = await call_tool("get_current_weather", {"city": "Ahmedabad"})
    content = json.loads(result[0].text)
    assert content["temperature"] == 31
    assert content["weather_condition"] == "Clear sky"

@pytest.mark.asyncio
async def test_get_weather_forecast_with_city(httpx_mock):
    httpx_mock.add_response(
        url="https://geocoding-api.open-meteo.com/v1/search?name=Ahmedabad&count=1&language=en&format=json",
        json={"results": [{"name": "Ahmedabad", "latitude": 23.0225, "longitude": 72.5714}]}
    )
    httpx_mock.add_response(
        url="https://api.open-meteo.com/v1/forecast?latitude=23.0225&longitude=72.5714&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum&timezone=auto",
        json={
            "daily": {
                "time": ["2023-10-27", "2023-10-28"],
                "weather_code": [61, 0],
                "temperature_2m_max": [27, 29],
                "temperature_2m_min": [21, 22],
                "precipitation_probability_max": [75, 5],
                "precipitation_sum": [10.0, 0.0]
            }
        }
    )
    result = await call_tool("get_weather_forecast", {"city": "Ahmedabad"})
    content = json.loads(result[0].text)
    assert len(content["forecast"]) == 2
    assert content["forecast"][0]["precipitation_probability"] == 75
