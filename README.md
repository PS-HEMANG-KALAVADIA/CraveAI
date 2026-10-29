# CraveAI - Context-Aware Food Discovery Agent

CraveAI is an AI-powered food discovery agent that understands user intent and context to provide intelligent, relevant food recommendations. It leverages the Model Context Protocol (MCP) to dynamically fetch context (like weather) and food knowledge.

## Architecture

- **Frontend**: React + TypeScript + Vite + Tailwind CSS
- **Backend/Agent**: Python + FastAPI
- **MCP Servers**: Independent services providing context and knowledge (Weather, Food Knowledge, Restaurant search)
- **AI**: LLM orchestrating MCP tools to fulfill user requests

## Setup Instructions

### 1. Environment Variables
Copy `.env.example` to `.env` in the root directory and fill in your API keys.

### 2. Backend Setup
Requires Python 3.12+
```bash
cd backend
python -m venv venv
# Activate venv
# Windows: venv\Scripts\activate
# Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
```

### 3. Frontend Setup
Requires Node.js 20+
```bash
cd frontend
npm install
```

## MCP Servers

### 1. Food Knowledge MCP Server
This server acts as a static knowledge base providing detailed culinary information to the agent.
- **Location:** `mcp_servers/food_knowledge`
- **Features:**
  - **Tools:** `search_food`, `get_dish_information`, `get_cuisine_information`, `get_city_food`, `get_food_for_weather`, `get_food_for_mood`
  - **Resources:** `food://cities/{city_id}`, `food://cuisines/{cuisine_id}`, `food://dishes/{dish_id}`

### 2. Weather MCP Server
This server provides live weather context (current weather and forecast) using the Open-Meteo API.
- **Location:** `mcp_servers/weather`
- **Provider:** Open-Meteo (No API Key Required)
- **Features:**
  - **Tools:** `get_current_weather`, `get_weather_forecast`
  - **Normalization:** Maps complex WMO codes to basic contexts (`rainy`, `stormy`, `hot`, `cold`, `cloudy`, `clear`, `pleasant`)

### 3. Restaurant Provider MCP Server
This server provides real-world, location-based restaurant recommendations using Yelp Fusion (or a fallback Mock provider).
- **Location:** `mcp_servers/restaurants`
- **Providers Supported:**
  - `YelpRestaurantProvider`: Uses the official Yelp Fusion API. Requires `YELP_API_KEY` in environment.
  - `MockRestaurantProvider`: Deterministic fallback testing provider.
- **Features:**
  - **Tools:** `search_nearby_restaurants`
  - **Capabilities:** Distance sorting, pricing, ratings, location matching.

### 4. Prompt MCP Server (Phase 7)
Demonstrates the official MCP Prompt protocol. Instead of hardcoding all workflows in the system prompt, this server provides dynamic, parameterizable workflow instructions (e.g., `rainy_day`, `city_experience`).
- **Location:** `mcp_servers/prompts`
- **Features:** 
  - `list_prompts()`: Allows the agent to discover available workflows.
  - `get_prompt()`: Returns precise step-by-step guidance for the agent to follow.
- **Agent Integration:** The LLM dynamically invokes the `get_workflow_guidance` tool when it detects an intent matching a known prompt. This maintains architectural purity by separating data retrieval (Tools) from behavioral guidance (Prompts).

**Running tests for MCP Servers:**
```bash
# Prompts
cd mcp_servers/prompts
python -m venv venv
# Activate venv
pip install -r requirements.txt
pytest tests/
```
# Food Knowledge
cd mcp_servers/food_knowledge
python -m venv venv
# Activate venv
pip install -r requirements.txt
pytest tests/

# Weather
cd ../weather
python -m venv venv
# Activate venv
pip install -r requirements.txt
pytest tests/

# Restaurants
cd ../restaurants
python -m venv venv
# Activate venv
pip install -r requirements.txt
pytest tests/
```

### 5. Backend Agent Layer (FastAPI)
The central orchestrator built with FastAPI and `google-genai`.
- **Location:** `backend/`
- **Features:**
  - Connects to multiple MCP servers using `mcp` SDK.
  - Generates tool declarations for the LLM.
  - Multi-step tool invocation loop handling (e.g. Weather -> Food Knowledge).
  - Exposes `POST /api/chat` for the frontend.

**Running the Backend:**
```bash
cd backend
python -m venv venv
# Activate venv
pip install -r requirements.txt
# Ensure GEMINI_API_KEY is set in environment or .env
uvicorn app.main:app --reload --port 8000
```

### 6. Recommendation Engine (Phase 6)
An intelligent, deterministic baseline ranking system acting as an intermediary between the Restaurant MCP and the Agent.
- **Location**: `backend/app/recommendation/`
- **Filtering & Scoring**: Uses a `DeterministicScorer` to evaluate:
  - Food & Cuisine keyword matching
  - Ratings & Distance (normalized)
  - Price Tier / Budget fitting
- **Intent-Aware Weights**: Dynamically adjusts scoring weights using heuristics based on the user's message (e.g., prioritizing distance if the user says "closest").
- **Explainability**: Returns the top 5 candidates with a detailed `score_breakdown`, allowing the LLM to craft natural, explainable recommendations without exposing raw math or chain-of-thought.

### 7. Frontend Chat UI (React/Vite)
A clean, functional conversational interface for users to chat with CraveAI.
- **Location:** `frontend/`
- **Features:**
  - Displays user and agent messages.
  - Shows which tools were dynamically selected by the agent.
  - Handles loading states and errors.

**Running the Frontend:**
```bash
cd frontend
npm install
npm run dev
```
