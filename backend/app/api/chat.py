from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.agent.agent import CraveAIAgent

router = APIRouter()

class Location(BaseModel):
    latitude: float
    longitude: float

from fastapi.responses import StreamingResponse

agent = CraveAIAgent()

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    conversation: list[Message] = []
    location: Optional[Location] = None
    location_status: Optional[str] = None

@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        conversation = [{"role": msg.role, "content": msg.content} for msg in request.conversation]
        location_data = request.location.model_dump() if request.location else None
        
        async def event_generator():
            try:
                kwargs = {
                    "user_message": request.message,
                    "conversation": conversation,
                    "location": location_data
                }
                if request.location_status:
                    kwargs["location_status"] = request.location_status

                async for chunk in agent.chat_stream(**kwargs):
                    yield f"data: {chunk}\n\n"
            except Exception as e:
                import json
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")
