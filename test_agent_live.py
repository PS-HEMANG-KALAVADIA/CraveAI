import asyncio
import sys
import os
import json

sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))
from app.agent.agent import CraveAIAgent

async def run_scenario(agent, name, message):
    print(f"\n{'='*50}")
    print(f"=== Scenario: {name} ===")
    print(f"User: {message}")
    print("-" * 50)
    
    # Mock location for the test (Ahmedabad)
    test_location = {"latitude": 23.0225, "longitude": 72.5714}

    try:
        # We must pass the explicit location now, otherwise the agent will ask for it!
        response = await agent.chat(message, location=test_location)
        print(f"Agent: {response.response}\n")
        print(f"Tools Used: {', '.join(response.tools_used) if response.tools_used else 'None'}")
    except Exception as e:
        print(f"Error: {e}")
    print(f"{'='*50}\n")

async def main():
    # Make sure we have the API key
    if not os.getenv("GEMINI_API_KEY"):
        print("GEMINI_API_KEY environment variable is not set. Cannot run live agent tests.")
        return

    agent = CraveAIAgent()

    scenarios = [
        ("Scenario 1", "I want Gujarati food near me."),
        ("Scenario 2", "It's raining. Find me something spicy nearby."),
        ("Scenario 3", "I want to experience Jaipur food near me."),
        ("Scenario 4", "I have ₹300. Find something good nearby."),
        ("Scenario 5", "What is dal baati churma?")
    ]

    for name, msg in scenarios:
        await run_scenario(agent, name, msg)

if __name__ == "__main__":
    # Ensure logs are visible if needed, uncomment to see tool execution logs
    # import logging
    # logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
