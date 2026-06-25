import asyncio
from fastapi import APIRouter, HTTPException, Header, Request, UploadFile, File, Form, Depends, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pathlib import Path
from typing import Optional
from lib.http.models import ToolInfo, AuthRequest, HealthResponse, UsageResponse, AuthResponse, RagAddDocumentResponse, RagIndexRequest, RagDeleteDocumentRequest, RagDeleteCollectionRequest, RagStatResponse, RagDeleteCollectionResponse, RagDeleteDocumentResponse

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
_rag_basic_auth_optional = HTTPBasic(auto_error=False)

#Pour gestion des routes acceptant une authentification Basic (admin) OU Bearer (session agent)
async def _usage_auth_dep(
    request: Request,
    credentials: Optional[HTTPBasicCredentials] = Depends(_rag_basic_auth_optional),
):
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        token = authorization[7:]
        if not Auth.checkAuthentification(token=token):
            raise HTTPException(status_code=401, detail="Unauthorized")
        return
    if credentials and AdminAuth.checkAdminCredentials(credentials.username, credentials.password):
        return
    raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"}, detail="Unauthorized")

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
        self.router.add_api_route("/usage", self.usage, methods=["GET"])
        self.router.add_api_route("/tools", self.list_tools, methods=["GET"], response_model=list[ToolInfo])
        self.router.add_api_websocket_route("/ws", self.ws_chat)
        self.router.add_api_route("/files/{key}/{filename}", self.get_file, methods=["GET"])
        self.router.add_api_route("/auth", self.auth, methods=["POST"])
        self.router.add_api_route("/auth", self.logout, methods=["DELETE"])
        self.router.add_api_route("/rag/documents", self.rag_index, methods=["POST"])
        self.router.add_api_route("/rag/documents", self.rag_update, methods=["PUT"])
        self.router.add_api_route("/rag/stats", self.rag_stats, methods=["GET"])
        self.router.add_api_route("/rag/collections/{collection}", self.rag_delete_collection, methods=["DELETE"])
        self.router.add_api_route("/rag/collections/{collection}/documents/{source:path}", self.rag_delete_document, methods=["DELETE"])

    """
    Route [GET] /health : renvoie l'état de santé du service
    Auth    : Basic admin
    Entrée  : (aucun paramètre)
    Sortie  : HealthResponse { status, services[], active_ws, version, version_name }
    """
    async def health(
            self,
            credentials: HTTPBasicCredentials = Depends(_rag_basic_auth),
    ) -> HealthResponse:
        self._check_admin_auth(credentials)
        out = {
            "status" : "ok",
            "services" : [],
            "active_ws" : self._active_ws,
            "version" : StaticConfig.version(),
            "version_name" : StaticConfig.versionName()
        }
        for name in ServiceManager.services:
            out["services"].append(name)

        return out
    
    """
    Route [GET] /usage : renvoie les statistiques d'usage du mois en cours
    Auth    : Basic admin  OU  Bearer token (session agent)
    Entrée  : (aucun paramètre)
    Sortie  : UsageResponse { year, month, token_used, request_count }
    """
    async def usage(
            self,
            _=Depends(_usage_auth_dep),
    ) -> UsageResponse:
        out = LocalData.getLLMUsage(currentMonth=True)[0]
        out['token_limit'] = int(Config.get("llm.max_tokens_month"))
        out['request_limit'] = int(Config.get("llm.max_requests_month"))
        
        return out

    """
    Route [GET] /tools : renvoie les outils MCP actifs
    Auth    : Basic admin
    Entrée  : (aucun paramètre)
    Sortie  : list[ToolInfo] { name, description }
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
    Auth    : Bearer token (query param ?token=) issu de /auth
    Entrée  : token (query string)
              Messages JSON entrants :
                {"type": "message",      "message": "..."}   — envoi d'un message à l'agent
                {"type": "confirmation", "option": N}         — réponse à une demande de confirmation
    Sortie  : Messages JSON sortants (stream) :
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
        #-----------------------------------------------------------------------------
        #Gestion de la vérification de l'authentification
        
        if not token:
            await websocket.close(code=4001, reason="Authentication token is required")
            return

        try:
            decodedToken = Auth.checkAuthentification(token=token)
        except Exception as e:
            Logger.write(f"[HTTP] [WS] ws_chat — Erreur during token verification : {e}", type=ERROR)
            await websocket.close(code=4001, reason="Authentication error")
            return

        if not decodedToken:
            Logger.write("[HTTP] [WS] ws_chat — Invalid token or session expired", type=ERROR)
            await websocket.close(code=4003, reason="Unauthorized")
            return

        if self.agent is None:
            Logger.write("[HTTP] [WS] ws_chat — Agentnon available", type=ERROR)
            await websocket.close(code=4503, reason="Agent non available")
            return

        session_id: str | None = decodedToken.get("session_id")

        if not AuthSessionManager.claim_ws(session_id):
            Logger.write(f"[HTTP] [WS] ws_chat — Session {session_id} already connected", type=WARNING)
            await websocket.close(code=4409, reason="Session already connected")
            return
        

        #Connexion acceptée, ouverture de la session
        await websocket.accept()
        self._active_ws += 1

        inactivity_timeout: int = Config.get(key="app.ws_inactivity_timeout")
        active_stream: asyncio.Task | None = None


        #-----------------------------------------------------------------------------
        #Gestion des échanges client / agent
        try:
            while True:
                try:
                    #Attente de réception d'un message du client
                    data = await asyncio.wait_for(websocket.receive_json(), timeout=inactivity_timeout)
                except asyncio.TimeoutError:
                    Logger.write(f"[HTTP] [WS] ws_chat — Intactivity timeout ({inactivity_timeout}s) for session {session_id}", type=WARNING)
                    await websocket.close(code=1001, reason="Inactivity timeout")
                    break
                except Exception:
                    break

                #Un message a été recu, on récupère le type du message
                msg_type = data.get("type", "message")

                #Type confirmation
                if msg_type == "confirmation":
                    AuthSessionManager.resolve_confirmation(session_id, data.get("option", -1))

                #Type message
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

                    #Appel LLM OK : on récupère le message
                    message = data.get("message", "").strip()
                    if not message:
                        continue

                    async def _stream(msg=message, sid=session_id):
                        try:
                            async for event in self.agent.chatStream(msg, sid):
                                await websocket.send_text(event)
                        except asyncio.CancelledError:
                            #Cas de déconnexion client. On termine silencieusement
                            pass
                        except Exception as e:
                            Logger.write(f"[HTTP] [WS] ws_chat — Streaming error: {e}", type=ERROR)

                    active_stream = asyncio.create_task(_stream())

        except WebSocketDisconnect:
            Logger.write("[HTTP] [WS] ws_chat — Client disconnected", type=WARNING)
        except Exception as e:
            Logger.write(f"[HTTP] [WS] ws_chat — Unexpected error : {e}", type=ERROR)
        finally:
            self._active_ws -= 1
            AuthSessionManager.release_ws(session_id)
            if active_stream:
                active_stream.cancel()

    """
    Route [GET] /files/{key}/{filename} : renvoie un fichier lié à la session
    Auth    : Bearer token via header Authorization  OU  hash du token via query param ?t=
    Entrée  : key      (path)  — identifiant du fichier dans la session
              filename (path)  — nom du fichier à retourner dans la réponse
              Authorization    (header, optionnel) — "Bearer <token>"
              t                (query,  optionnel) — sha256 du token
    Sortie  : FileResponse (contenu binaire du fichier)
    """
    async def get_file(self, key: str, filename: str, authorization: str | None = Header(default=None), t: str | None = Query(default=None)) -> FileResponse:
        session = None

        if authorization and authorization.startswith("Bearer "):
            token = authorization[7:]
            decoded = Auth.checkAuthentification(token=token)
            if not decoded:
                Logger.write(f"[HTTP] [403] get_file — Token invalide ou session expirée", type=ERROR)
                raise HTTPException(status_code=403, detail="Unauthorized")
            session = AuthSessionManager.get(decoded.get("session_id"))
        elif t:
            session = AuthSessionManager.get_by_token_hash(t)
        else:
            raise HTTPException(status_code=401, detail="Authentication required")

        if not session or key not in session.files:
            session_id = session.session_id if session else "?"
            Logger.write(f"[HTTP] [403] get_file — Clé {key} absente de la session {session_id}", type=ERROR)
            raise HTTPException(status_code=403, detail="Unauthorized")

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
    Route [POST] /auth : Authentification au service, ouvre une session
    Auth    : (aucune — endpoint public)
    Entrée  : AuthRequest { authorization: dict }
    Sortie  : AuthResponse { token: str }
    """
    async def auth(self, request: AuthRequest) -> AuthResponse:
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

    """
    Route [DELETE] /auth : Déconnexion — ferme la session associée au token
    Auth    : Bearer token (header Authorization)
    Entrée  : Authorization (header) — "Bearer <token>"
    Sortie  : { detail: "Session closed" }
    """
    async def logout(self, authorization: str | None = Header(default=None)):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Authentication required")
        token = authorization[7:]
        decoded = Auth.checkAuthentification(token=token)
        if not decoded:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        session_id = decoded.get("session_id")
        AuthSessionManager.remove(session_id)
        return {"detail": "Session closed"}

    def _check_admin_auth(self, credentials: HTTPBasicCredentials) -> None:
        if not AdminAuth.checkAdminCredentials(credentials.username, credentials.password):
            raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"}, detail="Unauthorized")

    """
    Route [POST] /rag/documents : Indexe un document dans la base de connaissances
    Auth    : Basic admin
    Entrée  : RagIndexRequest (multipart/form-data)
                text       (form, optionnel) — texte brut à indexer
                file       (file, optionnel) — fichier à indexer
                source     (form, optionnel) — identifiant source du document
                collection (form, optionnel) — collection cible (défaut si absent)
              Au moins `text` ou `file` est requis.
    Sortie  : RagAddDocumentResponse { chunk_indexed, collection }
    """
    async def rag_index(
        self,
        credentials: HTTPBasicCredentials = Depends(_rag_basic_auth),
        req: RagIndexRequest = Depends(),
    ) -> RagAddDocumentResponse:
        self._check_admin_auth(credentials)
        if not req.text and not req.file:
            raise HTTPException(status_code=400, detail="Provide either 'text' or 'file'")

        return await RagHelper.addDocument(
            text=req.text,
            file=req.file,
            source=req.source,
            collection=req.collection
        )


    """
    Route [PUT] /rag/documents : Met à jour un document existant identifié par son `source`
    Supprime les chunks existants puis ré-indexe le nouveau contenu.
    Auth    : Basic admin
    Entrée  : RagIndexRequest (multipart/form-data)
                text       (form, optionnel) — nouveau texte brut
                file       (file, optionnel) — nouveau fichier
                source     (form, requis)    — identifiant du document à mettre à jour
                collection (form, optionnel) — collection cible (défaut si absent)
              Au moins `text` ou `file` est requis. `source` est obligatoire.
    Sortie  : RagAddDocumentResponse { chunk_indexed, collection }
    """
    async def rag_update(
        self,
        credentials: HTTPBasicCredentials = Depends(_rag_basic_auth),
        req: RagIndexRequest = Depends(),
    ) -> RagAddDocumentResponse:
        self._check_admin_auth(credentials)
        if not req.text and not req.file:
            raise HTTPException(status_code=400, detail="Provide either 'text' or 'file'")

        if not req.source and (not req.file or not req.file.filename):
            raise HTTPException(status_code=400, detail="'source' is required to identify the document to update")

        return await RagHelper.updateDocument(
            text=req.text,
            file=req.file,
            source=req.source,
            collection=req.collection
        )

    """
    Route [GET] /rag/stats : Statistiques sur le contenu de la base vectorielle
    Auth    : Basic admin
    Entrée  : (aucun paramètre)
    Sortie  : RagStatResponse { total_chunks, collections[] }
    """
    async def rag_stats(self, credentials: HTTPBasicCredentials = Depends(_rag_basic_auth)) -> RagStatResponse:
        self._check_admin_auth(credentials)
        from lib.rag.vectorstore import VectorStore
        try:
            return await VectorStore.stats()
        except Exception as e:
            Logger.write(f"[HTTP] [500] rag_stats — {str(e)}", type=ERROR)
            raise HTTPException(status_code=500, detail=str(e))

    """
    Route [DELETE] /rag/collections/{collection}/documents/{source} : Supprime un document par sa source
    Auth    : Basic admin
    Entrée  : RagDeleteDocumentRequest (path params)
                collection (path) — nom de la collection
                source     (path) — identifiant source du document à supprimer
    Sortie  : RagDeleteDocumentResponse { deleted_chunks, source, collection }
    """
    async def rag_delete_document(self, req: RagDeleteDocumentRequest = Depends(), credentials: HTTPBasicCredentials = Depends(_rag_basic_auth)) -> RagDeleteDocumentResponse:
        self._check_admin_auth(credentials)
        from lib.rag.vectorstore import VectorStore
        try:
            deleted = await VectorStore.deleteBySource(req.collection, req.source)
            if deleted == 0:
                raise HTTPException(status_code=404, detail=f"No document with source '{req.source}' in collection '{req.collection}'")
            return {"deleted_chunks": deleted, "source": req.source, "collection": req.collection}
        except HTTPException:
            raise
        except Exception as e:
            Logger.write(f"[HTTP] [500] rag_delete_document — {str(e)}", type=ERROR)
            raise HTTPException(status_code=500, detail=str(e))

    """
    Route [DELETE] /rag/collections/{collection} : Supprime tous les documents d'une collection
    Auth    : Basic admin
    Entrée  : RagDeleteCollectionRequest (path params)
                collection (path) — nom de la collection à vider
    Sortie  : RagDeleteCollectionResponse { deleted_chunks, collection }
    """
    async def rag_delete_collection(self, req: RagDeleteCollectionRequest = Depends(), credentials: HTTPBasicCredentials = Depends(_rag_basic_auth)) -> RagDeleteCollectionResponse:
        self._check_admin_auth(credentials)
        from lib.rag.indexer import Indexer
        try:
            indexer = Indexer(collection=req.collection)
            deleted = await indexer.deleteCollection(req.collection)
            return {"deleted_chunks": deleted, "collection": req.collection}
        except Exception as e:
            Logger.write(f"[HTTP] [500] rag_delete_collection — {str(e)}", type=ERROR)
            raise HTTPException(status_code=500, detail=str(e))
