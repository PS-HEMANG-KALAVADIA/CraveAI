import pytest
import sys
import os
import json
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from unittest.mock import AsyncMock, MagicMock, patch

# Mock all get_*_client functions globally before importing app to avoid event loop issues with MCP
patch('app.agent.agent.get_food_knowledge_client').start()
patch('app.agent.agent.get_weather_client').start()
patch('app.agent.agent.get_restaurant_client').start()
patch('app.agent.agent.get_prompt_client').start()

from fastapi.testclient import TestClient
from app.main import app
from app.agent.agent import ChatResponse

client = TestClient(app)

def test_chat_endpoint_success():
    with patch("app.api.chat.agent.chat_stream", new_callable=MagicMock) as mock_chat_stream:
        # chat_stream is an async generator, we need to mock it properly
        async def mock_gen(*args, **kwargs):
            yield json.dumps({
                "type": "result",
                "response": "I recommend Pyaaz Kachori because it is raining.",
                "tools_used": ["get_current_weather", "get_food_for_weather"],
                "restaurants": []
            })
        
        mock_chat_stream.side_effect = mock_gen
        
        response = client.post("/api/chat", json={"message": "It's raining. What should I eat?"})
        assert response.status_code == 200
        
        # Parse SSE stream text
        text = response.text
        # data: {"type": "result", ...}
        lines = text.strip().split("\n")
        data_line = [l for l in lines if l.startswith("data: ")][-1]
        data = json.loads(data_line[6:])
        
        assert data["response"] == "I recommend Pyaaz Kachori because it is raining."
        assert "get_current_weather" in data["tools_used"]

def test_chat_endpoint_failure():
    with patch("app.api.chat.agent.chat_stream", new_callable=MagicMock) as mock_chat_stream:
        # simulate an exception during iteration
        async def mock_gen(*args, **kwargs):
            raise ValueError("LLM client is not configured")
            yield "" # need a yield to make it an async generator
            
        mock_chat_stream.side_effect = mock_gen
        
        response = client.post("/api/chat", json={"message": "Hello"})
        assert response.status_code == 200
        
        text = response.text
        lines = text.strip().split("\n")
        data_line = [l for l in lines if l.startswith("data: ")][-1]
        data = json.loads(data_line[6:])
        
        assert data["type"] == "error"
        assert "LLM client is not configured" in data["message"]

@pytest.mark.asyncio
async def test_agent_initializes_tools():
    # Test that the agent fetches tools from MCP clients
    with patch("app.agent.agent.get_food_knowledge_client") as mock_food, \
         patch("app.agent.agent.get_weather_client") as mock_weather, \
         patch("app.agent.agent.get_restaurant_client") as mock_restaurant, \
         patch("app.agent.agent.get_prompt_client") as mock_prompt:
        
        mock_f_client = AsyncMock()
        mock_w_client = AsyncMock()
        mock_r_client = AsyncMock()
        mock_p_client = AsyncMock()
        
        class DummyTool:
            def __init__(self, name, description, inputSchema):
                self.name = name
                self.description = description
                self.inputSchema = inputSchema
                
        class DummyPrompt:
            def __init__(self, name):
                self.name = name

        mock_f_client.get_tools.return_value = [
            DummyTool("search_food", "search", {"type": "object", "properties": {}})
        ]
        mock_w_client.get_tools.return_value = [
            DummyTool("get_current_weather", "weather", {"type": "object", "properties": {}})
        ]
        mock_r_client.get_tools.return_value = []
        mock_p_client.get_prompts.return_value = [DummyPrompt("test_prompt")]
        
        mock_food.return_value = mock_f_client
        mock_weather.return_value = mock_w_client
        mock_restaurant.return_value = mock_r_client
        mock_prompt.return_value = mock_p_client
        
        from app.agent.agent import CraveAIAgent
        agent = CraveAIAgent()
        tools = await agent.initialize_tools()
        
        # 3 tools: 1 from food, 1 from weather, 0 from restaurant, 1 meta-tool
        assert len(tools) == 3
        names = [f["function"]["name"] for f in tools]
        assert "search_food" in names
        assert "get_current_weather" in names
        assert "get_workflow_guidance" in names
