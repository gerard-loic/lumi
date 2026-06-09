"""
Lumi chatbot service
----------------------------------------------------------------
Routes :
  POST /chat        : réponse streamée SSE (usage production)
  GET  /tools       : liste les outils MCP disponibles (debug)
  GET  /health      : healthcheck
  GET  /files/{key}/{filename} : télécharge un fichier mis à disposition par l'agent
  POST /auth        : authentification au service


Lancer le service :
  python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from lib.mcp.client import mcp_manager
from lib.http.router import Router

import sys
sys.path.append('lib/')
from lib.config.config import Config, StaticConfig
from lib.log.logger import Logger, WARNING
from lib.agent.agent import Agent
from lib.mcp.services import ServiceManager

# ----------------------------------------------------------------
# Initialisation configuration
# ----------------------------------------------------------------
Config.init()

# ----------------------------------------------------------------
# Initialisation logger
# ----------------------------------------------------------------
Logger.init(configuration=Config.get(key="logger"))

print("###############################################################################")
print('# LUMI - IA agent with MCP toolkit')
print(f"# Version {StaticConfig.version()} ({StaticConfig.versionName()})")
print("###############################################################################")

# ----------------------------------------------------------------
# Initialisation gestionnaire de services (pour authentification)
# ----------------------------------------------------------------
ServiceManager.init()

# ----------------------------------------------------------------
# démarre/arrête le MCP Server avec FastAPI
# ----------------------------------------------------------------
lumi_router = Router()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Logger._patch_logging_handlers()
    async with mcp_manager.run():
        lumi_router.agent = Agent(connector=Config.get(key="LLM_CONNECTOR"))
        yield


# ----------------------------------------------------------------
# App
# ----------------------------------------------------------------

app = FastAPI(
    title=Config.get(key="SERVICE_NAME"),
    description=Config.get(key="SERVICE_DESCRIPTION"),
    version=f"{StaticConfig.version()} ({StaticConfig.versionName()})",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.get(key="CORS_IPS"),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(lumi_router.router)
