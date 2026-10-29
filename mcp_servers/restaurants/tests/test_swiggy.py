import pytest
import json
import sys
import os
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from providers.swiggy import SwiggyRestaurantProvider

@pytest.fixture
def mock_token_file(tmp_path):
    token_path = tmp_path / ".swiggy_token.json"
    token_path.write_text('{"access_token": "fake_test_token_12345", "refresh_token": "fake_refresh_token"}')
    return str(token_path)

@pytest.fixture
def provider(mock_token_file):
    p = SwiggyRestaurantProvider()
    p.token_path = mock_token_file
    return p

class FakeSession:
    def __init__(self):
        self.tools = []
        self.call_responses = {}
        self.last_calls = []
        
    async def list_tools(self):
        res = MagicMock()
        res.tools = self.tools
        return res
        
    async def call_tool(self, name, args):
        self.last_calls.append((name, args))
        if name in self.call_responses:
            res = self.call_responses[name]
            if isinstance(res, Exception):
                raise res
            mock_res = MagicMock()
            mock_content = MagicMock()
            mock_content.text = json.dumps(res) if not isinstance(res, str) else res
            mock_res.content = [mock_content]
            return mock_res
        raise ValueError(f"Unexpected tool call: {name}")

def create_mock_tool(name, schema):
    t = MagicMock()
    t.name = name
    t.inputSchema = schema
    return t

@pytest.mark.asyncio
async def test_missing_authentication(tmp_path):
    p = SwiggyRestaurantProvider()
    p.token_path = str(tmp_path / "nonexistent.json")
    with pytest.raises(Exception, match="Swiggy authentication missing"):
        p._get_token()

@pytest.mark.asyncio
async def test_expired_authentication_refresh_failure(provider):
    # Mock refresh failure returning 400
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_post.return_value = mock_resp
        
        with patch("providers.swiggy.streamable_http_client", side_effect=Exception("HTTP 401 Unauthorized")):
            with pytest.raises(Exception, match="Swiggy session expired"):
                await provider.search_nearby_restaurants(23.0225, 72.5714, query="pani puri")

@pytest.mark.asyncio
async def test_successful_search_with_coordinates(provider):
    session = FakeSession()
    session.tools = [
        create_mock_tool("search_restaurants", {
            "type": "object",
            "properties": {
                "latitude": {"type": "number"},
                "longitude": {"type": "number"},
                "query": {"type": "string"}
            },
            "required": ["latitude", "longitude", "query"]
        })
    ]
    session.call_responses["search_restaurants"] = {
        "restaurants": [
            {
                "id": "swiggy_rest_1",
                "name": "Shreeji Pani Puri Center",
                "avgRating": 4.6,
                "distanceKm": 1.5,
                "costForTwo": 150,
                "cuisines": ["Street Food", "Chaat"],
                "locality": "Navrangpura, Ahmedabad",
                "availabilityStatus": "OPEN"
            }
        ]
    }
    
    with patch.object(provider, '_run_with_session', new_callable=AsyncMock) as mock_run:
        async def mock_run_side_effect(cb):
            return await cb(session)
        mock_run.side_effect = mock_run_side_effect
        
        results = await provider.search_nearby_restaurants(23.0225, 72.5714, query="pani puri")
        
        assert len(results) == 1
        r = results[0]
        assert r["id"] == "swiggy_rest_1"
        assert r["name"] == "Shreeji Pani Puri Center"
        assert r["rating"] == 4.6
        assert r["distance_meters"] == 1500
        assert r["price"] == "$"
        assert r["is_closed"] is False
        assert "Street Food" in r["cuisine"]
        
        # Verify coordinates and query were passed to Swiggy search_restaurants
        assert len(session.last_calls) == 1
        call_name, call_args = session.last_calls[0]
        assert call_name == "search_restaurants"
        assert call_args["latitude"] == 23.0225
        assert call_args["longitude"] == 72.5714
        assert call_args["query"] == "pani puri"

