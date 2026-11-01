import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from contextlib import asynccontextmanager
from app.mcp_client.client import init_all_clients, close_all_clients

@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    print("EVENT LOOP TYPE:", type(asyncio.get_event_loop()))
    print("POLICY TYPE:", type(asyncio.get_event_loop_policy()))
    await init_all_clients()
    yield
    await close_all_clients()

app = FastAPI(title="CraveAI Agent API", version="0.1.0", lifespan=lifespan)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|\[::1\]|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.chat import router as chat_router
from app.api.auth import router as auth_router

app.include_router(chat_router, prefix="/api")
app.include_router(auth_router, prefix="/api")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "craveai-agent"}

@app.get("/")
async def root():
    return {"message": "Welcome to CraveAI Agent API"}

import os
print("MAIN LOADED IN PID:", os.getpid())
