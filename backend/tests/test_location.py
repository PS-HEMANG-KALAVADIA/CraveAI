import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from app.api.chat import chat_endpoint, ChatRequest, Location
from app.agent.agent import ChatResponse

@pytest.mark.asyncio
@patch('app.api.chat.agent.chat_stream')
async def test_chat_without_location(mock_chat_stream):
    import json
    # Mock agent generator response
    async def mock_generator(*args, **kwargs):
        yield json.dumps({"type": "progress", "message": "Thinking..."})
        yield json.dumps({"type": "result", "response": "Please provide your location.", "tools_used": [], "restaurants": []})
        
    mock_chat_stream.side_effect = mock_generator
    
    req = ChatRequest(message="Find me food nearby")
    res = await chat_endpoint(req)
    
    # Reading from StreamingResponse body
    response_text = ""
    async for chunk in res.body_iterator:
        response_text += chunk
        
    assert "Please provide your location" in response_text
    
    mock_chat_stream.assert_called_once_with(
        user_message="Find me food nearby", 
        conversation=[],
        location=None
    )

@pytest.mark.asyncio
@patch('app.api.chat.agent.chat_stream')
async def test_chat_with_location(mock_chat_stream):
    import json
    async def mock_generator(*args, **kwargs):
        yield json.dumps({"type": "progress", "message": "Thinking..."})
        yield json.dumps({"type": "result", "response": "Found some great places nearby!", "tools_used": ["search_nearby_restaurants"], "restaurants": []})
        
    mock_chat_stream.side_effect = mock_generator
    
    req = ChatRequest(
        message="Find me food nearby", 
        conversation=[],
        location=Location(latitude=23.0, longitude=72.0)
    )
    res = await chat_endpoint(req)
    
    response_text = ""
    async for chunk in res.body_iterator:
        response_text += chunk
        
    assert "Found some great places" in response_text
    
    mock_chat_stream.assert_called_once_with(
        user_message="Find me food nearby", 
        conversation=[],
        location={"latitude": 23.0, "longitude": 72.0}
    )
