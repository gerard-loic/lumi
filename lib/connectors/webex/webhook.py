import asyncio
import json
from datetime import datetime, timezone

from lib.connectors.webex.webexbot import WebexBot
from lib.session.session import AuthSessionManager
from lib.mcp.services import ServiceManager
from lib.config.config import Config
from lib.http.auth import Auth
from lib.log.logger import Logger, ERROR, WARNING, OK

"""
WebexWebhookHandler — Traitement des événements webhook Webex
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""


class WebexWebhookHandler:

    def __init__(self, agent, connector: WebexBot):
        self._agent = agent
        self._connector = connector
        self._pending_confirmations: dict[str, asyncio.Queue] = {}

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

        session_id = f"webex_{person_id}"

        # Intercepter les réponses à une confirmation en attente,
        # avant le filtre de mention pour que l'utilisateur n'ait pas à @mentionner le bot
        if session_id in self._pending_confirmations:
            msg_data = await self._connector.get_message(message_id)
            text = (msg_data.get("text", "") if msg_data else "").strip()
            if text:
                await self._pending_confirmations[session_id].put(text)
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
        if not AuthSessionManager.get(session_id):
            person_data = await self._connector.get_person(person_id)
            email = (person_data.get("emails") or [None])[0] if person_data else None
            if not email:
                Logger.write(f"[WEBEX] Impossible de récupérer l'email de {person_id}", type=ERROR)
                await self._connector.send_message(room_id, "❌ Impossible de récupérer votre identité Webex.")
                return

            auth_service_name = Config.get(key="authentication.service")
            auth_service = ServiceManager.get(name=auth_service_name)
            auth_data = auth_service.webexAuthenticate(username=email)
            if not auth_data:
                Logger.write(f"[WEBEX] Authentification échouée pour {email}", type=ERROR)
                await self._connector.send_message(room_id, f"❌ Votre compte **{email}** n'est pas autorisé à utiliser ce service.")
                return

            future_ts = datetime.now(tz=timezone.utc).timestamp() + Config.get("authentication.session_duration")
            AuthSessionManager.add(
                session_id=session_id,
                expires_at=future_ts,
                authentication={"session_id": session_id, "services": {auth_service_name: auth_data}},
                auth_fingerprint=f"webex_{person_id}",
            )

        Auth._local.sessionId = session_id

        Logger.write(f"[WEBEX] Message de {person_id} ({room_type}) : {text[:80]}", type=OK)

        placeholder_id = await self._connector.send_message(room_id, "⏳ *En cours de rédaction...*")

        tokens: list[str] = []
        extras: list[str] = []
        cancelled = False

        try:
            async for raw in self._agent.chatStream(text, {}, session_id, exclude_restricted=True):
                try:
                    ev = json.loads(raw)
                except Exception:
                    continue

                ev_type = ev.get("type")

                if ev_type == "token":
                    tokens.append(ev.get("content", ""))

                elif ev_type == "confirmation":
                    question = ev.get("question", "Confirmation requise")
                    options  = ev.get("options", [])

                    options_md = "\n".join(f"**{i + 1}.** {opt}" for i, opt in enumerate(options))
                    confirmation_msg = f"❓ **{question}**\n\n{options_md}\n\n*Répondez avec le numéro de votre choix.*"
                    await _reply(self._connector, room_id, placeholder_id, confirmation_msg)
                    placeholder_id = None

                    reply_queue: asyncio.Queue = asyncio.Queue(maxsize=1)
                    self._pending_confirmations[session_id] = reply_queue
                    option_idx = -1
                    try:
                        user_reply = await asyncio.wait_for(reply_queue.get(), timeout=120)
                        option_idx = _parse_option(user_reply, options)
                        if option_idx is None:
                            await self._connector.send_message(room_id, "⚠️ Réponse non reconnue. Opération annulée.")
                            option_idx = -1
                    except asyncio.TimeoutError:
                        await self._connector.send_message(room_id, "⏱️ Délai de confirmation dépassé. Opération annulée.")
                    finally:
                        self._pending_confirmations.pop(session_id, None)

                    # Résolution différée : wait_confirmation() n'a pas encore créé sa queue
                    # car le générateur est suspendu au yield — on attend qu'elle apparaisse
                    asyncio.create_task(_delayed_resolve(session_id, option_idx))

                    if option_idx != -1:
                        placeholder_id = await self._connector.send_message(room_id, "⏳ *En cours de rédaction...*")

                elif ev_type == "confirmation_refused":
                    cancelled = True

                elif ev_type == "tool_call":
                    if ev.get("status") == "PENDING" and placeholder_id:
                        tool_label = ev.get("message") or ev.get("tools", "")
                        await self._connector.update_message(placeholder_id, room_id, f"⏳ *{tool_label}...*")

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

        except Exception as e:
            Logger.write(f"[WEBEX] Erreur pendant le traitement de la requête : {e}", type=ERROR)
            await _reply(self._connector, room_id, placeholder_id, "❌ Une erreur est survenue lors du traitement de votre demande.")
            return

        response = "".join(tokens).strip()
        if extras:
            response = response + "\n\n" + "\n".join(extras)

        if response:
            await _reply(self._connector, room_id, placeholder_id, response)
            Logger.write(f"[WEBEX] Réponse envoyée dans {room_id} ({len(response)} car.)", type=OK)
        elif not cancelled:
            Logger.write(f"[WEBEX] Réponse vide pour session {session_id}", type=WARNING)
            await _reply(self._connector, room_id, placeholder_id, "❌ Aucune réponse n'a pu être générée.")


def _parse_option(reply: str, options: list[str]) -> int | None:
    """Retourne l'index de l'option choisie, ou None si non reconnue."""
    reply = reply.strip()
    try:
        idx = int(reply) - 1
        if 0 <= idx < len(options):
            return idx
    except ValueError:
        pass
    reply_lower = reply.lower()
    for i, opt in enumerate(options):
        if reply_lower in opt.lower() or opt.lower() in reply_lower:
            return i
    return None


async def _delayed_resolve(session_id: str, option_idx: int) -> None:
    """Attend que wait_confirmation() ait enregistré sa queue avant de résoudre."""
    for _ in range(50):
        if AuthSessionManager._confirmation_queues.get(session_id):
            break
        await asyncio.sleep(0.1)
    AuthSessionManager.resolve_confirmation(session_id, option_idx)


async def _reply(connector: WebexBot, room_id: str, placeholder_id: str | None, text: str) -> None:
    if placeholder_id:
        await connector.update_message(placeholder_id, room_id, text)
    else:
        await connector.send_message(room_id, text)
