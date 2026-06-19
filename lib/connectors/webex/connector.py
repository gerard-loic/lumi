import json
from fastapi import APIRouter, BackgroundTasks, Header, Request, HTTPException
from lib.connectors.connector import Connector
from lib.connectors.webex.webexbot import WebexBot
from lib.connectors.webex.webhook import WebexWebhookHandler
from lib.config.config import Config
from lib.log.logger import Logger, ERROR, WARNING
from lib.agent.agent import Agent

class WebexConnector(Connector):
    def __init__(self, agent:Agent, config:dict={}):
        super().__init__('webex', agent, config)

    async def start(self):
        webhook_secret = Config.get(key="webex.webhook_secret", default="")
        if not webhook_secret:
            raise Exception("[WebexConnector] webex.webhook_secret est obligatoire — configurez un secret pour sécuriser le webhook")

        self._bot = WebexBot(bot_token=self.getConfValue("bot_token"), connector=self)
        await self._bot.init()

        self._handler = WebexWebhookHandler(agent=self._agent, connector=self._bot)
        webhook_url = Config.get(key="app.url").rstrip("/") + "/webex/webhook"
        await self._bot.register_webhook(target_url=webhook_url, secret=webhook_secret)

        await super().start()

    async def stop(self):
        await super().stop()

    def get_router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route("/webex/webhook", self._webhook_endpoint, methods=["POST"])
        return router

    async def _webhook_endpoint(self, request: Request, background_tasks: BackgroundTasks, x_spark_signature: str | None = Header(default=None)):
        Logger.write(f"[HTTP] [WEBEX] Webhook reçu depuis {request.client.host}", type=WARNING)

        body = await request.body()

        if not x_spark_signature:
            Logger.write("[HTTP] [401] webex_webhook — Header X-Spark-Signature absent", type=ERROR)
            raise HTTPException(status_code=401, detail="Missing webhook signature")

        webhook_secret = Config.get(key="webex.webhook_secret")
        if not self._bot.verify_signature(body, x_spark_signature, webhook_secret):
            Logger.write("[HTTP] [401] webex_webhook — Signature invalide", type=ERROR)
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

        try:
            event = json.loads(body)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        background_tasks.add_task(self._handler.handle, event)
        return {"status": "ok"}