"""
Lumi chatbot service
----------------------------------------------------------------
Routes :
  POST /chat        → réponse streamée SSE (usage production)
  GET  /tools       → liste les outils MCP disponibles (debug)
  GET  /health      → healthcheck

Lancer le service :
  python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from lib.mcp.models import ChatRequest, ToolInfo
from lib.mcp.client import mcp_manager

import sys
sys.path.append('lib/')
from lib.config.config import Config
from lib.log.log import Log
from lib.agent.agent import Agent
from lib.com.database import DataBase

# ----------------------------------------------------------------
# Initialisation configuration
# ----------------------------------------------------------------
Config.init()

# ----------------------------------------------------------------
# Initialisation logger
# ----------------------------------------------------------------
Log.init()

# ----------------------------------------------------------------
# Initialisation database
# ----------------------------------------------------------------
DataBase.connect()


# ----------------------------------------------------------------
# démarre/arrête le MCP Server avec FastAPI
# ----------------------------------------------------------------
agent: Agent | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent
    async with mcp_manager.run():
        agent = Agent(connector=Config.get(key="LLM_CONNECTOR", type="env"))
        yield


# ----------------------------------------------------------------
# App
# ----------------------------------------------------------------
app = FastAPI(
    title=Config.get(key="SERVICE_NAME", type="env"),
    description=Config.get(key="SERVICE_DESCRIPTION", type="env"),
    version=Config.get(key="SERVICE_VERSION", type="env"),
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.getArray(key="CORS_IPS", type="env"),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------------------------------------------
# Routes
# ----------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "mcp": "connected"}


@app.get("/tools", response_model=list[ToolInfo])
async def list_tools():
    """Retourne la liste des outils MCP disponibles."""
    return [
        ToolInfo(name=t.name, description=t.description)
        for t in mcp_manager.tools
    ]

@app.post("/chat")
async def chat(request: ChatRequest):
    """
    Endpoint principal — retourne une réponse streamée (SSE).
    """
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message is empty")

    if not request.bearer.strip():
        raise HTTPException(status_code=400, detail="Bearer token is empty")

    return StreamingResponse(
        agent.chatStream(request.message, request.bearer, request.session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # important si derrière Nginx
        }
    )


