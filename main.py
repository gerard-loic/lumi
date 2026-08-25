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

from lib.config.config import Config, StaticConfig
from lib.log.logger import Logger
from lib.agent.agent import AgentManager
from lib.services.services import ServiceManager
from lib.session.session import AuthSessionManager
from lib.files.filestore import FileStore
from lib.files.localdata import LocalData
from lib.connectors.connector import ConnectorManager
from lib.cron.cronmanager import CronManager
from lib.agent.profile import ProfileManager
from lib.localization.language import LanguageManager
from lib.pipelines.pipelinemanager import PipelineManager


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
# Initialisation profils
# ----------------------------------------------------------------
ProfileManager.init()

# ----------------------------------------------------------------
# Initialisation localdata
# ----------------------------------------------------------------
LocalData.init()

# ----------------------------------------------------------------
# Initialisation des tâches CRON
# ----------------------------------------------------------------
CronManager.init()

# ----------------------------------------------------------------
# Initialisation des traductions
# ----------------------------------------------------------------
LanguageManager.init()
l = LanguageManager.getLanguage(code="en")
print(l._translations)


# ----------------------------------------------------------------
# Initialisation gestionnaire de services (pour authentification)
# ----------------------------------------------------------------
ServiceManager.init()

# ----------------------------------------------------------------
# Initialisation gestionnaire de pipelines
# ----------------------------------------------------------------
PipelineManager.init()

# ----------------------------------------------------------------
# démarre/arrête le MCP Server avec FastAPI
# ----------------------------------------------------------------
lumi_router = Router()

#Gestion du délestage des sessions et des tâches CRON
async def _session_cleaner():
    while True:
        await asyncio.sleep(60)
        AuthSessionManager.clear()
        await CronManager.execute()


@asynccontextmanager
async def lifespan(app: FastAPI):
    #Pour concentrer toute la gestion des logs en un seul endroit
    Logger._patch_logging_handlers()

    #Suppression des données rémanantes
    FileStore.deleteAll()

    #Gestion de la suppression des sessions et des fichiers temporaires
    cleaner = asyncio.create_task(_session_cleaner())
    async with mcp_manager.run():
        # ----------------------------------------------------------------
        # Initialisation des agents (après démarrage MCP pour que les tools soient chargés)
        # ----------------------------------------------------------------
        AgentManager.init()

        # ----------------------------------------------------------------
        # Initialisation des connecteurs
        # ----------------------------------------------------------------
        await ConnectorManager.init()
        for connector_router in ConnectorManager.get_routers():
            app.include_router(connector_router)

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
