import hmac
import hashlib
import httpx
from lib.log.logger import Logger, ERROR, OK

"""
WebexConnector — Client HTTP vers l'API Webex
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class WebexConnector:
    BASE_URL = "https://webexapis.com/v1"

    def __init__(self, bot_token: str):
        self._token = bot_token
        self._headers = {
            "Authorization": f"Bearer {bot_token}",
            "Content-Type": "application/json",
        }
        self.bot_id: str | None = None
        self.bot_display_name: str = ""

    async def init(self):
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{self.BASE_URL}/people/me", headers=self._headers)
        if r.status_code == 200:
            data = r.json()
            self.bot_id = data.get("id")
            self.bot_display_name = data.get("displayName", "")
            Logger.write(f"[WEBEX] Bot prêt — ID={self.bot_id}, Nom={self.bot_display_name}", type=OK)
        else:
            Logger.write(f"[WEBEX] Impossible de récupérer l'identité du bot : HTTP {r.status_code}", type=ERROR)

    def verify_signature(self, body: bytes, signature: str, secret: str) -> bool:
        expected = hmac.new(secret.encode(), body, hashlib.sha1).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def get_message(self, message_id: str) -> dict | None:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{self.BASE_URL}/messages/{message_id}", headers=self._headers)
        if r.status_code == 200:
            return r.json()
        Logger.write(f"[WEBEX] get_message erreur {r.status_code} : {r.text}", type=ERROR)
        return None

    async def send_message(self, room_id: str, markdown: str) -> bool:
        payload = {"roomId": room_id, "markdown": markdown}
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{self.BASE_URL}/messages", headers=self._headers, json=payload)
        if r.status_code not in (200, 201):
            Logger.write(f"[WEBEX] send_message erreur {r.status_code} : {r.text}", type=ERROR)
            return False
        return True
