import os
import sys
import json
import time
import base64
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient

from app.main import app
from app.api.auth import check_swiggy_token_status, decode_jwt_payload_unverified, get_token_path, get_auth_state_path
from app.agent.agent import CraveAIAgent

def create_fake_jwt(payload: dict) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    h_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    p_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig = "fake_signature"
    return f"{h_b64}.{p_b64}.{sig}"

# 1. Missing token file
def test_missing_token_file(tmp_path):
    t_file = str(tmp_path / "nonexistent_token.json")
    s_file = str(tmp_path / "nonexistent_state.json")
    
    result = check_swiggy_token_status(token_path=t_file, state_path=s_file)
    assert result["connected"] is False
    assert result["status"] == "not_connected"
    assert result["authenticated"] is False
    assert "login_url" in result
    assert "access_token" not in result

# 2. Empty or malformed token file
def test_empty_token_file(tmp_path):
    t_file = tmp_path / "empty_token.json"
    t_file.write_text("")
    s_file = str(tmp_path / "state.json")
    
    result = check_swiggy_token_status(token_path=str(t_file), state_path=s_file)
    assert result["connected"] is False
    assert result["status"] == "not_connected"

def test_malformed_token_file(tmp_path):
    t_file = tmp_path / "corrupt_token.json"
    t_file.write_text("{this is not valid json")
    s_file = str(tmp_path / "state.json")
    
    result = check_swiggy_token_status(token_path=str(t_file), state_path=s_file)
    assert result["connected"] is False
    assert result["status"] == "not_connected"

def test_non_dict_token_file(tmp_path):
    t_file = tmp_path / "list_token.json"
    t_file.write_text(json.dumps(["token1", "token2"]))
    s_file = str(tmp_path / "state.json")
    
    result = check_swiggy_token_status(token_path=str(t_file), state_path=s_file)
    assert result["connected"] is False
    assert result["status"] == "not_connected"

# 3. Valid stored authentication
def test_valid_stored_authentication_jwt(tmp_path):
    future_time = time.time() + 86400
    valid_access = create_fake_jwt({"sub": "user123", "exp": future_time})
    valid_refresh = create_fake_jwt({"sub": "user123", "exp": future_time + 86400})
    
    t_file = tmp_path / "valid_token.json"
    t_file.write_text(json.dumps({
        "access_token": valid_access,
        "refresh_token": valid_refresh,
        "token_type": "Bearer"
    }))
    s_file = str(tmp_path / "state.json")
    
    result = check_swiggy_token_status(token_path=str(t_file), state_path=s_file)
    assert result["connected"] is True
    assert result["status"] == "connected"
    assert result["authenticated"] is True
    # Ensure no secret tokens leaked
    assert valid_access not in str(result)
    assert valid_refresh not in str(result)

def test_valid_stored_authentication_expired_access_with_valid_refresh(tmp_path):
    """When access_token is expired but valid refresh_token exists, session can be renewed."""
    past_time = time.time() - 3600
    future_time = time.time() + 86400
    expired_access = create_fake_jwt({"sub": "user123", "exp": past_time})
    valid_refresh = create_fake_jwt({"sub": "user123", "exp": future_time})
    
    t_file = tmp_path / "refreshable_token.json"
    t_file.write_text(json.dumps({
        "access_token": expired_access,
        "refresh_token": valid_refresh,
        "token_type": "Bearer"
    }))
    s_file = str(tmp_path / "state.json")
    
    result = check_swiggy_token_status(token_path=str(t_file), state_path=s_file)
    assert result["connected"] is True
    assert result["status"] == "connected"

# 4. Known invalid refresh token / reauth required
def test_invalidated_token_file_marker(tmp_path):
    t_file = tmp_path / "invalid_token.json"
    t_file.write_text(json.dumps({
        "access_token": "some_token",
        "invalid": True
    }))
    s_file = str(tmp_path / "state.json")
    
    result = check_swiggy_token_status(token_path=str(t_file), state_path=s_file)
    assert result["connected"] is False
    assert result["status"] == "reauth_required"

def test_missing_token_with_reauth_state(tmp_path):
    t_file = str(tmp_path / "missing_token.json")
    s_file = tmp_path / "state.json"
    s_file.write_text(json.dumps({
        "status": "reauth_required",
        "reason": "invalid_grant"
    }))
    
    result = check_swiggy_token_status(token_path=t_file, state_path=str(s_file))
    assert result["connected"] is False
    assert result["status"] == "reauth_required"

def test_expired_refresh_token(tmp_path):
    past_time = time.time() - 3600
    expired_access = create_fake_jwt({"sub": "user123", "exp": past_time})
    expired_refresh = create_fake_jwt({"sub": "user123", "exp": past_time})
    
    t_file = tmp_path / "expired_refresh.json"
    t_file.write_text(json.dumps({
        "access_token": expired_access,
        "refresh_token": expired_refresh
    }))
    s_file = str(tmp_path / "state.json")
    
    result = check_swiggy_token_status(token_path=str(t_file), state_path=s_file)
    assert result["connected"] is False
    assert result["status"] == "reauth_required"

