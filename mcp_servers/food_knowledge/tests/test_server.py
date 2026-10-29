import pytest
import json
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from server import call_tool, read_resource

@pytest.mark.asyncio
async def test_search_food():
    # test valid search
    result = await call_tool("search_food", {"query": "kachori"})
    content = json.loads(result[0].text)
    assert len(content) > 0
    assert "pyaaz_kachori" in content[0]
    
    # test not found search
    result = await call_tool("search_food", {"query": "pizza"})
    content = json.loads(result[0].text)
    assert len(content) == 0

@pytest.mark.asyncio
async def test_get_dish_information():
    result = await call_tool("get_dish_information", {"dish_id": "vada_pav"})
    content = json.loads(result[0].text)
    assert content["name"] == "Vada Pav"
    
    # Invalid dish
    result = await call_tool("get_dish_information", {"dish_id": "invalid_dish"})
    assert "not found" in result[0].text

@pytest.mark.asyncio
async def test_get_cuisine_information():
    result = await call_tool("get_cuisine_information", {"cuisine_id": "gujarati"})
    content = json.loads(result[0].text)
    assert content["origin"] == "Gujarat"

    # Invalid cuisine
    result = await call_tool("get_cuisine_information", {"cuisine_id": "italian"})
    assert "not found" in result[0].text

@pytest.mark.asyncio
async def test_get_city_food():
    result = await call_tool("get_city_food", {"city_id": "jaipur"})
    content = json.loads(result[0].text)
    assert content["region"] == "Rajasthan"

    # Invalid city
    result = await call_tool("get_city_food", {"city_id": "tokyo"})
    assert "not found" in result[0].text

@pytest.mark.asyncio
async def test_get_food_for_weather():
    # Rainy weather
    result = await call_tool("get_food_for_weather", {"weather_condition": "rainy"})
    content = json.loads(result[0].text)
    assert "pyaaz_kachori" in content
    assert "vada_pav" in content

    # Clear and sunny weather
    result_clear = await call_tool("get_food_for_weather", {"weather_condition": "clear"})
    content_clear = json.loads(result_clear[0].text)
    assert "pani_puri" in content_clear
    assert "pyaaz_kachori" not in content_clear

    result_sunny = await call_tool("get_food_for_weather", {"weather_condition": "sunny"})
    content_sunny = json.loads(result_sunny[0].text)
    assert "dhokla" in content_sunny
    assert "vada_pav" not in content_sunny

    # Invalid weather
    result = await call_tool("get_food_for_weather", {"weather_condition": "apocalyptic"})
    assert "No food recommendations" in result[0].text

@pytest.mark.asyncio
async def test_get_food_for_mood():
    result = await call_tool("get_food_for_mood", {"mood": "comfort"})
    content = json.loads(result[0].text)
    assert "dal_baati_churma" in content

    # Invalid mood
    result = await call_tool("get_food_for_mood", {"mood": "angry"})
    assert "No food recommendations" in result[0].text

@pytest.mark.asyncio
async def test_read_resource():
    # Valid resource
    result = await read_resource("food://cities/mumbai")
    content = json.loads(result)
    assert content["name"] == "Mumbai"
    
    # Invalid resource
    try:
        await read_resource("food://cities/unknown")
        assert False
    except ValueError as e:
        assert "Resource not found" in str(e)
