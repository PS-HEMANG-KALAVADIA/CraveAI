import os
import json
import base64
import hashlib
import secrets
import tempfile
import time
from typing import Optional, Dict, Any
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
import httpx

router = APIRouter()

# Keep PKCE verifier in memory for the callback
auth_sessions = {}

CLIENT_ID = "swiggy-mcp"
REDIRECT_URI = "http://localhost:8000/api/swiggy/callback"

def get_backend_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def get_token_path() -> str:
    return os.path.join(get_backend_dir(), ".swiggy_token.json")

def get_auth_state_path() -> str:
    return os.path.join(get_backend_dir(), ".swiggy_auth_state.json")

def decode_jwt_payload_unverified(token: str) -> Optional[Dict[str, Any]]:
    """Safely decode JWT payload without verification to inspect claims like exp."""
    if not token or not isinstance(token, str):
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        payload_b64 = parts[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        decoded = base64.urlsafe_b64decode(padded)
        payload = json.loads(decoded)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None

def check_swiggy_token_status(
    token_path: Optional[str] = None,
    state_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Check Swiggy authentication status strictly against local credential validity.
    Does NOT ping remote Swiggy OAuth or MCP endpoints on every check to avoid
    rate limits, unnecessary network roundtrips, or invalidating healthy sessions.
    
    Returns:
      connected: bool
      status: "connected" | "not_connected" | "reauth_required"
      authenticated: bool (for backward compatibility)
      login_url: str
    """
    t_path = token_path if token_path is not None else get_token_path()
    s_path = state_path if state_path is not None else (
        os.path.join(os.path.dirname(os.path.abspath(t_path)), ".swiggy_auth_state.json")
        if token_path else get_auth_state_path()
    )
    
    login_url = "http://localhost:8000/api/swiggy/login"
    
    # 1. Check if token file exists
    if not os.path.exists(t_path):
        if os.path.exists(s_path):
            try:
                with open(s_path, "r", encoding="utf-8") as f:
                    st_data = json.load(f)
                    if isinstance(st_data, dict) and st_data.get("status") == "reauth_required":
                        return {
                            "connected": False,
                            "status": "reauth_required",
                            "authenticated": False,
                            "login_url": login_url
                        }
            except Exception:
                pass
        return {
            "connected": False,
            "status": "not_connected",
            "authenticated": False,
            "login_url": login_url
        }
        
    # 2. Token file exists: safely parse content
    try:
        with open(t_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {
                    "connected": False,
                    "status": "not_connected",
                    "authenticated": False,
                    "login_url": login_url
                }
            data = json.loads(content)
            if not isinstance(data, dict):
                return {
                    "connected": False,
                    "status": "not_connected",
                    "authenticated": False,
                    "login_url": login_url
                }
    except Exception:
        return {
            "connected": False,
            "status": "not_connected",
            "authenticated": False,
            "login_url": login_url
        }

    # 3. Check for explicit invalidated / reauth marker in token file or state file
    if data.get("invalid") is True or data.get("status") == "reauth_required" or data.get("error") == "invalid_grant":
        return {
            "connected": False,
            "status": "reauth_required",
            "authenticated": False,
            "login_url": login_url
        }
        
    if os.path.exists(s_path):
        try:
            with open(s_path, "r", encoding="utf-8") as f:
                st_data = json.load(f)
                if isinstance(st_data, dict) and st_data.get("status") == "reauth_required":
                    return {
                        "connected": False,
                        "status": "reauth_required",
                        "authenticated": False,
                        "login_url": login_url
                    }
        except Exception:
            pass

    # 4. Check credentials presence
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    
    if not access_token and not refresh_token:
        return {
            "connected": False,
            "status": "not_connected",
            "authenticated": False,
            "login_url": login_url
        }

    # 5. Check token expiration
    now = time.time()
    
    # Check access token exp
    access_token_expired = False
    if access_token and isinstance(access_token, str):
        jwt_payload = decode_jwt_payload_unverified(access_token)
        if jwt_payload and "exp" in jwt_payload:
            exp = jwt_payload["exp"]
            if isinstance(exp, (int, float)) and exp <= now:
                access_token_expired = True
        elif "expires_at" in data:
            exp = data["expires_at"]
            if isinstance(exp, (int, float)) and exp <= now:
                access_token_expired = True
    elif not access_token:
        access_token_expired = True

    # Check refresh token exp
    refresh_token_expired = False
    if refresh_token and isinstance(refresh_token, str):
        ref_payload = decode_jwt_payload_unverified(refresh_token)
        if ref_payload and "exp" in ref_payload:
            ref_exp = ref_payload["exp"]
            if isinstance(ref_exp, (int, float)) and ref_exp <= now:
                refresh_token_expired = True
        elif "refresh_expires_at" in data:
            ref_exp = data["refresh_expires_at"]
            if isinstance(ref_exp, (int, float)) and ref_exp <= now:
                refresh_token_expired = True

    # If refresh token itself is expired, reauthentication is required
    if refresh_token and refresh_token_expired:
        return {
            "connected": False,
            "status": "reauth_required",
            "authenticated": False,
            "login_url": login_url
        }

    # If access token is expired and there is no refresh token, reauthentication is required
    if access_token_expired and not refresh_token:
        return {
            "connected": False,
            "status": "reauth_required",
            "authenticated": False,
            "login_url": login_url
        }

    # Otherwise valid credentials exist
    return {
        "connected": True,
        "status": "connected",
        "authenticated": True,
        "login_url": login_url
    }

@router.get("/swiggy/login")
async def swiggy_login():
    """Start the Swiggy OAuth 2.1 PKCE flow."""
    verifier = secrets.token_urlsafe(32)
    challenge_bytes = hashlib.sha256(verifier.encode("utf-8")).digest()
    challenge = base64.urlsafe_b64encode(challenge_bytes).decode("utf-8").rstrip("=")
    
    state = secrets.token_urlsafe(16)
    auth_sessions[state] = verifier
    
    auth_url = (
        f"https://mcp.swiggy.com/auth/authorize?"
        f"response_type=code&"
        f"client_id={CLIENT_ID}&"
        f"redirect_uri={REDIRECT_URI}&"
        f"code_challenge={challenge}&"
        f"code_challenge_method=S256&"
        f"state={state}&"
        f"scope=mcp:tools"
    )
    return RedirectResponse(url=auth_url)


@router.get("/swiggy/status")
async def swiggy_status():
    """Check Swiggy connection status."""
    return check_swiggy_token_status()


@router.post("/swiggy/logout")
@router.get("/swiggy/logout")
async def swiggy_logout():
    """Clear Swiggy stored tokens and reset connection state."""
    token_path = get_token_path()
    state_path = get_auth_state_path()
    if os.path.exists(token_path):
        try:
            os.remove(token_path)
        except Exception:
            pass
    if os.path.exists(state_path):
        try:
            os.remove(state_path)
        except Exception:
            pass
    return {
        "connected": False,
        "status": "not_connected",
        "authenticated": False,
        "message": "Successfully logged out from Swiggy."
    }


def _atomic_write_json(file_path: str, data: dict) -> None:
    dir_name = os.path.dirname(os.path.abspath(file_path))
    os.makedirs(dir_name, exist_ok=True)
    temp_file = tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8")
    try:
        json.dump(data, temp_file, indent=2)
        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_file.close()
        os.replace(temp_file.name, file_path)
    except Exception:
        if os.path.exists(temp_file.name):
            try:
                os.remove(temp_file.name)
            except Exception:
                pass
        raise


@router.get("/swiggy/callback")
async def swiggy_callback(request: Request):
    """Handle the Swiggy OAuth callback and exchange the code for a token."""
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")
        
    verifier = auth_sessions.pop(state, None)
    if not verifier:
        raise HTTPException(status_code=400, detail="Invalid state")
        
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://mcp.swiggy.com/auth/token",
            json={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": REDIRECT_URI
            }
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Failed to exchange token: {response.text}")
            
        token_data = response.json()
        
        # Save token to file atomically
        token_path = get_token_path()
        _atomic_write_json(token_path, token_data)
        
        # Clear any prior reauth/invalid state
        state_path = get_auth_state_path()
        if os.path.exists(state_path):
            try:
                os.remove(state_path)
            except Exception:
                pass
            
        return {"message": "Successfully authenticated with Swiggy! Token saved to .swiggy_token.json. You can close this window."}
