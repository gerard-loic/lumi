import asyncio
from fastapi import APIRouter, HTTPException, Header, UploadFile, File, Form, Depends, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pathlib import Path
from typing import Optional
from lib.http.models import ToolInfo, AuthRequest

from lib.http.auth import Auth, AdminAuth
from lib.session.session import AuthSessionManager
from lib.mcp.client import mcp_manager
from lib.mcp.services import ServiceManager
from lib.log.logger import Logger, ERROR, WARNING
from lib.config.config import Config, StaticConfig
from lib.rag.raghelper import RagHelper
from lib.files.localdata import LocalData
from lib.agent.llmlimiter import LLMLimiter
from lib.agent.events import ErrorEvent

_rag_basic_auth = HTTPBasic()

"""
Router — Routeur endpoints serveur API

Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Router:
    def __init__(self):
        self.agent = None
        self._active_ws = 0
        self.router = APIRouter()
        self.router.add_api_route("/health", self.health, methods=["GET"])
        self.router.add_api_route("/tools", self.list_tools, methods=["GET"], response_model=list[ToolInfo])
        self.router.add_api_websocket_route("/ws", self.ws_chat)
        self.router.add_api_route("/files/{key}/{filename}", self.get_file, methods=["GET"])
        self.router.add_api_route("/auth", self.auth, methods=["POST"])
        self.router.add_api_route("/rag/documents", self.rag_index, methods=["POST"])
        self.router.add_api_route("/rag/documents", self.rag_update, methods=["PUT"])
        self.router.add_api_route("/rag/stats", self.rag_stats, methods=["GET"])
        self.router.add_api_route("/rag/collections/{collection}", self.rag_delete_collection, methods=["DELETE"])
        self.router.add_api_route("/rag/collections/{collection}/documents/{source:path}", self.rag_delete_document, methods=["DELETE"])

    """
    Route [GET] /health : renvoie l'état de santé du service
    """
    async def health(
            self,
            credentials: HTTPBasicCredentials = Depends(_rag_basic_auth),
    ):
        self._check_admin_auth(credentials)
        out = {
            "status" : "ok",
            "services" : [],
            "active_ws" : self._active_ws,
            "version" : StaticConfig.version(),
            "version_name" : StaticConfig.versionName(),
            "llm_usage" : LocalData.getLLMUsage(currentMonth=True)[0]
        }
        for name in ServiceManager.services:
            out["services"].append(name)

        return out

    """
    Route [GET] /tools : renvoie les outils MCP actifs
    """
    async def list_tools(
            self,
            credentials: HTTPBasicCredentials = Depends(_rag_basic_auth),
    ) -> list[ToolInfo]:
        self._check_admin_auth(credentials)
        try:
            return [ToolInfo(name=t.name, description=t.description) for t in mcp_manager.tools]
        except Exception as e:
            Logger.write(f"[HTTP] [503] list_tools — Unable reading tools: {e}", type=ERROR)
            raise HTTPException(status_code=503, detail="Unable reading tools")

    """
    Route [WS] /ws : conversation avec l'agent via WebSocket
    Paramètre : token (query string) issu de /auth

    Protocole messages entrants (JSON) :
      {"type": "message", "message": "..."}   — envoi d'un message à l'agent
      {"type": "confirmation", "option": N}   — réponse à une demande de confirmation

    Protocole messages sortants (JSON) :
      {"type": "token",              "content": "..."}
      {"type": "tool_call",          "tools": "...", "status": "PENDING|OK|ERROR", ...}
      {"type": "confirmation",       "question": "...", "options": [...]}
      {"type": "confirmation_refused"}
      {"type": "rag",                "source": "...", "locations": [...]}
      {"type": "file",               "name": "...", "url": "..."}
      {"type": "url",                "name": "...", "url": "..."}
      {"type": "error",              "error_code": "...", "message": "...", "details": "..."}
      {"type": "end"}
    """
    async def ws_chat(self, websocket: WebSocket, token: str = Query(...)):
        if not token:
            await websocket.close(code=4001, reason="Token manquant")
            return

        try:
            decodedToken = Auth.checkAuthentification(token=token)
        except Exception as e:
            Logger.write(f"[HTTP] [WS] ws_chat — Erreur de vérification du token : {e}", type=ERROR)
            await websocket.close(code=4001, reason="Authentication error")
            return

        if not decodedToken:
            Logger.write("[HTTP] [WS] ws_chat — Token invalide ou session expirée", type=ERROR)
            await websocket.close(code=4003, reason="Unauthorized")
            return

        if self.agent is None:
            Logger.write("[HTTP] [WS] ws_chat — Agent non disponible", type=ERROR)
            await websocket.close(code=4503, reason="Agent non available")
            return

        session_id: str | None = decodedToken.get("session_id")

        if not AuthSessionManager.claim_ws(session_id):
            Logger.write(f"[HTTP] [WS] ws_chat — Session {session_id} déjà connectée", type=WARNING)
            await websocket.close(code=4409, reason="Session already connected")
            return

        await websocket.accept()
        self._active_ws += 1

        inactivity_timeout: int = Config.get(key="app.ws_inactivity_timeout")
        active_stream: asyncio.Task | None = None

        try:
            while True:
                try:
                    data = await asyncio.wait_for(websocket.receive_json(), timeout=inactivity_timeout)
                except asyncio.TimeoutError:
                    Logger.write(f"[HTTP] [WS] ws_chat — Timeout d'inactivité ({inactivity_timeout}s) pour la session {session_id}", type=WARNING)
                    await websocket.close(code=1001, reason="Inactivity timeout")
                    break
                except Exception:
                    break

                msg_type = data.get("type", "message")

                if msg_type == "confirmation":
                    AuthSessionManager.resolve_confirmation(session_id, data.get("option", -1))

                elif msg_type == "message":
                    #Verification du droit d'appel du LLM
                    if LLMLimiter.isRequestUsageExceeded() or LLMLimiter.isTokenUsageExceeded():
                        await websocket.send_text(ErrorEvent.get(error_code="RATE_LIMIT_EXCEEDED", message="Request usage limit exceeded"))
                        continue

                    if LLMLimiter.isFloodDetected(session_id):
                        await websocket.send_text(ErrorEvent.get(error_code="RATE_LIMIT_EXCEEDED", message="Too many requests, please slow down"))
                        continue

                    if active_stream and not active_stream.done():
                        await websocket.send_text(ErrorEvent.get(error_code="RESPONSE_IN_PROGRESS", message="A response is already in progress, please wait"))
                        continue

                    message = data.get("message", "").strip()
                    if not message:
                        continue

                    async def _stream(msg=message, sid=session_id, auth=decodedToken):
                        try:
                            async for event in self.agent.chatStream(msg, auth, sid):
                                await websocket.send_text(event)
                        except asyncio.CancelledError:
                            pass
                        except Exception as e:
                            Logger.write(f"[HTTP] [WS] ws_chat — Erreur streaming : {e}", type=ERROR)

                    active_stream = asyncio.create_task(_stream())

        except WebSocketDisconnect:
            Logger.write("[HTTP] [WS] ws_chat — Client déconnecté", type=WARNING)
        except Exception as e:
            Logger.write(f"[HTTP] [WS] ws_chat — Erreur inattendue : {e}", type=ERROR)
        finally:
            self._active_ws -= 1
            AuthSessionManager.release_ws(session_id)
            if active_stream:
                active_stream.cancel()

    """
    Route [GET] /files/{key}/{filename} : renvoie un fichier
    """
    async def get_file(self, key: str, filename: str, authorization: str | None = Header(default=None)):
        token = None
        if authorization and authorization.startswith("Bearer "):
            token = authorization[7:]
        if not token:
            raise HTTPException(status_code=401, detail="Token manquant")

        decoded = Auth.checkAuthentification(token=token)
        if not decoded:
            Logger.write(f"[HTTP] [403] get_file — Token invalide ou session expirée", type=ERROR)
            raise HTTPException(status_code=403, detail="Non autorisé")

        session_id = decoded.get("session_id")
        session = AuthSessionManager.get(session_id)
        if not session or key not in session.files:
            Logger.write(f"[HTTP] [403] get_file — Clé {key} absente de la session {session_id}", type=ERROR)
            raise HTTPException(status_code=403, detail="Accès refusé")

        temp_root = Path("temp").resolve()
        file_path = (temp_root / key).resolve()
        if not file_path.is_relative_to(temp_root):
            Logger.write(f"[HTTP] [400] get_file — File path not valid : {file_path}", type=ERROR)
            raise HTTPException(status_code=400, detail="File path not valid")
        if not file_path.exists():
            Logger.write(f"[HTTP] [404] get_file — file not found : {filename}", type=ERROR)
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(file_path, filename=filename)

    """
    Route [POST] /auth : Authentification au service
    """
    async def auth(self, request: AuthRequest):
        try:
            token = Auth.authenticate(request.authorization)
        except Exception as e:
            Logger.write(f"[HTTP] [500] auth — Internal authentification error: {str(e)}", type=ERROR)
            raise HTTPException(status_code=500, detail=f"Internal authentification error")
        if token is None:
            Logger.write(f"[HTTP] [409] auth — Session already connected", type=ERROR)
            raise HTTPException(status_code=409, detail="A session is already active for this user")
        if not token:
            Logger.write(f"[HTTP] [403] auth — Unauthorized", type=ERROR)
            raise HTTPException(status_code=403, detail="Unauthorized")
        return {"token": token}

    def _check_admin_auth(self, credentials: HTTPBasicCredentials) -> None:
        if not AdminAuth.checkAdminCredentials(credentials.username, credentials.password):
            raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"}, detail="Unauthorized")

    """
    Route [POST] /rag/documents : Indexe un document dans la base de connaissances
    Accepte soit du texte brut (champ `text`), soit un fichier (champ `file`).
    """
    async def rag_index(
        self,
        credentials: HTTPBasicCredentials = Depends(_rag_basic_auth),
        text:       Optional[str]        = Form(default=None),
        file:       Optional[UploadFile] = File(default=None),
        source:     Optional[str]        = Form(default=None),
        collection: Optional[str]        = Form(default=None),
    ):
        self._check_admin_auth(credentials)
        if not text and not file:
            raise HTTPException(status_code=400, detail="Provide either 'text' or 'file'")

        return await RagHelper.addDocument(
            text=text,
            file=file,
            source=source,
            collection=collection
        )


    """
    Route [PUT] /rag/documents : Met à jour un document existant identifié par son `source`
    Supprime les chunks existants puis ré-indexe le nouveau contenu.
    """
    async def rag_update(
        self,
        credentials: HTTPBasicCredentials = Depends(_rag_basic_auth),
        source:     Optional[str]        = Form(default=None),
        text:       Optional[str]        = Form(default=None),
        file:       Optional[UploadFile] = File(default=None),
        collection: Optional[str]        = Form(default=None),
    ):
        self._check_admin_auth(credentials)
        if not text and not file:
            raise HTTPException(status_code=400, detail="Provide either 'text' or 'file'")

        if not source and (not file or not file.filename):
                raise HTTPException(status_code=400, detail="'source' is required to identify the document to update")

        return await RagHelper.updateDocument(
            text=text,
            file=file,
            source=source,
            collection=collection
        )

    """
    Route [GET] /rag/stats : Statistiques sur le contenu de la base vectorielle
    """
    async def rag_stats(self, credentials: HTTPBasicCredentials = Depends(_rag_basic_auth)):
        self._check_admin_auth(credentials)
        from lib.rag.vectorstore import VectorStore
        try:
            return await VectorStore.stats()
        except Exception as e:
            Logger.write(f"[HTTP] [500] rag_stats — {str(e)}", type=ERROR)
            raise HTTPException(status_code=500, detail=str(e))

    """
    Route [DELETE] /rag/collections/{collection}/documents/{source} : Supprime un document par sa source
    """
    async def rag_delete_document(self, collection: str, source: str, credentials: HTTPBasicCredentials = Depends(_rag_basic_auth)):
        self._check_admin_auth(credentials)
        from lib.rag.vectorstore import VectorStore
        try:
            deleted = await VectorStore.deleteBySource(collection, source)
            if deleted == 0:
                raise HTTPException(status_code=404, detail=f"No document with source '{source}' in collection '{collection}'")
            return {"deleted_chunks": deleted, "source": source, "collection": collection}
        except HTTPException:
            raise
        except Exception as e:
            Logger.write(f"[HTTP] [500] rag_delete_document — {str(e)}", type=ERROR)
            raise HTTPException(status_code=500, detail=str(e))

    """
    Route [DELETE] /rag/collections/{collection} : Supprime tous les documents d'une collection
    """
    async def rag_delete_collection(self, collection: str, credentials: HTTPBasicCredentials = Depends(_rag_basic_auth)):
        self._check_admin_auth(credentials)
        from lib.rag.indexer import Indexer
        try:
            indexer = Indexer(collection=collection)
            deleted = await indexer.deleteCollection(collection)
            return {"deleted_chunks": deleted, "collection": collection}
        except Exception as e:
            Logger.write(f"[HTTP] [500] rag_delete_collection — {str(e)}", type=ERROR)
            raise HTTPException(status_code=500, detail=str(e))
