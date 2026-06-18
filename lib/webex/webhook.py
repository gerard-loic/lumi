import asyncio
import json
from datetime import datetime, timezone

from lib.webex.connector import WebexConnector
from lib.session.session import AuthSessionManager
from lib.log.logger import Logger, ERROR, WARNING, OK

"""
WebexWebhookHandler — Traitement des événements webhook Webex
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""

_WEBEX_SESSION_TTL = 60 * 60 * 24 * 365  # Sessions Webex valides 1 an


class WebexWebhookHandler:

    def __init__(self, agent, connector: WebexConnector):
        self._agent = agent
        self._connector = connector

    async def handle(self, event: dict):
        data = event.get("data", {})
        room_id          = data.get("roomId")
        person_id        = data.get("personId")
        message_id       = data.get("id")
        room_type        = data.get("roomType", "group")
        mentioned_people = data.get("mentionedPeople", [])

        if not room_id or not person_id or not message_id:
            return

        # Ignorer les messages envoyés par le bot lui-même
        if person_id == self._connector.bot_id:
            return

        # En espace de groupe, ignorer si le bot n'est pas mentionné
        if room_type != "direct" and self._connector.bot_id not in mentioned_people:
            return

        # Récupérer le texte complet du message via l'API
        msg_data = await self._connector.get_message(message_id)
        if not msg_data:
            return

        text = msg_data.get("text", "").strip()
        if not text:
            return

        # En espace de groupe, le nom du bot précède le message dans le champ text
        if room_type != "direct" and self._connector.bot_display_name:
            prefix = self._connector.bot_display_name
            if text.startswith(prefix):
                text = text[len(prefix):].strip()

        # Obtenir ou créer la session Lumi pour cet utilisateur Webex
        session_id = f"webex_{person_id}"
        if not AuthSessionManager.get(session_id):
            future_ts = datetime.now(tz=timezone.utc).timestamp() + _WEBEX_SESSION_TTL
            AuthSessionManager.add(
                session_id=session_id,
                expires_at=future_ts,
                authentication={},
                auth_fingerprint=f"webex_{person_id}",
            )

        Logger.write(f"[WEBEX] Message de {person_id} ({room_type}) : {text[:80]}", type=OK)

        tokens: list[str] = []
        extras: list[str] = []

        async for raw in self._agent.chatStream(text, {}, session_id):
            try:
                ev = json.loads(raw)
            except Exception:
                continue

            ev_type = ev.get("type")

            if ev_type == "token":
                tokens.append(ev.get("content", ""))

            elif ev_type == "confirmation":
                # Refus automatique — résolu dès que la queue est créée par l'agent
                asyncio.create_task(_auto_refuse(session_id))

            elif ev_type == "file":
                url  = ev.get("url", "")
                name = ev.get("name", "Fichier")
                if url:
                    extras.append(f"📎 **{name}** : {url}")

            elif ev_type == "url":
                url  = ev.get("url", "")
                name = ev.get("name", "Lien")
                if url:
                    extras.append(f"🔗 **{name}** : {url}")

        response = "".join(tokens).strip()
        if extras:
            response = response + "\n\n" + "\n".join(extras)

        if response:
            await self._connector.send_message(room_id, response)
            Logger.write(f"[WEBEX] Réponse envoyée dans {room_id} ({len(response)} car.)", type=OK)
        else:
            Logger.write(f"[WEBEX] Réponse vide pour session {session_id}", type=WARNING)


async def _auto_refuse(session_id: str):
    """Résout automatiquement une demande de confirmation par un refus."""
    AuthSessionManager.resolve_confirmation(session_id, -1)
