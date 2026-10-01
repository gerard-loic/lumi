import os
import re
import mimetypes

import requests

from lib.config.config import Config
from lib.pipelines._abstract import Block
from lib.pipelines.pipelinecontext import PipelineContext
from lib.log.logger import Logger, ERROR, OK

_DEFAULT_WEBEX_API = "https://webexapis.com/v1"

#Bloc Webex : envoie une notification (message Markdown, pièce jointe optionnelle) via un bot Webex.
#
#Paramètres de configuration (clé "config" du bloc) :
#  - profile         (str,  défaut None)  : profil dont on réutilise le bot Webex (profiles.<profile>.connectors.webex :
#                                           bot_token et webex_api). Le connecteur n'a pas besoin d'être activé.
#  - bot_token       (str,  défaut None)  : jeton du bot ; prioritaire sur celui du profil.
#  - webex_api       (str,  défaut profil ou "https://webexapis.com/v1") : URL de base de l'API Webex.
#  - room_id         (str)                : identifiant de l'espace (room) destinataire.
#  - to_person_email (str)                : email du destinataire (message direct 1:1).
#  - to_person_id    (str)                : identifiant Webex du destinataire (message direct 1:1).
#                                           Exactement un destinataire parmi room_id / to_person_email / to_person_id.
#  - message         (str,  défaut "")    : texte Markdown du message ; interpolé via le contexte.
#  - attachment      (str | dict, défaut None) : fichier joint (Webex n'en accepte qu'un par message). Chemin local
#                                           (interpolé), référence de contexte "{var}" vers une structure de fichier
#                                           {"path","filename"} (ou une liste : seul le premier est envoyé), ou dict.
#  - timeout         (int,  défaut 30)    : délai d'attente HTTP en secondes.
#  - output          (str,  défaut "webex") : clé du contexte où stocker {"id","room_id"} du message créé.
class Webex(Block):
    def __init__(self, block_uid:str, config:dict, on_success_block:str=None, on_error_block:str=None):
        super().__init__("Webex", block_uid, config, on_success_block=on_success_block, on_error_block=on_error_block)

    def execute(self, context:PipelineContext):
        profile = context.getConfig(key="profile", default=None)
        profile_conf = Config.get(f"profiles.{profile}.connectors.webex", default=None) if profile else None
        if profile and not isinstance(profile_conf, dict):
            Logger.write(f"[Block Webex] No webex connector configured for profile '{profile}'", type=ERROR)
            return False
        profile_conf = profile_conf or {}

        bot_token = context.getConfig(key="bot_token", default=None) or profile_conf.get("bot_token")
        webex_api = (context.getConfig(key="webex_api", default=None) or profile_conf.get("webex_api") or _DEFAULT_WEBEX_API).rstrip("/")
        message = context.getConfig(key="message", default="")
        timeout = context.getConfig(key="timeout", default=30)
        output = context.getConfig(key="output", default="webex")

        if not bot_token:
            Logger.write(f"[Block Webex] Missing bot_token (set 'bot_token' or a 'profile' with a webex connector)", type=ERROR)
            return False

        #Un seul destinataire parmi les trois modes d'adressage Webex
        targets = {key: context.getConfig(key=key, default=None) for key in ("room_id", "to_person_email", "to_person_id")}
        targets = {key: value for key, value in targets.items() if value}
        if len(targets) != 1:
            Logger.write(f"[Block Webex] Exactly one of room_id / to_person_email / to_person_id is required", type=ERROR)
            return False
        target_key, target_value = next(iter(targets.items()))
        payload = {self._camel(target_key): target_value}
        if message:
            payload["markdown"] = message

        #On part de la config brute : "{var}" doit être résolu en structure de fichier, pas sérialisé en chaine
        attachment = self._resolveAttachment(self._config.get("attachment"), context)
        if attachment is not None and not os.path.isfile(attachment["path"]):
            Logger.write(f"[Block Webex] Attachment {attachment['path']} not found", type=ERROR)
            return False
        if not message and attachment is None:
            Logger.write(f"[Block Webex] Nothing to send : 'message' and 'attachment' are empty", type=ERROR)
            return False

        headers = {"Authorization": f"Bearer {bot_token}"}
        try:
            if attachment is None:
                r = requests.post(f"{webex_api}/messages", headers=headers, json=payload, timeout=timeout)
            else:
                content_type, _ = mimetypes.guess_type(attachment["filename"])
                with open(attachment["path"], "rb") as f:
                    files = {"files": (attachment["filename"], f, content_type or "application/octet-stream")}
                    r = requests.post(f"{webex_api}/messages", headers=headers, data=payload, files=files, timeout=timeout)
        except requests.RequestException as e:
            Logger.write(f"[Block Webex] Request failed : {e}", type=ERROR)
            return False

        if r.status_code not in (200, 201):
            Logger.write(f"[Block Webex] Send failed : HTTP {r.status_code} — {r.text}", type=ERROR)
            return False

        data = r.json()
        context.set(output, {"id": data.get("id"), "room_id": data.get("roomId")})
        Logger.write(f"[Block Webex] Message sent to {target_key}={target_value}", type=OK)
        return True

    #room_id -> roomId, to_person_email -> toPersonEmail
    def _camel(self, key:str)->str:
        first, *rest = key.split("_")
        return first + "".join(part.capitalize() for part in rest)

    #Jeton d'interpolation unique, ex. "{files}" ou "{report.path}" (rien autour).
    _SINGLE_TOKEN_RE = re.compile(r'^\s*\{([\w\.\[\]]+)\}\s*$')

    #Retourne {"path","filename"} ou None. Accepte un chemin, une référence "{var}" vers une structure de
    #fichier (ou une liste : seul le premier élément est retenu, Webex n'acceptant qu'un fichier), ou un dict.
    def _resolveAttachment(self, value, context:PipelineContext):
        if value is None or value == "":
            return None

        if isinstance(value, (list, tuple)):
            if len(value) > 1:
                Logger.write(f"[Block Webex] Webex accepts one file per message, only the first one is sent", type=ERROR)
            return self._resolveAttachment(value[0], context) if value else None

        if isinstance(value, dict):
            path = value.get("path")
            if not path:
                Logger.write(f"[Block Webex] Attachment entry without 'path' ignored : {value}", type=ERROR)
                return None
            path = context.transform(path) if isinstance(path, str) else path
            return {"path": path, "filename": value.get("filename") or os.path.basename(path)}

        if isinstance(value, str):
            match = self._SINGLE_TOKEN_RE.match(value)
            if match:
                try:
                    resolved = context.get(match.group(1))
                except KeyError:
                    resolved = None
                if resolved is not None and not isinstance(resolved, str):
                    return self._resolveAttachment(resolved, context)
            path = context.transform(value)
            return {"path": path, "filename": os.path.basename(path)}

        Logger.write(f"[Block Webex] Unsupported attachment entry ignored : {value!r}", type=ERROR)
        return None
