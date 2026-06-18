"""
Lumi chatbot service
----------------------------------------------------------------
Routes :
  WS   /ws          : conversation streamée WebSocket (usage production)
  GET  /tools       : liste les outils MCP disponibles (debug)
  GET  /health      : healthcheck
  GET  /files/{key}/{filename} : télécharge un fichier mis à disposition par l'agent
  POST /auth        : authentification au service

Lancer le service :
  python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload
"""

import asyncio
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
from lib.session.session import AuthSessionManager
from lib.files.filestore import FileStore
from lib.files.localdata import LocalData
from lib.agent.filters.llmfilter import LLMFilterManager

# ----------------------------------------------------------------
# Initialisation configuration
# ----------------------------------------------------------------
Config.init()

# ----------------------------------------------------------------
# Initialisation logger
# ----------------------------------------------------------------
Logger.init(configuration=Config.get(key="logger"))

# ----------------------------------------------------------------
# Initialisation localdata
# ----------------------------------------------------------------
LocalData.init()

# ----------------------------------------------------------------
# Initialisation filtres
# ----------------------------------------------------------------
LLMFilterManager.init()

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


async def _session_cleaner():
    while True:
        await asyncio.sleep(60)
        AuthSessionManager.clear()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Logger._patch_logging_handlers()

    #Suppression des données rémanantes
    FileStore.deleteAll()

    #Gestion de la suppression des sessions et des fichiers temporaires
    cleaner = asyncio.create_task(_session_cleaner())
    async with mcp_manager.run():
        lumi_router.agent = Agent(connector=Config.get(key="llm.connector"))

        if Config.get(key="webex.enabled", default=False):
            from lib.webex.connector import WebexConnector
            from lib.webex.webhook import WebexWebhookHandler
            webex_connector = WebexConnector(bot_token=Config.get(key="webex.bot_token"))
            await webex_connector.init()
            lumi_router._webex_connector = webex_connector
            lumi_router._webex_handler = WebexWebhookHandler(agent=lumi_router.agent, connector=webex_connector)
            webhook_url = Config.get(key="app.url").rstrip("/") + "/webex/webhook"
            webhook_secret = Config.get(key="webex.webhook_secret", default="")
            await webex_connector.register_webhook(target_url=webhook_url, secret=webhook_secret)

        yield
    cleaner.cancel()


# ----------------------------------------------------------------
# App
# ----------------------------------------------------------------

app = FastAPI(
    title=Config.get(key="app.name"),
    description=Config.get(key="app.description"),
    version=f"{StaticConfig.version()} ({StaticConfig.versionName()})",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.get(key="app.allowed_cors_ips"),
    allow_methods=Config.get(key="app.allowed_cors_methods"),
    allow_headers=Config.get(key="app.allowed_cors_headers"),
)

app.include_router(lumi_router.router)