@pytest.mark.asyncio
async def test_zero_results(provider):
    session = FakeSession()
    session.tools = [
        create_mock_tool("search_restaurants", {
            "properties": {
                "latitude": {},
                "longitude": {},
                "query": {}
            }
        })
    ]
    session.call_responses["search_restaurants"] = {"restaurants": []}
    
    with patch.object(provider, '_run_with_session', new_callable=AsyncMock) as mock_run:
        async def mock_run_side_effect(cb):
            return await cb(session)
        mock_run.side_effect = mock_run_side_effect
        
        results = await provider.search_nearby_restaurants(23.0225, 72.5714, query="nonexistent dish 999")
        assert results == []

@pytest.mark.asyncio
async def test_swiggy_transport_failure(provider):
    with patch.object(provider, '_run_with_session', new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = Exception("Streamable HTTP connection refused: connect ECONNREFUSED")
        
        with pytest.raises(Exception, match="connection refused"):
            await provider.search_nearby_restaurants(23.0225, 72.5714, query="pani puri")

@pytest.mark.asyncio
async def test_address_id_fallback_when_schema_only_supports_address(provider):
    """When Swiggy search_restaurants only declares addressId, provider discovers and uses address."""
    session = FakeSession()
    session.tools = [
        create_mock_tool("get_addresses", {}),
        create_mock_tool("search_restaurants", {
            "properties": {
                "addressId": {},
                "query": {}
            }
        })
    ]
    session.call_responses["get_addresses"] = [{"id": "addr_ahmedabad_1"}]
    session.call_responses["search_restaurants"] = {
        "restaurants": [
            {
                "id": "r_addr_1",
                "name": "Ahmedabad Chaat Corner",
                "avgRating": 4.3,
                "distance": 800
            }
        ]
    }
    
    with patch.object(provider, '_run_with_session', new_callable=AsyncMock) as mock_run:
        async def mock_run_side_effect(cb):
            return await cb(session)
        mock_run.side_effect = mock_run_side_effect
        
        results = await provider.search_nearby_restaurants(23.0225, 72.5714, query="chaat")
        assert len(results) == 1
        assert results[0]["name"] == "Ahmedabad Chaat Corner"
        assert session.last_calls[0][0] == "get_addresses"
        assert session.last_calls[1][0] == "search_restaurants"
        assert session.last_calls[1][1]["addressId"] == "addr_ahmedabad_1"

@pytest.mark.asyncio
async def test_no_sensitive_data_in_sanitized_errors(provider):
    """Verify that access tokens or sensitive credentials never leak into exceptions."""
    secret_token = "fake_test_token_12345"
    with patch.object(provider, '_run_with_session', new_callable=AsyncMock) as mock_run:
        # Simulate an internal error that might contain the token
        mock_run.side_effect = Exception(f"Internal error for Bearer {secret_token}")
        
        try:
            await provider.search_nearby_restaurants(23.0225, 72.5714, query="pani puri")
        except Exception as e:
            err_msg = str(e)
            assert secret_token not in err_msg
            assert "Bearer" not in err_msg


@pytest.mark.asyncio
async def test_successful_refresh_and_request_contract(provider):
    """Verify refresh uses POST https://mcp.swiggy.com/auth/token, Content-Type: application/json,
    body: {"grant_type": "refresh_token", "refresh_token": "..."}, and no client_id."""
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "new_access_token_67890",
            "token_type": "Bearer",
            "expires_in": 2592000,
            "refresh_token": "rotated_refresh_token_abcde"
        }
        mock_post.return_value = mock_resp

        new_tok = await provider._try_refresh_token(failed_token="fake_test_token_12345")
        assert new_tok == "new_access_token_67890"

        # Verify exact request parameters
        assert mock_post.call_count == 1
        args, kwargs = mock_post.call_args
        assert args[0] == "https://mcp.swiggy.com/auth/token"
        assert kwargs["headers"]["Content-Type"] == "application/json"
        assert kwargs["json"] == {
            "grant_type": "refresh_token",
            "refresh_token": "fake_refresh_token"
        }
        assert "client_id" not in kwargs["json"]

        # Verify saved token file
        with open(provider.token_path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["access_token"] == "new_access_token_67890"
        assert saved["refresh_token"] == "rotated_refresh_token_abcde"


@pytest.mark.asyncio
async def test_token_rotation(provider):
    """Verify that after successful rotation, the new refresh token is saved and the old one is discarded."""
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "rotated_access_111",
            "token_type": "Bearer",
            "expires_in": 2592000,
            "refresh_token": "rotated_refresh_222"
        }
        mock_post.return_value = mock_resp

        new_tok = await provider._try_refresh_token()
        assert new_tok == "rotated_access_111"

        with open(provider.token_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["access_token"] == "rotated_access_111"
        assert data["refresh_token"] == "rotated_refresh_222"
        assert provider._get_token() == "rotated_access_111"


@pytest.mark.asyncio
async def test_invalid_refresh_token_400_invalid_grant_stops_retrying(provider):
    """When Swiggy returns 400 invalid_grant, stop retrying and remove invalid token file."""
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Refresh token expired or revoked"
        }
        mock_post.return_value = mock_resp

        # First refresh attempt encounters 400 invalid_grant
        result = await provider._try_refresh_token()
        assert result is None

        # Verify invalid token was removed so it won't be retried
        assert not os.path.exists(provider.token_path)

        # Subsequent attempts fail immediately without calling Swiggy again
        mock_post.reset_mock()
        second_result = await provider._try_refresh_token()
        assert second_result is None
        assert mock_post.call_count == 0

        # Attempting to read token raises authentication missing
        with pytest.raises(Exception, match="Swiggy authentication missing"):
            provider._get_token()


