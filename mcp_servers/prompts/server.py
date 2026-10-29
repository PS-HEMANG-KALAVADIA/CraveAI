import asyncio
from typing import List
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Prompt, PromptArgument, GetPromptResult, PromptMessage, TextContent

app = Server("prompts")

PROMPTS = {
    "rainy_day": {
        "description": "Workflow for rainy day food recommendations.",
        "arguments": [
            PromptArgument(name="location", description="User's current city or coordinates", required=False),
            PromptArgument(name="dietary_preference", description="E.g., vegetarian, vegan", required=False)
        ]
    },
    "city_experience": {
        "description": "Workflow to experience a specific city's food culture.",
        "arguments": [
            PromptArgument(name="city_name", description="The city to explore (e.g. Jaipur)", required=True),
            PromptArgument(name="location", description="User's actual physical location for finding nearby places", required=False)
        ]
    },
    "budget_food": {
        "description": "Workflow for finding cheap or budget-constrained food.",
        "arguments": [
            PromptArgument(name="budget", description="The budget amount or constraint (e.g. 300, cheap)", required=True)
        ]
    }
}

@app.list_prompts()
async def list_prompts() -> List[Prompt]:
    return [
        Prompt(
            name=name,
            description=info["description"],
            arguments=info["arguments"]
        ) for name, info in PROMPTS.items()
    ]

@app.get_prompt()
async def get_prompt(name: str, arguments: dict | None) -> GetPromptResult:
    args = arguments or {}
    
    if name == "rainy_day":
        loc = args.get("location", "their current location")
        diet = args.get("dietary_preference", "none")
        
        instructions = f"""
        You are executing the 'Rainy Day' workflow.
        Context: The user is at {loc} and has dietary preference: {diet}.
        
        Step 1: Check the weather at {loc} using the Weather MCP to confirm conditions or get temperature context.
        Step 2: Use the Food Knowledge MCP to find comforting, warm, or spicy foods that match rainy weather and the dietary preference.
        Step 3: If you have their coordinates, use the Restaurant MCP to find those exact foods nearby. If not, ask for their location.
        Step 4: Use the recommendation engine score breakdown to suggest the absolute best match. Focus your tone on warmth and comfort.
        """
        return GetPromptResult(
            messages=[
                PromptMessage(role="user", content=TextContent(type="text", text=instructions.strip()))
            ]
        )
        
    elif name == "city_experience":
        city = args.get("city_name", "")
        loc = args.get("location", "their current location")
        
        instructions = f"""
        You are executing the 'City Experience' workflow for {city}.
        Context: The user is currently at {loc}.
        
        Step 1: Use the Food Knowledge MCP to find authentic, iconic dishes and cuisines native to {city}.
        Step 2: If you have their actual location coordinates, use the Restaurant MCP to search for those specific {city} dishes near them.
        Step 3: Synthesize the results, acting as a culinary guide bridging {city}'s food culture with what's actually available nearby.
        """
        return GetPromptResult(
            messages=[
                PromptMessage(role="user", content=TextContent(type="text", text=instructions.strip()))
            ]
        )

    elif name == "budget_food":
        budget = args.get("budget", "")
        
        instructions = f"""
        You are executing the 'Budget Food' workflow.
        Context: The user has a strict budget of {budget}.
        
        Step 1: Acknowledge the budget.
        Step 2: When invoking the Restaurant MCP, explicitly pass price_tier="1" (or "$") to ensure cheap eats are retrieved.
        Step 3: The Recommendation Engine will automatically boost budget fits if you pass the price_tier. 
        Step 4: Ensure your final response explicitly confirms that these places fit within their budget constraint.
        """
        return GetPromptResult(
            messages=[
                PromptMessage(role="user", content=TextContent(type="text", text=instructions.strip()))
            ]
        )
        
    raise ValueError(f"Unknown prompt: {name}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
