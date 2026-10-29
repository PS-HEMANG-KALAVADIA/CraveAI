import os
import json
import logging
import asyncio
import re
import tempfile
import time
from typing import List, Dict, Any, Optional, Tuple
from contextlib import asynccontextmanager

import anyio
import httpx
import mcp.types as types
from mcp.client.session import ClientSession
from mcp.shared.exceptions import McpError
from .base import RestaurantProvider

logger = logging.getLogger(__name__)


@asynccontextmanager
async def streamable_http_client(url: str, headers: Optional[Dict[str, str]] = None, timeout: float = 30.0):
    """
    Client transport for MCP over Streamable HTTP.
    Sends JSON-RPC requests via POST to the MCP endpoint and reads JSON-RPC responses
    or SSE stream events from the response body.
    """
    read_stream_writer, read_stream = anyio.create_memory_object_stream(50)
    write_stream, write_stream_reader = anyio.create_memory_object_stream(50)

    req_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        **(headers or {})
    }

    async with anyio.create_task_group() as tg:
        async with httpx.AsyncClient(headers=req_headers, timeout=timeout) as client:
            async def post_worker():
                try:
                    async with write_stream_reader:
                        async for message in write_stream_reader:
                            body = message.model_dump(by_alias=True, mode="json", exclude_none=True)
                            req_id = body.get("id")
                            try:
                                resp = await client.post(url, json=body)
                                if resp.status_code == 401:
                                    if req_id is not None:
                                        err = types.JSONRPCMessage(types.JSONRPCError(
                                            jsonrpc="2.0",
                                            id=req_id,
                                            error=types.ErrorData(
                                                code=-32001,
                                                message="Swiggy authentication failed: Access token is missing or expired (HTTP 401)."
                                            )
                                        ))
                                        await read_stream_writer.send(err)
                                    continue

                                resp.raise_for_status()

                                if resp.status_code in (202, 204) or not resp.content:
                                    continue

                                ct = resp.headers.get("content-type", "")
                                if "application/json" in ct:
                                    data = resp.json()
                                    if isinstance(data, list):
                                        for item in data:
                                            msg = types.JSONRPCMessage.model_validate(item)
                                            await read_stream_writer.send(msg)
                                    else:
                                        msg = types.JSONRPCMessage.model_validate(data)
                                        await read_stream_writer.send(msg)
                                elif "text/event-stream" in ct:
                                    for line in resp.text.splitlines():
                                        line = line.strip()
                                        if line.startswith("data:"):
                                            json_str = line[5:].strip()
                                            if json_str:
                                                msg = types.JSONRPCMessage.model_validate_json(json_str)
                                                await read_stream_writer.send(msg)
                            except httpx.HTTPStatusError as e:
                                if req_id is not None:
                                    err = types.JSONRPCMessage(types.JSONRPCError(
                                        jsonrpc="2.0",
                                        id=req_id,
                                        error=types.ErrorData(
                                            code=-32603,
                                            message=f"HTTP {e.response.status_code} error from Swiggy MCP service."
                                        )
                                    ))
                                    await read_stream_writer.send(err)
                            except Exception as e:
                                if req_id is not None:
                                    err = types.JSONRPCMessage(types.JSONRPCError(
                                        jsonrpc="2.0",
                                        id=req_id,
                                        error=types.ErrorData(
                                            code=-32603,
                                            message=f"Transport error connecting to Swiggy MCP: {type(e).__name__}"
                                        )
                                    ))
                                    await read_stream_writer.send(err)
                finally:
                    await read_stream_writer.aclose()

            tg.start_soon(post_worker)
            try:
                yield read_stream, write_stream
            finally:
                tg.cancel_scope.cancel()
                await read_stream_writer.aclose()
                await write_stream.aclose()


def _sanitize_log_str(s: str, token: Optional[str] = None, refresh_token: Optional[str] = None) -> str:
    if not s:
        return ""
    clean = str(s)
    if token:
        clean = clean.replace(token, "[REDACTED]")
    if refresh_token:
        clean = clean.replace(refresh_token, "[REDACTED]")
    clean = re.sub(r'Bearer\s+[A-Za-z0-9._~+/-]+=*', 'Bearer [REDACTED]', clean, flags=re.IGNORECASE)
    clean = re.sub(r'eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]*', '[REDACTED_JWT]', clean)
    return clean


def _read_token_file(file_path: str) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Token file does not exist: {file_path}")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                raise ValueError("Token file is empty")
            data = json.loads(content)
            if not isinstance(data, dict):
                raise ValueError("Token file root must be a JSON object")
            return data
    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(f"Failed to parse token file: {e}") from e


def _atomic_write_token_file(file_path: str, data: Dict[str, Any]) -> None:
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


