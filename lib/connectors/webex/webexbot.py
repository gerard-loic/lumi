from __future__ import annotations
import hmac
import hashlib
import httpx
from typing import TYPE_CHECKING
from lib.log.logger import Logger, ERROR, WARNING, OK
if TYPE_CHECKING:
    from lib.connectors.webex.connector import WebexConnector
_WEBHOOK_NAME = "lumi-webhook"

"""
WebexBot — Client HTTP vers l'API Webex
Attention pour l'initialisation : les deux constructeurs doivent être appelés (synch et asynch)
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class WebexBot:

    def __init__(self, bot_token: str, connector:WebexConnector):
        self._token = bot_token
        self._connector = connector
        self._webex_api = connector.getConfValue("webex_api")
        self._headers = {
            "Authorization": f"Bearer {bot_token}",
            "Content-Type": "application/json",
        }
        self.bot_id: str | None = None
        self.bot_display_name: str = ""

    #Initialisation du Bot (asynchrone - complète le constructeur)
    async def init(self):
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{self._webex_api}/people/me", headers=self._headers)
        if r.status_code == 200:
            data = r.json()
            self.bot_id = data.get("id")
            self.bot_display_name = data.get("displayName", "")
            Logger.write(f"[Connector webex] Bot ready — ID={self.bot_id}, Nom={self.bot_display_name}", type=OK)
        else:
            Logger.write(f"[Connector webex] Unable to retrieve bot identity : HTTP {r.status_code}", type=ERROR)

    #Créé ou met à jour le webhook webex pointant vers l'url du service
    async def register_webhook(self, target_url: str, secret: str = "") -> bool:
        payload: dict = {
            "name":      _WEBHOOK_NAME,
            "targetUrl": target_url,
            "resource":  "messages",
            "event":     "created",
        }
        if secret:
            payload["secret"] = secret

        async with httpx.AsyncClient() as client:
            # Chercher un webhook existant avec ce nom
            existing_id = await self._find_webhook(client)

            if existing_id:
                # Mettre à jour
                r = await client.put(
                    f"{self._webex_api}/webhooks/{existing_id}",
                    headers=self._headers,
                    json={"name": _WEBHOOK_NAME, "targetUrl": target_url, "secret": secret},
                )
                if r.status_code == 200:
                    Logger.write(f"[Connector webex] Webhook updated : {target_url}", type=OK)
                    return True
                Logger.write(f"[Connector webex] Unable to update webhook : HTTP {r.status_code} — {r.text}", type=ERROR)
                return False
            else:
                # Créer
                r = await client.post(
                    f"{self._webex_api}/webhooks",
                    headers=self._headers,
                    json=payload,
                )
                if r.status_code in (200, 201):
                    Logger.write(f"[Connector webex] Webhook created : {target_url}", type=OK)
                    return True
                Logger.write(f"[Connector webex] Unable to create webhook : HTTP {r.status_code} — {r.text}", type=ERROR)
                return False

    #Retourne l'ID du webhook existant portant le nom _WEBHOOK_NAME, ou None.
    async def _find_webhook(self, client: httpx.AsyncClient) -> str | None:
        r = await client.get(f"{self._webex_api}/webhooks?max=100", headers=self._headers)
        if r.status_code != 200:
            Logger.write(f"[Connector webex] Unable to list webhooks : HTTP {r.status_code}", type=WARNING)
            return None
        for wh in r.json().get("items", []):
            if wh.get("name") == _WEBHOOK_NAME:
                return wh.get("id")
        return None

    #Vérification de la signature Webex
    def verify_signature(self, body: bytes, signature: str, secret: str) -> bool:
        expected = hmac.new(secret.encode(), body, hashlib.sha1).hexdigest()
        return hmac.compare_digest(expected, signature)

    #Vérification de l'existence de la personne auprès de Webex, pour confirmer l'authentification
    async def get_person(self, person_id: str) -> dict | None:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{self._webex_api}/people/{person_id}", headers=self._headers)
        if r.status_code == 200:
            return r.json()
        Logger.write(f"[Connector webex] get_person erreur {r.status_code} : {r.text}", type=ERROR)
        return None

    #Récupération d'un message webex à partir de son ID
    async def get_message(self, message_id: str) -> dict | None:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{self._webex_api}/messages/{message_id}", headers=self._headers)
        if r.status_code == 200:
            return r.json()
        Logger.write(f"[Connector webex] get_message erreur {r.status_code} : {r.text}", type=ERROR)
        return None

    #Envoi d'un message à Webex
    async def send_message(self, room_id: str, markdown: str) -> str | None:
        """Envoie un message et retourne son ID, ou None en cas d'erreur."""
        payload = {"roomId": room_id, "markdown": markdown}
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{self._webex_api}/messages", headers=self._headers, json=payload)
        if r.status_code not in (200, 201):
            Logger.write(f"[Connector webex] send_message erreur {r.status_code} : {r.text}", type=ERROR)
            return None
        return r.json().get("id")

    #Modifie un message existant (pour la mise à jour des messages de statut)
    async def update_message(self, message_id: str, room_id: str, markdown: str) -> bool:
        payload = {"roomId": room_id, "markdown": markdown}
        async with httpx.AsyncClient() as client:
            r = await client.put(f"{self._webex_api}/messages/{message_id}", headers=self._headers, json=payload)
        if r.status_code not in (200, 201):
            Logger.write(f"[Connector webex] update_message erreur {r.status_code} : {r.text}", type=ERROR)
            return False
        return True
