from pydantic import BaseModel
from typing import Optional

class ChatRequest(BaseModel):
    message: str
    bearer: str
    session_id: Optional[str] = None

class ToolInfo(BaseModel):
    name: str
    description: str