class SwiggyRestaurantProvider(RestaurantProvider):
    _path_locks: Dict[Tuple[Optional[asyncio.AbstractEventLoop], str], asyncio.Lock] = {}

    @classmethod
    def _get_path_lock(cls, path: str) -> asyncio.Lock:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        canon_path = os.path.abspath(path)
        key = (loop, canon_path)
        if key not in cls._path_locks:
            cls._path_locks[key] = asyncio.Lock()
        return cls._path_locks[key]

    def __init__(self, token_path: Optional[str] = None):
        if token_path:
            self.token_path = token_path
        else:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
            self.token_path = os.path.join(root_dir, "backend", ".swiggy_token.json")
        self.mcp_url = "https://mcp.swiggy.com/food"

    def _get_token(self) -> str:
        """Read token without logging its contents."""
        if not os.path.exists(self.token_path):
            raise Exception("Swiggy authentication missing. Please authenticate via /api/swiggy/login first.")

        try:
            data = _read_token_file(self.token_path)
        except Exception:
            raise Exception("Failed to read Swiggy token file. Please re-authenticate via /api/swiggy/login.")

        token = data.get("access_token")
        if not token:
            raise Exception("Invalid Swiggy token format. Please re-authenticate via /api/swiggy/login.")

        return token

    async def _try_refresh_token(self, failed_token: Optional[str] = None) -> Optional[str]:
        """Attempt to refresh an expired token using refresh_token strictly adhering to Swiggy OAuth docs."""
        if not os.path.exists(self.token_path):
            return None

        lock = self._get_path_lock(self.token_path)
        async with lock:
            # 1. Safely parse stored token file
            try:
                data = _read_token_file(self.token_path)
            except Exception as e:
                logger.warning("Error reading Swiggy token file for refresh: %s", type(e).__name__)
                return None

            current_access = data.get("access_token")

            # 2. Check for stale token state / resolution from concurrent refresh
            if failed_token and current_access and current_access != failed_token:
                logger.info("Swiggy token was already refreshed by another concurrent task.")
                return current_access

            refresh_tok = data.get("refresh_token")
            if not refresh_tok:
                logger.warning("No refresh_token found in Swiggy token file.")
                return None

            # 3. Documented refresh request contract:
            # POST https://mcp.swiggy.com/auth/token
            # Content-Type: application/json
            # Body: {"grant_type": "refresh_token", "refresh_token": "<stored refresh token>"}
            # No client_id or authorization headers.
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            body = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_tok
            }

            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        "https://mcp.swiggy.com/auth/token",
                        headers=headers,
                        json=body
                    )

                if resp.status_code == 200:
                    new_data = resp.json()
                    new_access = new_data.get("access_token")
                    if not new_access:
                        logger.warning("Swiggy token refresh response missing access_token.")
                        return None

                    # Swiggy rotates refresh tokens. Persist new tokens immediately.
                    updated_data = dict(data)
                    updated_data.update(new_data)
                    _atomic_write_token_file(self.token_path, updated_data)
                    try:
                        state_path = os.path.join(os.path.dirname(os.path.abspath(self.token_path)), ".swiggy_auth_state.json")
                        if os.path.exists(state_path):
                            os.remove(state_path)
                    except Exception:
                        pass
                    logger.info("Swiggy token refreshed and rotated successfully.")
                    return new_access

                # Error handling: capture and safely inspect error and error_description
                error_code = "unknown_error"
                error_desc = "No description provided"
                try:
                    err_json = resp.json()
                    if isinstance(err_json, dict):
                        error_code = err_json.get("error", "unknown_error")
                        error_desc = err_json.get("error_description", "")
                except Exception:
                    error_desc = resp.text[:200] if resp.text else "empty response"

                safe_desc = _sanitize_log_str(str(error_desc), token=current_access, refresh_token=refresh_tok)
                safe_code = _sanitize_log_str(str(error_code))
                logger.warning(
                    "Swiggy token refresh failed with status %d: %s (%s)",
                    resp.status_code,
                    safe_code,
                    safe_desc
                )

                # Stop retrying on 400 invalid_grant:
                # Invalidate the stored token so future calls do not retry the bad refresh token
                # and require fresh OAuth flow via login/callback routes.
                if resp.status_code == 400 and error_code == "invalid_grant":
                    logger.warning("Swiggy refresh token is invalid or expired (invalid_grant). Clearing stored token.")
                    try:
                        if os.path.exists(self.token_path):
                            os.remove(self.token_path)
                    except Exception as e:
                        logger.warning("Could not remove invalid token file: %s", type(e).__name__)
                    try:
                        state_path = os.path.join(os.path.dirname(os.path.abspath(self.token_path)), ".swiggy_auth_state.json")
                        _atomic_write_token_file(state_path, {
                            "status": "reauth_required",
                            "reason": "invalid_grant",
                            "updated_at": time.time()
                        })
                    except Exception as se:
                        logger.warning("Could not write auth state file: %s", type(se).__name__)

                return None

            except Exception as e:
                logger.warning("Error during Swiggy token refresh request: %s", type(e).__name__)
                return None

    def _unwrap_exceptions(self, exc: BaseException) -> List[BaseException]:
        res = []
        if isinstance(exc, BaseExceptionGroup):
            for sub in exc.exceptions:
                res.extend(self._unwrap_exceptions(sub))
        else:
            res.append(exc)
        return res

    async def _run_with_session(self, callback):
        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}"}

        try:
            async with streamable_http_client(url=self.mcp_url, headers=headers) as streams:
                read_stream, write_stream = streams
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    return await callback(session)
        except BaseException as root_e:
            all_errors = self._unwrap_exceptions(root_e)
            
            # Check for McpError or 401 / unauthorized / authentication errors
            auth_error = False
            for err in all_errors:
                err_str = str(err).lower()
                if isinstance(err, McpError) and (err.error.code == -32001 or "authentication" in err_str or "401" in err_str or "unauthorized" in err_str):
                    auth_error = True
                    break
                if "401" in err_str or "unauthorized" in err_str or "invalid_token" in err_str or "jwt has expired" in err_str:
                    auth_error = True
                    break

            if auth_error:
                new_token = await self._try_refresh_token(failed_token=token)
                if new_token:
                    headers = {"Authorization": f"Bearer {new_token}"}
                    async with streamable_http_client(url=self.mcp_url, headers=headers) as streams:
                        read_stream, write_stream = streams
                        async with ClientSession(read_stream, write_stream) as session:
                            await session.initialize()
                            return await callback(session)
                try:
                    state_path = os.path.join(os.path.dirname(os.path.abspath(self.token_path)), ".swiggy_auth_state.json")
                    _atomic_write_token_file(state_path, {
                        "status": "reauth_required",
                        "reason": "session_expired",
                        "updated_at": time.time()
                    })
                except Exception:
                    pass
                raise Exception("Swiggy session expired. Please re-authenticate at /api/swiggy/login")

            # Check for other specific errors
            for err in all_errors:
                if isinstance(err, McpError):
                    clean_msg = err.error.message.replace(token, "[REDACTED]") if token else err.error.message
                    raise Exception(f"Swiggy MCP error: {clean_msg}")
                err_str = str(err).lower()
                if "authentication" in err_str or "missing" in err_str or "expired" in err_str:
                    clean_err = str(err).replace(token, "[REDACTED]") if token else str(err)
                    raise Exception(clean_err)
            
            primary_msg = str(all_errors[0]) if all_errors else str(root_e)
            clean_msg = primary_msg.replace(token, "[REDACTED]") if token else primary_msg
            raise Exception(f"Swiggy MCP error: {clean_msg}")

    @staticmethod
    def _parse_json_response(text: str) -> Any:
        if not text:
            return {}
        cleaned = text.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Swiggy MCP tool responses often append instruction text after the JSON payload,
        # e.g.: {...}\n\n⚠️ A rich UI widget may be shown to the user with this data.
        # Use JSONDecoder.raw_decode to extract the valid JSON object.
        try:
            start_idx = 0
            for i, ch in enumerate(cleaned):
                if ch in ('{', '['):
                    start_idx = i
                    break
            decoder = json.JSONDecoder()
            obj, _ = decoder.raw_decode(cleaned[start_idx:])
            return obj
        except Exception:
            pass

        import re
        match = re.search(r'```(?:json)?\s*([\{\[].*?[\}\]])\s*```', cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass

        raise Exception("Malformed JSON response from Swiggy tool")

    @staticmethod
    def _parse_menu_search_text(text: str) -> List[Dict[str, Any]]:
        """Parses the response of Swiggy search_menu tool (JSON or formatted text) into structured items."""
        import re
        items = []
        if not text:
            return items

        trimmed = text.strip()
        if trimmed.startswith("{") or trimmed.startswith("["):
            try:
                raw_json = json.loads(trimmed)
                raw_list = raw_json.get("items", []) if isinstance(raw_json, dict) else raw_json
                if isinstance(raw_list, list):
                    for obj in raw_list:
                        if isinstance(obj, dict):
                            is_avail = obj.get("is_available", obj.get("inStock", True))
                            obj_str = str(obj).lower()
                            if is_avail and ("out of stock" in obj_str or "unavailable" in obj_str):
                                is_avail = False
                            price_val = obj.get("price", 0.0)
                            try:
                                price_float = float(price_val)
                            except (ValueError, TypeError):
                                price_float = 0.0
                            rating_val = obj.get("rating")
                            try:
                                rating_float = float(rating_val) if rating_val is not None else None
                            except (ValueError, TypeError):
                                rating_float = None
                            p_type, p_label = SwiggyRestaurantProvider.classify_item_product_type(obj.get("name", ""), "")
                            items.append({
                                'name': obj.get("name", ""),
                                'price': price_float,
                                'rating': rating_float,
                                'veg': bool(obj.get("veg", False)),
                                'restaurant_name': obj.get("restaurantName", obj.get("restaurant_name", "")),
                                'restaurant_id': str(obj.get("restaurantId", obj.get("restaurant_id", ""))),
                                'is_available': bool(is_avail),
                                'product_type': p_type,
                                'product_type_label': p_label
                            })
                    if items:
                        return items
            except Exception:
                pass
            
        line_pattern = re.compile(
            r'^\s*\d+\.\s+(?P<name>.+?)\s+[—–-]\s+₹(?P<price>[\d\.]+)\s*\|\s*(?P<rest>.*)$'
        )
        for line in text.splitlines():
            line = line.strip()
            m = line_pattern.match(line)
            if not m:
                continue
            name = m.group('name').strip()
            try:
                price = float(m.group('price'))
            except (ValueError, TypeError):
                price = 0.0
                
            rest_part = m.group('rest')
            
            # restaurantId and name
            r_match = re.search(r'\|\s*([^|]+?)\s*\(restaurantId:\s*(\w+)\)', rest_part)
            rest_name = r_match.group(1).strip() if r_match else ''
            rest_id = r_match.group(2).strip() if r_match else ''
            
            # rating
            rating_match = re.search(r'([\d\.]+)★', rest_part)
            rating = float(rating_match.group(1)) if rating_match else None
            
            # veg
            is_veg = 'Veg' in rest_part

            # availability
            is_unavail = "out of stock" in line.lower() or "unavailable" in line.lower()
            
            p_type, p_label = SwiggyRestaurantProvider.classify_item_product_type(name, "")
            items.append({
                'name': name,
                'price': price,
                'rating': rating,
                'veg': is_veg,
                'restaurant_name': rest_name,
                'restaurant_id': rest_id,
                'is_available': not is_unavail,
                'product_type': p_type,
                'product_type_label': p_label
            })
        return items

    @staticmethod
    def classify_item_product_type(item_name: str, requested_dish: str = "") -> Tuple[str, str]:
        """Classifies menu items into 'prepared', 'packaged', 'side', or 'unspecified'. Returns (product_type, product_type_label)."""
        if not item_name:
            return "unspecified", "Unspecified Product Type"

        import re
        name_lower = item_name.lower().strip()
        dish_lower = (requested_dish or "").lower().strip()

        # 1. Sides / Potato shapes / Alternative cuts (e.g. Waffle fries vs Waffle pastry)
        if "waffle" in dish_lower or not dish_lower:
            if re.search(r'\bwaffle\s+(?:fries|fry|chips|crisps|potato)\b', name_lower) or re.search(r'\b(?:french\s+fries|fries|potato\s+wedges)\b', name_lower):
                return "side", "Side / Snack"

        # 2. Packaged FMCG / Retail goods
        packaged_keywords = [
            r'\btubes?\b',
            r'\bpre-?mix\b',
            r'\bbatter\b',
            r'\bsyrups?\b',
            r'\bspreads?\b',
            r'\bpack(?:et)?(?:\s+of)?\b',
            r'\bbox\b',
            r'\btin\b',
            r'\bbiscuits?\b',
            r'\bcookies?\b',
            r'\bchips?\b',
            r'\bcone(?:\s+pack)?\b',
            r'\bbar(?:\s+pack)?\b',
            r'\bcrisps?\b'
        ]
        has_weight = bool(re.search(r'\(\s*\d+\s*(?:g|gm|gms|grams|kg|ml|ltr)\s*\)|\b\d+\s*(?:g|gm|gms|grams|kg|ml|ltr)\b', name_lower))
        has_packaged_kw = any(re.search(pat, name_lower) for pat in packaged_keywords)

        if has_packaged_kw or (has_weight and not re.search(r'\b(?:\d+\s*(?:pc|piece|pieces|slice|slices))\b', name_lower)):
            return "packaged", "Packaged Product"

        # 3. Freshly prepared dishes
        fresh_terms = [
            "waffle", "puri", "kachori", "dhokla", "dosa", "pizza", "burger", "biryani",
            "sandwich", "chaat", "pasta", "noodles", "pancake", "crepe", "cake", "shake"
        ]
        if any(term in name_lower for term in fresh_terms) or (dish_lower and dish_lower in name_lower):
            return "prepared", "Freshly Prepared"

        return "unspecified", "Unspecified Product Type"

    @staticmethod
    def clean_restaurant_name(name: str) -> str:
        """Removes advertising tags like (Ad), (AD), (ad) and trims extraneous whitespace."""
        if not name:
            return ""
        import re
        return re.sub(r'\s*\([Aa][Dd]\)\s*$', '', name).strip()

    @staticmethod
    def build_swiggy_search_urls(
        rest_name: str,
        dish_name: str = "",
        is_local_restaurant: bool = True,
        canonical_url: str = ""
    ) -> Dict[str, str]:
        """
        Builds the best verified Swiggy URL and fallback URL strategy based on real storefront behavior.
        
        Strategy:
        1. Prefer canonical restaurant URL if returned by Swiggy provider.
        2. If restaurant is in local restaurant directory (is_local_restaurant=True):
           - If dish_name is available: Primary is combined search ({rest_name} {dish_name}),
             and fallback is dish-only search ({dish_name}).
           - Otherwise: Primary is restaurant-only search ({rest_name}).
        3. If restaurant is merged from item search and not in local restaurant directory (is_local_restaurant=False):
           - In real storefront tests, combined and restaurant-only searches return empty illustrations (0 results)
             because the outlet is outside the local delivery polygon.
           - Use dish-focused search as primary fallback ({dish_name}) which succeeds on Swiggy,
             and restaurant name as secondary fallback.
        """
        import urllib.parse
        if canonical_url and isinstance(canonical_url, str) and canonical_url.startswith("http"):
            return {
                "url": canonical_url,
                "url_type": "canonical",
                "fallback_url": "",
                "fallback_url_type": "none"
            }

        clean_name = SwiggyRestaurantProvider.clean_restaurant_name(rest_name)
        clean_dish = (dish_name or "").strip()

        if not clean_name and not clean_dish:
            return {
                "url": "",
                "url_type": "none",
                "fallback_url": "",
                "fallback_url_type": "none"
            }

        encoded_rest = urllib.parse.quote_plus(clean_name, safe='') if clean_name else ""
        encoded_dish = urllib.parse.quote_plus(clean_dish, safe='') if clean_dish else ""

        if is_local_restaurant:
            if clean_name and clean_dish and clean_dish.lower() not in clean_name.lower():
                combined_term = f"{clean_name} {clean_dish}".strip()
                encoded_combined = urllib.parse.quote_plus(combined_term, safe='')
                return {
                    "url": f"https://www.swiggy.com/search?query={encoded_combined}",
                    "url_type": "search",
                    "fallback_url": f"https://www.swiggy.com/search?query={encoded_dish}" if encoded_dish else "",
                    "fallback_url_type": "dish_fallback" if encoded_dish else "none"
                }
            elif clean_name:
                return {
                    "url": f"https://www.swiggy.com/search?query={encoded_rest}",
                    "url_type": "restaurant_search",
                    "fallback_url": f"https://www.swiggy.com/search?query={encoded_dish}" if encoded_dish else "",
                    "fallback_url_type": "dish_fallback" if encoded_dish else "none"
                }
            else:
                return {
                    "url": f"https://www.swiggy.com/search?query={encoded_dish}",
                    "url_type": "dish_fallback",
                    "fallback_url": "",
                    "fallback_url_type": "none"
                }
        else:
            # Merged restaurant from menu search not in local restaurant directory
            # Combined query returns no results, but dish-only query works
            if clean_dish:
                return {
                    "url": f"https://www.swiggy.com/search?query={encoded_dish}",
                    "url_type": "dish_fallback",
                    "fallback_url": f"https://www.swiggy.com/search?query={encoded_rest}" if encoded_rest else "",
                    "fallback_url_type": "restaurant_fallback" if encoded_rest else "none"
                }
            elif clean_name:
                return {
                    "url": f"https://www.swiggy.com/search?query={encoded_rest}",
                    "url_type": "restaurant_search",
                    "fallback_url": "",
                    "fallback_url_type": "none"
                }
            else:
                return {
                    "url": "",
                    "url_type": "none",
                    "fallback_url": "",
                    "fallback_url_type": "none"
                }

    @classmethod
    def _extract_all_dish_queries(cls, query: str) -> List[Tuple[str, List[str], List[str]]]:
        """Extracts all recognized dishes or comma/and-separated terms into (core_dish, aliases, styles)."""
        import re
        q = (query or "").lower().strip()
        if not q or q in ("food", "restaurant", "restaurants"):
            return []

        known_aliases = {
            'pani puri': ['pani puri', 'paani puri', 'panipuri', 'golgappa', 'puchka', 'pakodi'],
            'kachori': ['kachori'],
            'dal baati': ['dal baati', 'daal baati', 'dal bati'],
            'vada pav': ['vada pav', 'vadapav', 'wada pav', 'wada pao', 'vada pao', 'vadapau'],
            'chole bhature': ['chole bhature', 'bhature'],
            'dhokla': ['dhokla', 'khaman'],
            'thepla': ['thepla'],
            'biryani': ['biryani'],
            'dosa': ['dosa'],
            'pizza': ['pizza'],
            'burger': ['burger'],
            'chaat': ['chaat', 'bhel', 'sev puri', 'dahi puri', 'samosa chaat', 'papdi chaat'],
            'waffle': ['waffle', 'waffles', 'belgian waffle', 'belgian waffles', 'chocolate waffle', 'nutella waffle'],
            'dessert': ['dessert', 'desserts', 'sweet', 'sweets'],
            'ice cream': ['ice cream', 'icecream', 'gelato', 'sorbet'],
            'sandwich': ['sandwich', 'sandwiches'],
            'pasta': ['pasta'],
            'noodles': ['noodles', 'chowmein', 'maggi'],
            'coffee': ['coffee', 'cappuccino', 'latte', 'espresso'],
            'tea': ['tea', 'chai']
        }

        style_keywords = [
            "jaipur", "rajasthan", "rajasthani", "jodhpur", "jodhpuri", "pyaz", "pyaaz", "onion",
            "bombay", "mumbai", "mumbaiya", "maharashtrian",
            "delhi", "amritsari", "kolkata", "bengali", "south indian", "hyderabadi", "lucknowi", "gujarati", "indori"
        ]
        found_styles = [s for s in style_keywords if s in q]

        results = []
        for dish_key, aliases in known_aliases.items():
            if any(re.search(rf'\b{re.escape(a)}\b', q) for a in aliases) or dish_key in q:
                results.append((dish_key, aliases, found_styles))

        if results:
            return results

        # If no known aliases matched, split by comma or 'and'
        parts = [p.strip() for p in re.split(r'[,&]|\band\b', q) if p.strip()]
        fluff = {
            'suggest', 'me', 'places', 'place', 'for', 'in', 'at', 'near', 'nearby', 'best', 
            'authentic', 'style', 'good', 'top', 'famous', 'traditional', 'cheap', 'hot', 'spicy', 
            'this', 'these', 'i', 'wanna', 'want', 'to', 'have', 'eat', 'order', 'find', 'get', 
            'some', 'craving', 'crave', 'recommend', 'recommendation', 'recommendations', 'around',
            'like', 'looking', 'show', 'options', 'food', 'restaurant', 'restaurants'
        }
        for part in parts:
            words = [w for w in re.findall(r'\w+', part) if w not in fluff]
            core = " ".join(words) if words else part
            if core and core not in fluff:
                results.append((core, [core], found_styles))

        if not results:
            words = [w for w in re.findall(r'\w+', q) if w not in fluff]
            core = " ".join(words) if words else q
            if core and core not in fluff:
                results.append((core, [core], found_styles))

        return results

    @classmethod
    def _extract_core_dish_keywords(cls, query: str):
        """Extracts primary core dish keyword, search aliases, and style keywords for backward compatibility."""
        dishes = cls._extract_all_dish_queries(query)
        if dishes:
            return dishes[0]
        return query or "", [query] if query else [], []

    async def search_nearby_restaurants(
        self,
        latitude: float,
        longitude: float,
        query: Optional[str] = None,
        radius_meters: int = 5000,
        price_tier: Optional[str] = None
    ) -> List[Dict[str, Any]]:

        async def _do_search(session: ClientSession):
            # 1. Discover tools dynamically
            tools_response = await session.list_tools()
            available_tools = {t.name: t for t in tools_response.tools}

            if "search_restaurants" not in available_tools:
                raise Exception("Swiggy MCP error: 'search_restaurants' tool not found on Swiggy server.")

            search_tool = available_tools["search_restaurants"]
            schema = search_tool.inputSchema
            props = schema.get("properties", {})
            required_fields = schema.get("required", [])

            # 2. Build arguments based on actual schema
            args: Dict[str, Any] = {}

            # Coordinates handling
            has_coords = (latitude is not None and longitude is not None)
            if "latitude" in props and "longitude" in props and has_coords:
                args["latitude"] = float(latitude)
                args["longitude"] = float(longitude)
            elif "addressId" in props:
                # If schema expects addressId, check get_addresses
                if "get_addresses" in available_tools:
                    addr_res = await session.call_tool("get_addresses", {})
                    addr_text = addr_res.content[0].text if addr_res.content else "{}"
                    addresses = self._parse_json_response(addr_text)
                    addr_list = addresses.get("addresses", addresses) if isinstance(addresses, dict) else addresses
                    if isinstance(addr_list, list) and len(addr_list) > 0:
                        first_addr = addr_list[0]
                        args["addressId"] = first_addr.get("id") or first_addr.get("addressId")

            # Extract dish queries
            dish_queries = self._extract_all_dish_queries(query) if query else []
            query_val = (query or "").strip()
            if dish_queries:
                # Use primary dish for Swiggy restaurant search query to avoid failure on long multi-dish phrases
                args["query"] = dish_queries[0][0]
            elif query_val:
                args["query"] = query_val
            else:
                args["query"] = "food"

            # Radius if explicitly supported by schema
            if "radius_meters" in props and radius_meters:
                args["radius_meters"] = radius_meters
            elif "radius" in props and radius_meters:
                args["radius"] = radius_meters

            # Validate required fields
            for req in required_fields:
                if req not in args:
                    raise Exception(f"Missing required parameter '{req}' for Swiggy search_restaurants.")

            # 3. If query represents specific dish(es), perform cross-restaurant dish search via search_menu
            menu_items_by_rest_id: Dict[str, List[Dict[str, Any]]] = {}
            menu_items_by_rest_name: Dict[str, List[Dict[str, Any]]] = {}
            has_dish_search = bool(dish_queries)
            menu_search_failed = False

            if "search_menu" in available_tools and dish_queries:
                try:
                    menu_args_base: Dict[str, Any] = {}
                    if "latitude" in available_tools["search_menu"].inputSchema.get("properties", {}) and has_coords:
                        menu_args_base["latitude"] = float(latitude)
                        menu_args_base["longitude"] = float(longitude)
                    elif "addressId" in args:
                        menu_args_base["addressId"] = args["addressId"]

                    # Search up to 3 candidate dishes individually to retrieve authoritative menu items
                    for core_dish, aliases, styles in dish_queries[:3]:
                        menu_args = dict(menu_args_base)
                        menu_args["query"] = core_dish
                        try:
                            menu_res = await session.call_tool("search_menu", menu_args)
                            menu_text = menu_res.content[0].text if menu_res.content else ""
                            parsed_items = self._parse_menu_search_text(menu_text)

                            matched_items = [
                                it for it in parsed_items
                                if any(a in it["name"].lower() for a in aliases) or (core_dish and core_dish in it["name"].lower())
                            ]

                            # Query style sub-queries if needed (e.g. pyaaz kachori)
                            if len(matched_items) < 3 and styles:
                                for s in styles[:2]:
                                    menu_args["query"] = f"{s} {core_dish}"
                                    sub_res = await session.call_tool("search_menu", menu_args)
                                    sub_text = sub_res.content[0].text if sub_res.content else ""
                                    for it in self._parse_menu_search_text(sub_text):
                                        if any(a in it["name"].lower() for a in aliases) or (core_dish and core_dish in it["name"].lower()):
                                            if not any(ex["name"] == it["name"] and ex["restaurant_id"] == it["restaurant_id"] for ex in matched_items):
                                                matched_items.append(it)

                            for it in matched_items:
                                p_type, p_label = self.classify_item_product_type(it["name"], core_dish)
                                it["product_type"] = p_type
                                it["product_type_label"] = p_label
                                r_id = str(it.get("restaurant_id", "")).strip()
                                # Strictly index by restaurant_id.
                                # Global search items without restaurant ID MUST NOT be attributed to any specific restaurant.
                                if r_id:
                                    menu_items_by_rest_id.setdefault(r_id, []).append(it)
                        except Exception as single_e:
                            logger.warning(f"Error querying search_menu for '{core_dish}': {single_e}")
                            menu_search_failed = True
                except Exception as menu_e:
                    logger.warning(f"Error executing Swiggy search_menu: {menu_e}")
                    menu_search_failed = True

            # 4. Call search_restaurants
            search_result = await session.call_tool("search_restaurants", args)
            search_text = search_result.content[0].text if search_result.content else "{}"
            search_data = self._parse_json_response(search_text)

            # Handle explicit failure response
            if isinstance(search_data, dict) and search_data.get("success") is False:
                err_msg = (
                    search_data.get("error", {}).get("message")
                    or search_data.get("message")
                    or "Restaurant search service returned an unsuccessful response."
                )
                raise Exception(f"Swiggy search error: {err_msg}")

            # 5. Extract raw restaurants
            raw_restaurants = []
            if isinstance(search_data, dict):
                data_field = search_data.get("data", search_data)
                if isinstance(data_field, dict):
                    raw_restaurants = data_field.get("restaurants", [])
                elif isinstance(data_field, list):
                    raw_restaurants = data_field
                elif "restaurants" in search_data:
                    raw_restaurants = search_data["restaurants"]
            elif isinstance(search_data, list):
                raw_restaurants = search_data

            # 6. Standardize results with verified menu items & match categories
            results = []
            for r in raw_restaurants:
                # Distance calculation in meters
                dist_meters = 0.0
                if "distanceKm" in r and r["distanceKm"] is not None:
                    try:
                        dist_meters = float(r["distanceKm"]) * 1000.0
                    except (ValueError, TypeError):
                        dist_meters = 0.0
                elif "distance_meters" in r and r["distance_meters"] is not None:
                    try:
                        dist_meters = float(r["distance_meters"])
                    except (ValueError, TypeError):
                        dist_meters = 0.0
                elif "distance" in r and r["distance"] is not None:
                    try:
                        val = float(r["distance"])
                        dist_meters = val * 1000.0 if val < 50.0 else val
                    except (ValueError, TypeError):
                        dist_meters = 0.0

                # Price normalization
                raw_price = r.get("costForTwo", r.get("price", r.get("price_tier", "")))
                price_str = "$$"
                if isinstance(raw_price, (int, float)):
                    if raw_price < 300:
                        price_str = "$"
                    elif raw_price < 800:
                        price_str = "$$"
                    else:
                        price_str = "$$$"
                elif isinstance(raw_price, str):
                    digits = "".join(ch for ch in raw_price if ch.isdigit())
                    if digits:
                        num = int(digits)
                        if num < 300:
                            price_str = "$"
                        elif num < 800:
                            price_str = "$$"
                        else:
                            price_str = "$$$"
                    elif raw_price in ("$", "$$", "$$$"):
                        price_str = raw_price

                # Cuisines normalization
                cuisines = r.get("cuisines", r.get("cuisine", []))
                if isinstance(cuisines, str):
                    cuisines = [c.strip() for c in cuisines.split(",") if c.strip()]
                elif not isinstance(cuisines, list):
                    cuisines = []

                # Availability status (restaurant level)
                availability = r.get("availabilityStatus", "OPEN")
                is_closed = (str(availability).upper() != "OPEN") if availability else r.get("is_closed", r.get("closed", False))

                # Rating
                rating_val = r.get("avgRating", r.get("rating", 0.0))
                try:
                    rating_float = float(rating_val)
                except (ValueError, TypeError):
                    rating_float = 0.0

                rest_id = str(r.get("id", r.get("restaurantId", ""))).strip()
                raw_name = r.get("name", "Unknown")
                rest_name = self.clean_restaurant_name(raw_name)

                # Strict Match category & verified items:
                # Item must strictly belong to the same restaurant ID as the displayed restaurant card!
                confirmed_items = []
                if rest_id:
                    confirmed_items = [
                        it for it in menu_items_by_rest_id.get(rest_id, [])
                        if str(it.get("restaurant_id", "")).strip() == rest_id
                    ]

                match_category = "unverified"
                dish_avail = "unverified"
                matched_dishes_list = []
                match_reason = ""

                if confirmed_items:
                    match_category = "confirmed"
                    matched_dishes_list = [
                        {
                            "name": it["name"],
                            "price": it.get("price"),
                            "rating": it.get("rating"),
                            "is_available": it.get("is_available", True),
                            "product_type": it.get("product_type", "unspecified"),
                            "product_type_label": it.get("product_type_label", "Unspecified Product Type")
                        }
                        for it in confirmed_items
                    ]
                    all_unavail = all(it.get("is_available") is False for it in confirmed_items)
                    dish_avail = "unavailable" if all_unavail else "confirmed"

                    has_prepared = any(it.get("product_type") == "prepared" for it in confirmed_items)
                    has_packaged = any(it.get("product_type") == "packaged" for it in confirmed_items)
                    has_side = any(it.get("product_type") == "side" for it in confirmed_items)

                    all_styles = [s for dq in dish_queries for s in dq[2]]
                    exact_style_items = []
                    if all_styles:
                        exact_style_items = [
                            it for it in confirmed_items
                            if any(s in it["name"].lower() for s in all_styles)
                        ]
                    if all_styles and exact_style_items:
                        names_str = ", ".join(f"{it['name']} (₹{it.get('price', 0)})" for it in exact_style_items[:2])
                        match_reason = f"Confirmed exact style match on menu: {names_str}"
                    elif has_prepared:
                        fresh_names = [it for it in confirmed_items if it.get("product_type") == "prepared"]
                        names_str = ", ".join(f"{it['name']} (₹{it.get('price', 0)})" for it in fresh_names[:2])
                        match_reason = f"Confirmed menu item: {names_str}"
                    elif has_packaged:
                        names_str = ", ".join(f"{it['name']} (₹{it.get('price', 0)})" for it in confirmed_items[:2])
                        match_reason = f"Confirmed packaged item on menu: {names_str} (packaged retail item, not freshly prepared)"
                    elif has_side:
                        names_str = ", ".join(f"{it['name']} (₹{it.get('price', 0)})" for it in confirmed_items[:2])
                        match_reason = f"Confirmed side item on menu: {names_str} (side/snack, not fresh pastry)"
                    else:
                        names_str = ", ".join(f"{it['name']} (₹{it.get('price', 0)})" for it in confirmed_items[:2])
                        match_reason = f"Confirmed menu item: {names_str} (product type unverified)"

                elif has_dish_search:
                    all_aliases = [a for dq in dish_queries for a in dq[1]]
                    core_dishes = [dq[0] for dq in dish_queries]

                    if menu_search_failed:
                        match_category = "unverified"
                        dish_avail = "unverified"
                        match_reason = "Menu availability could not be verified at this time."
                    elif any(a in rest_name.lower() for a in all_aliases) or any(cd in rest_name.lower() for cd in core_dishes):
                        match_category = "possible"
                        dish_avail = "unavailable"
                        match_reason = f"Restaurant name suggests {core_dishes[0]}, but specific menu items were not found on retrieved menu."
                    elif any(c.lower() in ("snacks", "street food", "chaat", "fast food") for c in cuisines):
                        match_category = "possible"
                        dish_avail = "unavailable"
                        match_reason = f"Serves {', '.join(cuisines)}, but specific dish was not found on retrieved menu."
                    else:
                        match_category = "unverified"
                        dish_avail = "unavailable"
                        match_reason = "Restaurant is listed on Swiggy, but requested dish was not found on menu."

                # Check for canonical URL returned by Swiggy MCP
                canonical_url = (
                    r.get("url")
                    or r.get("canonicalUrl")
                    or r.get("link")
                    or (r.get("cta") if isinstance(r.get("cta"), dict) else {}).get("link")
                    or (r.get("ctaWithParams") if isinstance(r.get("ctaWithParams"), dict) else {}).get("link")
                    or ""
                )

                dish_for_search = ""
                if confirmed_items:
                    fresh_items = [it for it in confirmed_items if it.get("product_type") == "prepared"]
                    dish_for_search = fresh_items[0].get("name", "") if fresh_items else confirmed_items[0].get("name", "")
                elif dish_queries:
                    dish_for_search = dish_queries[0][0]

                url_info = self.build_swiggy_search_urls(
                    rest_name=rest_name,
                    dish_name=dish_for_search,
                    is_local_restaurant=True,
                    canonical_url=canonical_url
                )

                norm_r = {
                    "id": rest_id,
                    "name": rest_name,
                    "rating": rating_float,
                    "distance_meters": dist_meters,
                    "price": price_str,
                    "cuisine": cuisines,
                    "address": r.get("areaName", r.get("area", r.get("address", ""))),
                    "is_closed": bool(is_closed),
                    "url": url_info["url"],
                    "url_type": url_info["url_type"],
                    "fallback_url": url_info["fallback_url"],
                    "fallback_url_type": url_info["fallback_url_type"],
                    "match_category": match_category,
                    "matched_items": matched_dishes_list,
                    "match_reason": match_reason,
                    "dish_availability": dish_avail
                }

                # Optional price filter
                if price_tier and norm_r["price"] != price_tier:
                    continue

                results.append(norm_r)

            # 7. Merge confirmed restaurants from search_menu that weren't in search_restaurants
            existing_ids = {r["id"] for r in results if r.get("id")}
            existing_names = {r["name"].lower() for r in results if r.get("name")}

            for m_id, items in menu_items_by_rest_id.items():
                if not m_id or m_id in existing_ids:
                    continue
                first_it = items[0]
                m_raw = first_it.get("restaurant_name", "Unknown Restaurant")
                m_name = self.clean_restaurant_name(m_raw)
                if m_name.lower() in existing_names:
                    continue

                m_price = "$" if first_it.get("price", 0) < 300 else "$$"
                
                has_prepared = any(it.get("product_type") == "prepared" for it in items)
                has_packaged = any(it.get("product_type") == "packaged" for it in items)
                has_side = any(it.get("product_type") == "side" for it in items)

                # Check style alignment on merged items
                all_styles = [s for dq in dish_queries for s in dq[2]]
                exact_style_items = []
                if all_styles:
                    exact_style_items = [
                        it for it in items
                        if any(s in it["name"].lower() for s in all_styles)
                    ]
                if all_styles and exact_style_items:
                    names_str = ", ".join(f"{it['name']} (₹{it.get('price', 0)})" for it in exact_style_items[:2])
                    m_reason = f"Confirmed exact style match on menu: {names_str}"
                elif has_prepared:
                    fresh_names = [it for it in items if it.get("product_type") == "prepared"]
                    names_str = ", ".join(f"{it['name']} (₹{it.get('price', 0)})" for it in fresh_names[:2])
                    m_reason = f"Confirmed menu item: {names_str}"
                elif has_packaged:
                    names_str = ", ".join(f"{it['name']} (₹{it.get('price', 0)})" for it in items[:2])
                    m_reason = f"Confirmed packaged item on menu: {names_str} (packaged retail item, not freshly prepared)"
                elif has_side:
                    names_str = ", ".join(f"{it['name']} (₹{it.get('price', 0)})" for it in items[:2])
                    m_reason = f"Confirmed side item on menu: {names_str} (side/snack, not fresh pastry)"
                else:
                    names_str = ", ".join(f"{it['name']} (₹{it.get('price', 0)})" for it in items[:2])
                    m_reason = f"Confirmed menu item: {names_str} (product type unverified)"

                fresh_m = [it for it in items if it.get("product_type") == "prepared"]
                m_dish_name = fresh_m[0].get("name", "") if fresh_m else (items[0].get("name", "") if items else (dish_queries[0][0] if dish_queries else ""))

                # Merged restaurants were not returned in local search_restaurants.
                # In browser tests, combined search returns 0 results while dish search works.
                # Use dish-focused search fallback as primary, and restaurant name as secondary.
                m_url_info = self.build_swiggy_search_urls(
                    rest_name=m_name,
                    dish_name=m_dish_name,
                    is_local_restaurant=False,
                    canonical_url=""
                )

                all_unavail = all(it.get("is_available") is False for it in items)
                results.append({
                    "id": m_id,
                    "name": m_name,
                    "rating": first_it.get("rating") or 4.2,
                    "distance_meters": 3000.0,
                    "price": m_price,
                    "cuisine": ["Snacks", "Street Food"],
                    "address": "Ahmedabad",
                    "is_closed": False,
                    "url": m_url_info["url"],
                    "url_type": m_url_info["url_type"],
                    "fallback_url": m_url_info["fallback_url"],
                    "fallback_url_type": m_url_info["fallback_url_type"],
                    "match_category": "confirmed",
                    "matched_items": [
                        {
                            "name": it["name"],
                            "price": it.get("price"),
                            "rating": it.get("rating"),
                            "is_available": it.get("is_available", True),
                            "product_type": it.get("product_type", "unspecified"),
                            "product_type_label": it.get("product_type_label", "Unspecified Product Type")
                        }
                        for it in items
                    ],
                    "match_reason": m_reason,
                    "dish_availability": "unavailable" if all_unavail else "confirmed"
                })

            return results

        try:
            return await self._run_with_session(_do_search)
        except Exception as e:
            err_msg = str(e)
            import re
            err_msg = re.sub(r'Bearer\s+[A-Za-z0-9_\-\.]+', '[REDACTED]', err_msg)
            if hasattr(self, 'token_path') and self.token_path and os.path.exists(self.token_path):
                try:
                    with open(self.token_path) as f:
                        tok_data = json.load(f)
                        tok = tok_data.get("access_token")
                        if tok and tok in err_msg:
                            err_msg = err_msg.replace(tok, "[REDACTED]")
                except Exception:
                    pass
            raise Exception(err_msg)


clean_restaurant_name = SwiggyRestaurantProvider.clean_restaurant_name
build_swiggy_search_urls = SwiggyRestaurantProvider.build_swiggy_search_urls