@pytest.mark.asyncio
async def test_malformed_request_error_handling(provider, caplog):
    """Verify 400 invalid_request error is safely parsed without logging secret tokens."""
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {
            "error": "invalid_request",
            "error_description": "Missing required refresh_token"
        }
        mock_post.return_value = mock_resp

        result = await provider._try_refresh_token()
        assert result is None

        # Ensure no secret tokens leaked into log messages
        for record in caplog.records:
            assert "fake_test_token_12345" not in record.message
            assert "fake_refresh_token" not in record.message


@pytest.mark.asyncio
async def test_reauthentication_required_behavior(provider):
    """When token refresh fails, search raises exception requiring re-authentication via login route."""
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Token expired"
        }
        mock_post.return_value = mock_resp

        with patch("providers.swiggy.streamable_http_client", side_effect=Exception("HTTP 401 Unauthorized")):
            with pytest.raises(Exception, match="Swiggy session expired. Please re-authenticate at /api/swiggy/login"):
                await provider.search_nearby_restaurants(23.0225, 72.5714, query="pani puri")

        # After invalid_grant, token file is cleared; future searches prompt to authenticate
        with pytest.raises(Exception, match="Swiggy authentication missing. Please authenticate via /api/swiggy/login first."):
            await provider.search_nearby_restaurants(23.0225, 72.5714, query="pani puri")


@pytest.mark.asyncio
async def test_concurrent_refresh_attempts_single_network_call(provider):
    """Concurrent refresh attempts are synchronized: only one HTTP request is made and both callers receive the new token."""
    network_calls = 0

    async def delayed_post(*args, **kwargs):
        nonlocal network_calls
        network_calls += 1
        await asyncio.sleep(0.05)
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "access_token": "concurrent_refreshed_access",
            "refresh_token": "concurrent_refreshed_refresh"
        }
        return resp

    with patch("httpx.AsyncClient.post", side_effect=delayed_post):
        # Fire two concurrent refresh attempts with the same failed token
        t1, t2 = await asyncio.gather(
            provider._try_refresh_token(failed_token="fake_test_token_12345"),
            provider._try_refresh_token(failed_token="fake_test_token_12345")
        )

        assert t1 == "concurrent_refreshed_access"
        assert t2 == "concurrent_refreshed_access"
        # Only one HTTP request should have been performed
        assert network_calls == 1


@pytest.mark.asyncio
async def test_corrupt_or_empty_token_file_handling(tmp_path):
    """Verify empty or corrupted token files are handled safely without crashing."""
    p = SwiggyRestaurantProvider()
    empty_file = tmp_path / "empty.json"
    empty_file.write_text("")
    p.token_path = str(empty_file)

    assert await p._try_refresh_token() is None
    with pytest.raises(Exception, match="Failed to read Swiggy token file"):
        p._get_token()

    corrupt_file = tmp_path / "corrupt.json"
    corrupt_file.write_text("NOT_VALID_JSON{")
    p.token_path = str(corrupt_file)

    assert await p._try_refresh_token() is None
    with pytest.raises(Exception, match="Failed to read Swiggy token file"):
        p._get_token()

