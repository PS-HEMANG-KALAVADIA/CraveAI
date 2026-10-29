import os
import re
import json
import logging
from typing import List, Dict, Any, Tuple
from pydantic import BaseModel

from app.mcp_client.client import get_food_knowledge_client, get_weather_client, get_restaurant_client, get_prompt_client
from app.agent.prompts import SYSTEM_PROMPT
from app.recommendation.engine import RecommendationEngine
from app.services.geocoding import geocode_city, extract_city

import groq

logger = logging.getLogger(__name__)

class ChatResponse(BaseModel):
    response: str
    tools_used: List[str]
    restaurants: List[Dict[str, Any]] = []

class CraveAIAgent:
    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY")
        self.model_name = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
        
        if self.api_key:
            self.client = groq.AsyncGroq(api_key=self.api_key)
        else:
            self.client = None
            logger.warning("GROQ_API_KEY is not set. Agent will fail if invoked.")

        self.food_client = get_food_knowledge_client()
        self.weather_client = get_weather_client()
        self.restaurant_client = get_restaurant_client()
        self.prompt_client = get_prompt_client()
        self.mcp_tools_cache = {}
        self.mcp_prompts_cache = []
        self.ranker = RecommendationEngine()

    def _convert_schema_to_groq(self, schema: dict) -> dict:
        """Ensure schema matches JSON Schema standard for Groq."""
        if not isinstance(schema, dict):
            return schema
        
        new_schema = {}
        for k, v in schema.items():
            if k == "type" and isinstance(v, str):
                new_schema[k] = v.lower()
            elif isinstance(v, dict):
                new_schema[k] = self._convert_schema_to_groq(v)
            elif isinstance(v, list):
                new_schema[k] = [self._convert_schema_to_groq(i) if isinstance(i, dict) else i for i in v]
            else:
                new_schema[k] = v
        return new_schema

    async def initialize_tools(self) -> List[Dict[str, Any]]:
        groq_tools = []
        
        def add_tool(t, server_type):
            self.mcp_tools_cache[t.name] = (server_type, t)
            groq_tools.append({
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": self._convert_schema_to_groq(t.inputSchema)
                }
            })

        import traceback
        try:
            food_tools = await self.food_client.get_tools()
            for t in food_tools:
                add_tool(t, "food")
        except Exception as e:
            logger.error(f"Failed to fetch food tools: {traceback.format_exc()}")

        try:
            weather_tools = await self.weather_client.get_tools()
            for t in weather_tools:
                add_tool(t, "weather")
        except Exception as e:
            logger.error(f"Failed to fetch weather tools: {traceback.format_exc()}")

        try:
            restaurant_tools = await self.restaurant_client.get_tools()
            for t in restaurant_tools:
                add_tool(t, "restaurant")
        except Exception as e:
            logger.error(f"Failed to fetch restaurant tools: {traceback.format_exc()}")
            
        try:
            prompts = await self.prompt_client.get_prompts()
            self.mcp_prompts_cache = [p.name for p in prompts]
            
            groq_tools.append({
                "type": "function",
                "function": {
                    "name": "get_workflow_guidance",
                    "description": f"Retrieve specific step-by-step instructions for a known workflow prompt. Available prompts: {', '.join(self.mcp_prompts_cache)}. Call this if the user's intent matches one of these workflows.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "prompt_name": {"type": "string", "description": "Name of the prompt to retrieve."},
                            "arguments": {"type": "object", "description": "Key-value JSON object of arguments required for the prompt (e.g. location, budget)."}
                        },
                        "required": ["prompt_name"]
                    }
                }
            })
        except Exception as e:
            logger.error(f"Failed to fetch prompts: {traceback.format_exc()}")

        self._cached_groq_tools = groq_tools
        return groq_tools

    async def _get_cached_tools(self) -> List[Dict[str, Any]]:
        if hasattr(self, '_cached_groq_tools'):
            return self._cached_groq_tools
        return await self.initialize_tools()
    async def execute_tool(self, name: str, args: dict) -> Any:
        logger.info(f"Tool selected: {name} with args {args}")
        
        if not self.mcp_tools_cache:
            await self._get_cached_tools()

        if name == "get_workflow_guidance":
            prompt_name = args.get("prompt_name")
            prompt_args = {k: str(v) for k, v in args.get("arguments", {}).items()}
            try:
                content = await self.prompt_client.get_prompt_content(prompt_name, prompt_args)
                logger.info(f"Retrieved guidance for prompt: {prompt_name}")
                return content
            except Exception as e:
                logger.error(f"Failed to fetch prompt {prompt_name}: {e}")
                return {"error": f"Failed to retrieve prompt instructions: {str(e)}"}
                
        if name != "get_workflow_guidance" and name not in self.mcp_tools_cache:
            return {
                "error": "Unknown tool requested",
                "tool": name,
                "available_tools": list(self.mcp_tools_cache.keys()) + ["get_workflow_guidance"]
            }
        
        server_type, _ = self.mcp_tools_cache[name]
        try:
            if server_type == "food":
                result = await self.food_client.call_tool(name, args)
            elif server_type == "weather":
                # Ensure coordinates are provided. If missing or if city is provided, resolve automatically
                if ("latitude" not in args or "longitude" not in args or args.get("latitude") is None or args.get("longitude") is None):
                    city_to_resolve = args.get("city") or args.get("location")
                    if city_to_resolve:
                        geo = await geocode_city(str(city_to_resolve))
                        if geo:
                            args["latitude"] = geo["latitude"]
                            args["longitude"] = geo["longitude"]
                        else:
                            return {"error": f"Could not find coordinates for city '{city_to_resolve}'"}
                    elif hasattr(self, 'current_city_geo') and self.current_city_geo:
                        args["latitude"] = self.current_city_geo["latitude"]
                        args["longitude"] = self.current_city_geo["longitude"]
                    elif hasattr(self, 'current_location') and self.current_location and self.current_location.get("latitude") is not None and self.current_location.get("longitude") is not None:
                        args["latitude"] = self.current_location["latitude"]
                        args["longitude"] = self.current_location["longitude"]
                    else:
                        return {"error": "Missing coordinates for weather. Please ask the user for their city name."}
                result = await self.weather_client.call_tool(name, args)
            elif server_type == "restaurant":
                if name == "search_nearby_restaurants":
                    if "latitude" not in args or "longitude" not in args or args.get("latitude") is None or args.get("longitude") is None:
                        city_to_resolve = args.get("city") or args.get("location")
                        if city_to_resolve:
                            geo = await geocode_city(str(city_to_resolve))
                            if geo:
                                args["latitude"] = geo["latitude"]
                                args["longitude"] = geo["longitude"]
                            else:
                                return {"error": f"Could not find coordinates for city '{city_to_resolve}'"}
                        elif hasattr(self, 'current_city_geo') and self.current_city_geo:
                            args["latitude"] = self.current_city_geo["latitude"]
                            args["longitude"] = self.current_city_geo["longitude"]
                        elif hasattr(self, 'current_location') and self.current_location and self.current_location.get("latitude") is not None and self.current_location.get("longitude") is not None:
                            args["latitude"] = self.current_location["latitude"]
                            args["longitude"] = self.current_location["longitude"]
                        else:
                            return {"error": "Missing coordinates for restaurant search. Please ask the user for their city name."}
                result = await self.restaurant_client.call_tool(name, args)
            else:
                result = await self.restaurant_client.call_tool(name, args)
            
            text_result = result[0].text
            
            try:
                parsed_json = json.loads(text_result)
                if name == "search_nearby_restaurants":
                    if isinstance(parsed_json, dict) and "error" in parsed_json:
                        err_text = str(parsed_json.get("error", "")).lower()
                        if "session expired" in err_text or "re-authenticate" in err_text or "invalid_grant" in err_text:
                            self.last_auth_error = "reauth_required"
                        elif "authentication missing" in err_text or "authenticate via /api/swiggy/login" in err_text:
                            self.last_auth_error = "not_connected"
                        self.last_restaurants = []
                        return parsed_json
                    if isinstance(parsed_json, dict) and "restaurants" in parsed_json:
                        restaurants_list = parsed_json.get("restaurants", [])
                        if restaurants_list:
                            ranked_results = self.ranker.rank(
                                restaurants=restaurants_list,
                                user_message=self.current_user_message,
                                tool_args=args,
                                top_k=5
                            )
                            self.last_restaurants = [r.model_dump() for r in ranked_results]
                            # Clean compact summary for model context to conserve tokens
                            llm_summary = []
                            for r in ranked_results:
                                rest = r.restaurant
                                llm_summary.append({
                                    "name": rest.get("name"),
                                    "rating": rest.get("rating"),
                                    "price": rest.get("price"),
                                    "distance_meters": rest.get("distance_meters"),
                                    "address": rest.get("address"),
                                    "cuisines": rest.get("cuisine", [])[:3],
                                    "url": rest.get("url"),
                                    "url_type": rest.get("url_type"),
                                    "match_category": r.match_category,
                                    "matched_items": r.matched_items,
                                    "match_reason": r.match_reason,
                                    "dish_availability": r.dish_availability
                                })
                            return llm_summary
                        else:
                            self.last_restaurants = []
                        return self.last_restaurants
                    if isinstance(parsed_json, dict) and "message" in parsed_json:
                        self.last_restaurants = []
                        return parsed_json
                    
                return parsed_json
            except json.JSONDecodeError:
                if isinstance(text_result, str) and ("error executing tool" in text_result.lower() or "500 internal server error" in text_result.lower() or "error:" in text_result.lower()):
                    return {"error": text_result}
                return text_result
        except Exception as e:
            logger.error(f"Error executing tool {name}: {e}")
            return {"error": str(e)}

    async def chat_stream_initialized(
        self,
        user_message: str,
        conversation: List[Dict[str, str]] = None,
        location: dict | None = None,
        location_status: str | None = None
    ):
        logger.info("Agent stream request received")
        if not self.client:
            yield json.dumps({"type": "error", "message": "LLM client is not configured (missing API key)."})
            return

        yield json.dumps({"type": "progress", "message": "Initializing agent..."})
        
        tools = await self._get_cached_tools()
        tools_used = []
        self.last_restaurants = []
        self.last_auth_error = None

        self.current_user_message = user_message
        self.current_location = location

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        
        if conversation:
            # Keep the most recent 4 messages (2 conversation turns) to avoid exceeding provider token limits
            recent_conversation = conversation[-4:]
            for msg in recent_conversation:
                content = msg.get("content", "")
                if msg.get("role") == "assistant" and len(content) > 400:
                    content = content[:400] + "..."
                messages.append({"role": msg.get("role", "user"), "content": content})

        # Geocode explicit city from user query if present, or search conversation history only when browser location is unavailable
        city_name = extract_city(user_message)
        has_browser_loc = bool(location and location.get("latitude") is not None and location.get("longitude") is not None)
        if not city_name and not has_browser_loc and conversation:
            for msg in reversed(conversation):
                if msg.get("role") == "user":
                    c = extract_city(msg.get("content", ""))
                    if c:
                        city_name = c
                        break

        # Check if current user message is a follow-up clarification/reply for location
        follow_up_prior_request = None
        if conversation:
            words = user_message.strip().split()
            is_loc_reply = (len(words) <= 6 and (city_name is not None or any(w.lower() in ("ahmedabad", "jaipur", "mumbai", "delhi", "bengaluru", "here", "city") for w in words)))
            if is_loc_reply:
                for msg in reversed(conversation):
                    if msg.get("role") == "user":
                        prev_text = msg.get("content", "").strip()
                        cleaned_prev = re.sub(r'\b(?:in|at|around)\s+[A-Za-z\s]+$', '', prev_text, flags=re.IGNORECASE).strip()
                        follow_up_prior_request = cleaned_prev if cleaned_prev else prev_text
                        break

        # Check if current user message is a follow-up asking for places for previously recommended food
        follow_up_dishes = []
        user_msg_lower = user_message.lower()
        if conversation and any(p in user_msg_lower for p in ["this", "these", "them", "it"]):
            if any(k in user_msg_lower for k in ["place", "places", "restaurant", "restaurants", "where", "find", "order", "get", "suggest"]):
                for msg in reversed(conversation):
                    if msg.get("role") == "assistant":
                        txt = msg.get("content", "")
                        m = re.findall(r'-\s*\*\*([^*:]+)(?:\*\*:|\*\*)|(?:\d+\.\s*\*\*([^*:]+)(?:\*\*:|\*\*))', txt)
                        extracted = [item.strip() for t in m for item in t if item.strip()]
                        if not extracted:
                            extracted = [d.strip() for d in re.findall(r'\*\*([^*:]+)\*\*', txt) if d.strip()]
                        extracted = [d for d in extracted if len(d) > 1 and len(d.split()) <= 4 and d.lower() not in ("recommendation", "recommendations", "weather", "note", "places", "swiggy", "confirmed", "unverified")]
                        if extracted:
                            follow_up_dishes = extracted[:3]
                            break

        city_geo = None
        if city_name:
            city_geo = await geocode_city(city_name)
        self.current_city_geo = city_geo

        context_str = ""
        if follow_up_dishes:
            dishes_str = ", ".join(follow_up_dishes)
            self.current_user_message = f"places for {dishes_str} nearby"
            context_str += (
                f"[SYSTEM: The user is asking for places/restaurants for the dishes recommended in the previous turn: '{dishes_str}'. "
                f"When calling search_nearby_restaurants, you MUST search for '{dishes_str}' (or '{follow_up_dishes[0]}'). "
                f"Do NOT search for generic food or the literal word 'this'.]\n\n"
            )
        loc_context_str = ""
        if follow_up_prior_request and city_geo:
            self.current_user_message = f"{follow_up_prior_request} in {city_geo['name']}"
            corrected_note = ""
            if city_geo.get("corrected_from"):
                corrected_note = f" (Note: city was corrected from '{city_geo['corrected_from']}')"
            loc_context_str = (
                f"[SYSTEM: Follow-up location provided: '{city_geo['name']}' (latitude: {city_geo['latitude']}, longitude: {city_geo['longitude']}){corrected_note}. "
                f"The user's original active food request from previous turn is: '{follow_up_prior_request}'. "
                f"You MUST search specifically for '{follow_up_prior_request}' in '{city_geo['name']}' using the resolved coordinates. "
                f"Retain all original constraints (dish, style, budget). Do NOT perform a generic restaurant search!]\n\n"
            )
        elif city_geo:
            corrected_note = ""
            if city_geo.get("corrected_from"):
                corrected_note = f" (detected likely spelling correction from '{city_geo['corrected_from']}'; please briefly confirm to user: 'Assuming you meant {city_geo['name']}...')"
            loc_context_str = f"[SYSTEM: Resolved coordinates for city '{city_geo['name']}': latitude: {city_geo['latitude']}, longitude: {city_geo['longitude']}{corrected_note}]\n\n"
        elif city_name and not city_geo:
            loc_context_str = f"[SYSTEM: Could not resolve coordinates for city '{city_name}'. Inform the user and ask for clarification. Do NOT invent coordinates or hardcode a city.]\n\n"
        elif location and location.get("latitude") is not None and location.get("longitude") is not None:
            loc_context_str = f"[SYSTEM: User's current location from browser geolocation is latitude: {location['latitude']}, longitude: {location['longitude']}]\n\n"
        else:
            loc_context_str = "[SYSTEM: User location coordinates are unavailable (permission denied or unavailable in browser), and no city was specified. If asking for nearby places/restaurants or weather, ask for a city name. Do NOT ask for latitude/longitude coordinates, and do NOT fabricate coordinates or hardcode a city.]\n\n"
            
        full_context = (context_str + loc_context_str) if context_str else loc_context_str
        messages.append({"role": "user", "content": full_context + user_message})

        max_iterations = 5
        yield json.dumps({"type": "progress", "message": "Understanding your request..."})
        
        for iteration in range(max_iterations):
            hallucinated = False
            # When restaurant search has completed and results are captured, omit tools for the final synthesis call
            active_tools = None if (iteration > 0 and self.last_restaurants) else (tools if tools else None)
            tool_choice = "auto" if active_tools else "none"
            for attempt in range(3):
                try:
                    response = await self.client.chat.completions.create(
                        model=self.model_name,
                        messages=messages,
                        tools=active_tools,
                        tool_choice=tool_choice,
                        temperature=0.2 + (attempt * 0.1),
                        max_tokens=800,
                    )
                    break
                except Exception as e:
                    raw_err = str(e)
                    sanitized_err = re.sub(r'gsk_[A-Za-z0-9_-]+', '[REDACTED_API_KEY]', raw_err)

                    if "tool_use_failed" in raw_err:
                        logger.warning(f"Intercepting tool hallucination: {sanitized_err}")
                        try:
                            # Try to extract the failed generation to mock a response
                            if hasattr(e, 'response') and hasattr(e.response, 'json'):
                                err_data = e.response.json()
                                failed_gen_str = err_data.get('error', {}).get('failed_generation')
                                if failed_gen_str:
                                    failed_gen = json.loads(failed_gen_str)
                                    tool_name = failed_gen.get('name', 'unknown_tool')
                                    tool_args = json.dumps(failed_gen.get('arguments', {}))
                                    import uuid
                                    fake_id = "call_" + str(uuid.uuid4())[:8]
                                    
                                    # Inject assistant tool call
                                    messages.append({
                                        "role": "assistant",
                                        "tool_calls": [{
                                            "id": fake_id,
                                            "type": "function",
                                            "function": {
                                                "name": tool_name,
                                                "arguments": tool_args
                                            }
                                        }]
                                    })
                                    
                                    # Inject tool error response
                                    available_tools = list(self.mcp_tools_cache.keys()) + ["get_workflow_guidance"]
                                    error_msg = json.dumps({
                                        "error": "Unknown tool requested. You MUST ONLY use the provided available_tools.",
                                        "tool": tool_name,
                                        "available_tools": available_tools
                                    })
                                    
                                    messages.append({
                                        "role": "tool",
                                        "tool_call_id": fake_id,
                                        "name": tool_name,
                                        "content": error_msg
                                    })
                                    
                                    hallucinated = True
                                    break
                        except Exception as parse_e:
                            logger.error(f"Failed to parse tool hallucination: {parse_e}")
                            
                        if attempt < 2:
                            continue
                            
                    # Truthful, sanitized user-facing error instead of opaque internal provider error
                    logger.error(f"Groq API error: {sanitized_err}")
                    err_lower = sanitized_err.lower()
                    if "413" in raw_err or "rate_limit_exceeded" in err_lower or "tokens per minute" in err_lower or "itpm" in err_lower or "429" in raw_err:
                        user_error = "The AI provider rate limit was exceeded (tokens per minute limit reached). Please wait a few seconds and try again."
                    elif "401" in raw_err or "invalid_api_key" in err_lower or "unauthorized" in err_lower:
                        user_error = "AI provider authentication failed. Please verify your GROQ_API_KEY configuration."
                    elif "404" in raw_err or "model_not_found" in err_lower:
                        user_error = f"The configured AI model '{self.model_name}' is not available on Groq."
                    elif "timeout" in err_lower or "timed out" in err_lower or "504" in raw_err or "408" in raw_err:
                        user_error = "AI provider request timed out. Please try again."
                    else:
                        msg_match = re.search(r"'message':\s*'([^']+)'", sanitized_err)
                        if msg_match:
                            user_error = f"AI provider error: {msg_match.group(1)}"
                        else:
                            clean_short = sanitized_err.split("\n")[0][:180]
                            user_error = f"AI provider error: {clean_short}"

                    yield json.dumps({"type": "error", "message": user_error})
                    return

            if hallucinated:
                continue


            choice = response.choices[0]
            message = choice.message
            
            logger.info(f"Groq message: {message}")
            
            # Reconstruct the message to append properly (dict form is preferred for Groq python SDK to avoid validation errors, but wait, Groq SDK messages should be dicts)
            assistant_msg = {"role": "assistant"}
            if message.content:
                assistant_msg["content"] = message.content
            
            parsed_tool_calls = []
            if getattr(message, 'tool_calls', None):
                parsed_tool_calls = message.tool_calls
            elif message.content and "<tool_call>" in message.content:
                try:
                    import uuid
                    match = re.search(r'<tool_call>(.*?)</tool_call>', message.content, re.DOTALL)
                    if match:
                        call_str = match.group(1).strip()
                        class FakeFunction:
                            def __init__(self, name, args):
                                self.name = name
                                self.arguments = args if isinstance(args, str) else json.dumps(args)
                        class FakeToolCall:
                            def __init__(self, fn, id):
                                self.id = id
                                self.type = "function"
                                self.function = fn
                                
                        try:
                            call_data = json.loads(call_str)
                            fake_id = "call_" + str(uuid.uuid4())[:8]
                            parsed_tool_calls.append(FakeToolCall(FakeFunction(call_data["name"], call_data.get("arguments", {})), fake_id))
                        except json.JSONDecodeError:
                            lines = call_str.split('\n')
                            func_name = ""
                            args = {}
                            current_key = None
                            for l in lines:
                                l = l.strip()
                                if l.startswith('<function='):
                                    func_name = l.split('=')[1].strip('>')
                                elif l.startswith('<parameter='):
                                    current_key = l.split('=')[1].strip('>')
                                elif l == '</parameter>':
                                    current_key = None
                                elif current_key and not l.startswith('</'):
                                    args[current_key] = l
                            if func_name:
                                fake_id = "call_" + str(uuid.uuid4())[:8]
                                parsed_tool_calls.append(FakeToolCall(FakeFunction(func_name, args), fake_id))
                except Exception as e:
                    logger.error(f"Failed to parse Qwen XML tool call: {e}")

            if parsed_tool_calls:
                assistant_msg["tool_calls"] = []
                for tc in parsed_tool_calls:
                    assistant_msg["tool_calls"].append({
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    })
                    
            messages.append(assistant_msg)

            if parsed_tool_calls:
                for tool_call in parsed_tool_calls:
                    tool_name = tool_call.function.name
                    
                    # Truthful progress messages
                    if tool_name == "search_nearby_restaurants":
                        yield json.dumps({"type": "progress", "message": "Searching nearby restaurants..."})
                    elif tool_name == "get_current_weather":
                        yield json.dumps({"type": "progress", "message": "Checking current weather..."})
                    elif tool_name == "get_weather_forecast":
                        yield json.dumps({"type": "progress", "message": "Checking weather forecast..."})
                    elif tool_name == "search_food":
                        yield json.dumps({"type": "progress", "message": "Searching food knowledge..."})
                    else:
                        yield json.dumps({"type": "progress", "message": f"Calling tool: {tool_name}..."})
                    
                    try:
                        args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
                    except json.JSONDecodeError:
                        args = {}
                        
                    tool_result = await self.execute_tool(tool_name, args)
                    
                    # Record tool status accurately and truthfully
                    if (isinstance(tool_result, dict) and "error" in tool_result) or (isinstance(tool_result, str) and ("error executing tool" in tool_result.lower() or "internal server error" in tool_result.lower())):
                        if tool_name == "get_current_weather":
                            tools_used.append("get_current_weather_failed: Could not retrieve current conditions")
                        else:
                            tools_used.append(f"{tool_name}_failed")
                    elif tool_name == "get_current_weather":
                        if isinstance(tool_result, dict) and ("temperature" in tool_result or "weather_condition" in tool_result):
                            raw_cond = tool_result.get("weather_condition") or tool_result.get("normalized_condition") or "Clear"
                            cond_clean = raw_cond.replace(" sky", "")
                            if cond_clean.lower() == "mainly clear":
                                cond_clean = "Clear"
                            temp = tool_result.get("temperature")
                            if temp is not None:
                                tools_used.append(f"get_current_weather: {cond_clean}, {round(float(temp))}°C")
                            else:
                                tools_used.append(f"get_current_weather: {cond_clean}")
                        else:
                            tools_used.append("get_current_weather")
                    elif tool_name == "search_nearby_restaurants":
                        if isinstance(tool_result, dict) and "message" in tool_result and "no restaurants" in str(tool_result.get("message", "")).lower():
                            tools_used.append("search_nearby_restaurants_no_results")
                        elif not self.last_restaurants:
                            tools_used.append("search_nearby_restaurants_no_results")
                        else:
                            tools_used.append(tool_name)
                    else:
                        tools_used.append(tool_name)
                    
                    # Ensure tool result is a string
                    if not isinstance(tool_result, str):
                        tool_result = json.dumps(tool_result)
                        
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": tool_result
                    })
                
                yield json.dumps({"type": "progress", "message": "Analyzing results..."})
            else:
                final_text = message.content if message.content else "Sorry, I could not generate a response."
                
                # If authentication failed specifically, ensure the user has a clear message with login link
                if getattr(self, "last_auth_error", None):
                    if "swiggy/login" not in final_text.lower():
                        if self.last_auth_error == "reauth_required":
                            final_text += "\n\n⚠️ Your Swiggy session has expired. [Click here to reconnect with Swiggy](http://localhost:8000/api/swiggy/login)."
                        else:
                            final_text += "\n\n⚠️ Swiggy authentication is required to search restaurants. [Click here to connect with Swiggy](http://localhost:8000/api/swiggy/login)."

                result_data = {
                    "type": "result", 
                    "response": final_text, 
                    "tools_used": tools_used,
                    "restaurants": self.last_restaurants
                }
                if getattr(self, "last_auth_error", None):
                    result_data["auth_status"] = self.last_auth_error
                    
                yield json.dumps(result_data)
                return
        
        final_text = "I'm sorry, I needed too many steps to answer that request. Here is what I found so far..."
        if getattr(self, "last_auth_error", None):
            if "swiggy/login" not in final_text.lower():
                if self.last_auth_error == "reauth_required":
                    final_text += "\n\n⚠️ Your Swiggy session has expired. [Click here to reconnect with Swiggy](http://localhost:8000/api/swiggy/login)."
                else:
                    final_text += "\n\n⚠️ Swiggy authentication is required to search restaurants. [Click here to connect with Swiggy](http://localhost:8000/api/swiggy/login)."

        fallback_result = {
            "type": "result", 
            "response": final_text, 
            "tools_used": tools_used,
            "restaurants": self.last_restaurants
        }
        if getattr(self, "last_auth_error", None):
            fallback_result["auth_status"] = self.last_auth_error

        yield json.dumps(fallback_result)

    chat_stream = chat_stream_initialized

    async def chat(self, user_message: str, location: dict | None = None) -> ChatResponse:
        final_result = None
        async for chunk in self.chat_stream(user_message, [], location):
            data = json.loads(chunk)
            if data.get("type") == "result":
                final_result = ChatResponse(
                    response=data["response"],
                    tools_used=data["tools_used"],
                    restaurants=data.get("restaurants", [])
                )
        if final_result:
            return final_result
        return ChatResponse(response="Error: No response generated.", tools_used=[])

    async def close(self):
        await self.food_client.close()
        await self.weather_client.close()
        await self.restaurant_client.close()
        await self.prompt_client.close()
