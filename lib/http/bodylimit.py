from fastapi import HTTPException
from starlette.types import ASGIApp, Receive, Scope, Send
from lib.config.config import Config

#Marge ajoutée à la taille maximale d'une pièce jointe pour l'enveloppe multipart (délimiteurs, en-têtes de partie)
_MULTIPART_OVERHEAD = 1024 * 1024

"""
BodySizeLimitMiddleware — Limite la taille du corps des requêtes HTTP
Starlette écrit un fichier uploadé entièrement sur disque avant d'appeler la route, sans limite de taille : la
limite doit donc s'appliquer en amont, pendant la réception. Refus en 413 d'après l'en-tête Content-Length s'il
est présent, sinon dès que le volume reçu dépasse la limite (corps envoyé en chunked).
Limites :
  - POST /files/upload : plus grande attachments.max_file_size_mb des profils (+ enveloppe multipart), la limite
    propre au profil de la session étant vérifiée ensuite par la route (cf. Attachement) ;
  - autres routes : app.max_request_body_mb (défaut 100, ex. indexation RAG par l'API d'administration).
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = BodySizeLimitMiddleware._limit(scope["path"])
        content_length = dict(scope["headers"]).get(b"content-length")
        try:
            too_large = content_length is not None and int(content_length) > limit
        except ValueError:
            too_large = False
        if too_large:
            await BodySizeLimitMiddleware._reject(send)
            return

        received = 0
        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    #HTTPException : relayée telle quelle par FastAPI pendant la lecture du corps (réponse 413)
                    raise HTTPException(status_code=413, detail="Request body too large")
            return message

        await self.app(scope, limited_receive, send)

    @staticmethod
    def _limit(path: str) -> int:
        if path == "/files/upload":
            profiles = Config.get("profiles", {})
            max_mb = max((p.get("attachments", {}).get("max_file_size_mb", 20) for p in profiles.values() if p.get("attachments", {}).get("enabled", False)), default=0)
            return int(max_mb * 1024 * 1024) + _MULTIPART_OVERHEAD
        return int(Config.get("app.max_request_body_mb", 100) * 1024 * 1024)

    @staticmethod
    async def _reject(send: Send):
        body = b'{"detail":"Request body too large"}'
        await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
