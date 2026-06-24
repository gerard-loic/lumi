import json
from fastapi import APIRouter, BackgroundTasks, Header, Request, HTTPException
from lib.connectors.connector import Connector
from lib.connectors.webex.webexbot import WebexBot
from lib.connectors.webex.webhook import WebexWebhookHandler
from lib.config.config import Config
from lib.log.logger import Logger, ERROR, WARNING
from lib.agent.agent import Agent

"""
WebexConnector — connecteur agent pour Webex
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class WebexConnector(Connector):
    def __init__(self, agent:Agent, config:dict={}):
        super().__init__('webex', agent, config)

    async def start(self):
        webhook_secret = self._config.get("webhook_secret", "")
        if not webhook_secret:
            self.raiseException(message="webex.webhook_secret is required")

        #Initialisation du bot
        self._bot = WebexBot(bot_token=self.getConfValue("bot_token"), connector=self)
        await self._bot.init()

        #Configuraion du gestionnaire webhook pour webex
        self._handler = WebexWebhookHandler(agent=self._agent, connector=self._bot)
        webhook_url = Config.get(key="app.url").rstrip("/") + "/webex/webhook"
        await self._bot.register_webhook(target_url=webhook_url, secret=webhook_secret)

        await super().start()

    async def stop(self):
        await super().stop()

    #Retourne les méthodes à implémenter dans le router
    def get_router(self) -> APIRouter:
        router = APIRouter()
        #ajout de la route pour la gestion des webhook webex
        router.add_api_route("/webex/webhook", self._webhook_endpoint, methods=["POST"])
        return router

    #Methode utiliser par la route webex/webhook
    async def _webhook_endpoint(self, request: Request, background_tasks: BackgroundTasks, x_spark_signature: str | None = Header(default=None)):
        self.log(message=f"Webhook received from {request.client.host}")

        body = await request.body()

        #Le message doit contenir la signature attendue de Webex
        if not x_spark_signature:
            self.log(message=f"Header X-Spark-Signature required")
            raise HTTPException(status_code=401, detail="Missing webhook signature")

        #On vérifie la signature pour authentifier l'appel
        webhook_secret = self.getConfValue("webhook_secret")
        if not self._bot.verify_signature(body, x_spark_signature, webhook_secret):
            self.log(message=f"Invalid webhook signature")
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
        try:
            event = json.loads(body)
        except Exception:
            self.log(message=f"Invalid JSON payload")
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        background_tasks.add_task(self._handler.handle, event)
        return {"status": "ok"}