def test_expired_access_token_without_refresh_token(tmp_path):
    past_time = time.time() - 3600
    expired_access = create_fake_jwt({"sub": "user123", "exp": past_time})
    
    t_file = tmp_path / "expired_no_refresh.json"
    t_file.write_text(json.dumps({
        "access_token": expired_access
    }))
    s_file = str(tmp_path / "state.json")
    
    result = check_swiggy_token_status(token_path=str(t_file), state_path=s_file)
    assert result["connected"] is False
    assert result["status"] == "reauth_required"

# 5. FastApi status endpoint tests
def test_swiggy_status_endpoint(tmp_path):
    client = TestClient(app)
    with patch("app.api.auth.get_token_path") as mock_t, \
         patch("app.api.auth.get_auth_state_path") as mock_s:
        mock_t.return_value = str(tmp_path / "nonexistent.json")
        mock_s.return_value = str(tmp_path / "state.json")
        
        resp = client.get("/api/swiggy/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is False
        assert data["status"] == "not_connected"
        assert "login_url" in data

# 6. Status refresh after OAuth login and logout
def test_status_after_callback_and_logout(tmp_path):
    token_file = tmp_path / ".swiggy_token.json"
    state_file = tmp_path / ".swiggy_auth_state.json"
    
    with patch("app.api.auth.get_token_path", return_value=str(token_file)), \
         patch("app.api.auth.get_auth_state_path", return_value=str(state_file)), \
         patch("app.api.auth.auth_sessions", {"test_state": "test_verifier"}):
        
        client = TestClient(app)
        
        # Initial status: not connected
        r1 = client.get("/api/swiggy/status")
        assert r1.json()["status"] == "not_connected"
        
        # Simulate OAuth exchange callback
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            future_exp = time.time() + 86400
            mock_resp.json.return_value = {
                "access_token": create_fake_jwt({"exp": future_exp}),
                "refresh_token": create_fake_jwt({"exp": future_exp + 86400})
            }
            mock_post.return_value = mock_resp
            
            cb_resp = client.get("/api/swiggy/callback?code=mock_code&state=test_state")
            assert cb_resp.status_code == 200
            
        # Rechecked status: now connected
        r2 = client.get("/api/swiggy/status")
        assert r2.json()["status"] == "connected"
        assert r2.json()["connected"] is True
        
        # Test logout
        logout_resp = client.post("/api/swiggy/logout")
        assert logout_resp.status_code == 200
        assert logout_resp.json()["status"] == "not_connected"
        
        # Rechecked status after logout: not connected
        r3 = client.get("/api/swiggy/status")
        assert r3.json()["status"] == "not_connected"

# 7. Status update after authentication-related restaurant-search failure
@pytest.mark.asyncio
async def test_auth_related_restaurant_search_failure():
    agent = CraveAIAgent()
    
    # Mock restaurant_client.call_tool to return session expired error
    mock_res = [MagicMock()]
    mock_res[0].text = json.dumps({"error": "Swiggy session expired. Please re-authenticate at /api/swiggy/login"})
    agent.restaurant_client = MagicMock()
    agent.restaurant_client.call_tool = AsyncMock(return_value=mock_res)
    agent.mcp_tools_cache["search_nearby_restaurants"] = ("restaurant", MagicMock())
    
    result = await agent.execute_tool("search_nearby_restaurants", {"latitude": 23.0, "longitude": 72.0, "query": "pizza"})
    assert isinstance(result, dict)
    assert "error" in result
    assert agent.last_auth_error == "reauth_required"

@pytest.mark.asyncio
async def test_auth_missing_restaurant_search_failure():
    agent = CraveAIAgent()
    
    mock_res = [MagicMock()]
    mock_res[0].text = json.dumps({"error": "Swiggy authentication missing. Please authenticate via /api/swiggy/login first."})
    agent.restaurant_client = MagicMock()
    agent.restaurant_client.call_tool = AsyncMock(return_value=mock_res)
    agent.mcp_tools_cache["search_nearby_restaurants"] = ("restaurant", MagicMock())
    
    result = await agent.execute_tool("search_nearby_restaurants", {"latitude": 23.0, "longitude": 72.0, "query": "pizza"})
    assert isinstance(result, dict)
    assert "error" in result
    assert agent.last_auth_error == "not_connected"

# 8. Unrelated restaurant-search errors do NOT mark user as disconnected
@pytest.mark.asyncio
async def test_unrelated_search_errors_do_not_change_status():
    agent = CraveAIAgent()
    agent.last_auth_error = None
    
    # Empty results
    mock_res = [MagicMock()]
    mock_res[0].text = json.dumps({"message": "No restaurants found matching the criteria."})
    agent.restaurant_client = MagicMock()
    agent.restaurant_client.call_tool = AsyncMock(return_value=mock_res)
    agent.mcp_tools_cache["search_nearby_restaurants"] = ("restaurant", MagicMock())
    
    result = await agent.execute_tool("search_nearby_restaurants", {"latitude": 23.0, "longitude": 72.0, "query": "rare_dish_123"})
    assert agent.last_auth_error is None

    # Unrelated network error
    mock_res_err = [MagicMock()]
    mock_res_err[0].text = json.dumps({"error": "Transport error connecting to Swiggy MCP: ConnectTimeout"})
    agent.restaurant_client.call_tool = AsyncMock(return_value=mock_res_err)
    
    result2 = await agent.execute_tool("search_nearby_restaurants", {"latitude": 23.0, "longitude": 72.0, "query": "pizza"})
    assert agent.last_auth_error is None
