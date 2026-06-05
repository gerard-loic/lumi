from pydantic import BaseModel
from typing import Optional

"""
ChatRequest — Format requête HTTP chat
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

"""
ToolInfo — Format requête HTTP tools
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class ToolInfo(BaseModel):
    name: str
    description: str

"""
AuthRequest — Format requête HTTP auth
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class AuthRequest(BaseModel):
    authorization: dict