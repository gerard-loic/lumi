from pydantic import BaseModel
from typing import Optional

class ChatRequest(BaseModel):
    message: str
    bearer:str

class ToolInfo(BaseModel):
    name: str
    description: str
