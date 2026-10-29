import pytest
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from server import list_prompts, get_prompt

@pytest.mark.asyncio
async def test_list_prompts():
    prompts = await list_prompts()
    assert len(prompts) == 3
    names = [p.name for p in prompts]
    assert "rainy_day" in names
    assert "city_experience" in names
    assert "budget_food" in names

@pytest.mark.asyncio
async def test_get_prompt_valid():
    result = await get_prompt("rainy_day", {"location": "Seattle", "dietary_preference": "vegan"})
    assert result.messages
    text = result.messages[0].content.text
    assert "Seattle" in text
    assert "vegan" in text
    assert "Weather MCP" in text

@pytest.mark.asyncio
async def test_get_prompt_missing_args():
    # Should fallback to defaults
    result = await get_prompt("budget_food", None)
    text = result.messages[0].content.text
    assert "budget of" in text

@pytest.mark.asyncio
async def test_get_prompt_invalid():
    with pytest.raises(ValueError, match="Unknown prompt"):
        await get_prompt("invalid_prompt_name", {})
