import httpx
import json
import asyncio
import sys
import os

# Force unbuffered output to local test directory
output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_live_output.txt")
file_out = open(output_file, "w", encoding="utf-8")

def log(msg=""):
    try:
        print(msg)
    except Exception:
        print(msg.encode("ascii", errors="replace").decode("ascii"))
    file_out.write(str(msg) + "\n")
    file_out.flush()

async def run_queries():
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            # Query 1: Pani Puri in Ahmedabad
            log("==================================================")
            log("TEST 1: 'suggest me nearby places for pani puri in Ahmedabad'")
            log("==================================================")
            payload1 = {
                "message": "suggest me nearby places for pani puri in Ahmedabad",
                "conversation": [],
                "location": None
            }
            async with client.stream("POST", "http://127.0.0.1:8000/api/chat", json=payload1) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if data_str:
                            event = json.loads(data_str)
                            if event.get("type") == "progress":
                                log(f"[Progress] {event.get('message')}")
                            elif event.get("type") == "result":
                                log("\n[AI Response]:")
                                log(event.get("response"))
                                log(f"\n[Tools Used]: {event.get('tools_used')}")
                                rests = event.get("restaurants", [])
                                log(f"\n[Returned Restaurants ({len(rests)})]:")
                                for idx, r in enumerate(rests, 1):
                                    rest_info = r.get("restaurant", r)
                                    name = rest_info.get("name")
                                    cat = r.get("match_category")
                                    items = r.get("matched_items", [])
                                    reason = r.get("match_reason", "")
                                    log(f"  {idx}. {name} | Category: {cat} | Verified Items: {items} | Reason: {reason}")
                                break
                            elif event.get("type") == "error":
                                log(f"[Error]: {event}")
                                break

            log("\n\n==================================================")
            log("TEST 2: Jaipur-style authentic kachori in 'ahmedabaf' -> follow up 'Ahmedabad'")
            log("==================================================")
            
            # Turn 1: Typo in city
            payload2_turn1 = {
                "message": "suggest me places for jaipur style authentic kachori in ahmedabaf",
                "conversation": [],
                "location": None
            }
            turn1_response = ""
            async with client.stream("POST", "http://127.0.0.1:8000/api/chat", json=payload2_turn1) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if data_str:
                            event = json.loads(data_str)
                            if event.get("type") == "progress":
                                log(f"[Turn 1 Progress] {event.get('message')}")
                            elif event.get("type") == "result":
                                turn1_response = event.get("response", "")
                                log("\n[Turn 1 AI Response]:")
                                log(turn1_response)
                                rests = event.get("restaurants", [])
                                log(f"[Turn 1 Restaurants ({len(rests)})]:")
                                for idx, r in enumerate(rests, 1):
                                    rest_info = r.get("restaurant", r)
                                    name = rest_info.get("name")
                                    cat = r.get("match_category")
                                    items = r.get("matched_items", [])
                                    reason = r.get("match_reason", "")
                                    log(f"  {idx}. {name} | Category: {cat} | Items: {items} | Reason: {reason}")
                                break
                            elif event.get("type") == "error":
                                log(f"[Turn 1 Error]: {event}")
                                break

            # Turn 2: User confirms/clarifies "Ahmedabad"
            log("\n--- Sending Turn 2: 'Ahmedabad' ---")
            payload2_turn2 = {
                "message": "Ahmedabad",
                "conversation": [
                    {"role": "user", "content": "suggest me places for jaipur style authentic kachori in ahmedabaf"},
                    {"role": "assistant", "content": turn1_response if turn1_response else "Which city are you in?"}
                ],
                "location": None
            }
            async with client.stream("POST", "http://127.0.0.1:8000/api/chat", json=payload2_turn2) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if data_str:
                            event = json.loads(data_str)
                            if event.get("type") == "progress":
                                log(f"[Turn 2 Progress] {event.get('message')}")
                            elif event.get("type") == "result":
                                log("\n[Turn 2 AI Response]:")
                                log(event.get("response"))
                                log(f"\n[Turn 2 Tools Used]: {event.get('tools_used')}")
                                rests = event.get("restaurants", [])
                                log(f"\n[Turn 2 Returned Restaurants ({len(rests)})]:")
                                for idx, r in enumerate(rests, 1):
                                    rest_info = r.get("restaurant", r)
                                    name = rest_info.get("name")
                                    cat = r.get("match_category")
                                    items = r.get("matched_items", [])
                                    reason = r.get("match_reason", "")
                                    log(f"  {idx}. {name} | Category: {cat} | Verified Items: {items} | Reason: {reason}")
                                break
                            elif event.get("type") == "error":
                                log(f"[Turn 2 Error]: {event}")
                                break
    finally:
        file_out.close()

if __name__ == "__main__":
    asyncio.run(run_queries())
