import asyncio
from fastapi import APIRouter, HTTPException, Header, Request, UploadFile, File, Depends, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pathlib import Path
from typing import Optional
from lib.http.models import ToolInfo, AuthRequest, PipelineStartResponse, PipelineInfoRequest, PipelineInfoResponse, PipelineStepInfoRequest, PipelineStepInfoResponse, PipelineStartRequest, PipelineStartBody, HealthResponse, UsageResponse, AuthResponse, RagAddDocumentResponse, RagIndexRequest, RagDeleteDocumentRequest, RagDeleteCollectionRequest, RagStatResponse, RagDeleteCollectionResponse, RagDeleteDocumentResponse, FileUploadResponse, AuthSessionResponse
from lib.http.auth import Auth, AdminAuth
from lib.session.session import AuthSessionManager
from lib.mcp.client import mcp_manager
from lib.mcp.toolloader import ToolLoader, MCPTool
from lib.services.services import ServiceManager
from lib.log.logger import Logger, ERROR, WARNING
from lib.config.config import Config, StaticConfig
from lib.rag.raghelper import RagHelper
from lib.files.localdata import LocalData
from lib.agent.llmlimiter import LLMLimiter
from lib.agent.events import ErrorEvent
from lib.rag.attachement import Attachement
from lib.agent.profile import ProfileManager
from lib.agent.agent import AgentManager
from lib.localization.language import LanguageManager, Language
from lib.localization.traduction import Traduction
from lib.pipelines.pipelinemanager import PipelineManager
from lib.pipelines.pipelinerunner import PipelineRunner
from lib.pipelines.pipeline import Pipeline
from lib.pipelines.pipelineinfo import PipelineInfo
from lib.pipelines.trigger import triggerEvent, TRIGGER_API_CALL

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
        self._active_ws = 0
        self.router = APIRouter()
        self.router.add_api_route("/health", self.health, methods=["GET"])
        self.router.add_api_route("/usage", self.usage, methods=["GET"])
        self.router.add_api_route("/tools", self.list_tools, methods=["GET"], response_model=list[ToolInfo])
        self.router.add_api_websocket_route("/ws", self.ws_chat)
        self.router.add_api_route("/files/{key}/{filename}", self.get_file, methods=["GET"])
        self.router.add_api_route("/files/rag/{collection}/{key}/{filename}", self.get_rag_file, methods=["GET"])
        self.router.add_api_route("/files/upload", self.upload_file, methods=["POST"])
        self.router.add_api_route("/auth", self.auth, methods=["POST"])
        self.router.add_api_route("/auth", self.logout, methods=["DELETE"])
        self.router.add_api_route("/auth", self.auth_session, methods=["GET"])
        self.router.add_api_route("/rag/documents", self.rag_index, methods=["POST"])
        self.router.add_api_route("/rag/documents", self.rag_update, methods=["PUT"])
        self.router.add_api_route("/rag/stats", self.rag_stats, methods=["GET"])
        self.router.add_api_route("/rag/collections/{collection}", self.rag_delete_collection, methods=["DELETE"])
        self.router.add_api_route("/rag/collections/{collection}/documents/{source:path}", self.rag_delete_document, methods=["DELETE"])
        self.router.add_api_route("/pipeline/{pipeline}/start", self.pipeline_start, methods=["POST"])
        self.router.add_api_route("/pipeline/process/{process_uid}", self.pipeline_info, methods=["GET"])
        self.router.add_api_route("/pipeline/process/{process_uid}/{id}", self.pipeline_step_info, methods=["GET"])

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
    Route [GET] /auth : Récupère les informations de la session
    Auth    : Bearer token (header Authorization)
    Entrée  : Authorization (header) — "Bearer <token>"
    Sortie  : FileUploadResponse { key, filename, tokens }
    """
    async def auth_session(self, authorization: str | None = Header(default=None))->AuthSessionResponse:
        #Check présent autorisation
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Authentication required")
        token = authorization[7:]

        #Vérifie le token
        decoded = Auth.checkAuthentification(token=token)
        if not decoded:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        #Récupère la session
        session = AuthSessionManager.get(decoded.get("session_id"))
        if not session:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        #récupère le profil
        profil = ProfileManager.getProfile(session.getProfile())

        #récupère le language
        language = session.getLanguage()

        out = {
            'followup_questions' : profil.getConfigValue(key="llm.followup_questions.enabled", default=False),
            'language' : language.getCode(),
            'attachements' : profil.getConfigValue(key="attachments.enabled", default=False),
            'attachements_max_file_size_mb' : profil.getConfigValue(key="attachments.max_file_size_mb", default=0),
            'attachements_max_files' : profil.getConfigValue(key="attachments.max_files", default=0),
            'attachements_allowed_extensions' : profil.getConfigValue(key="attachments.allowed_extensions", default=[])
        }

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
        out['token_limit'] = int(Config.get("usage.max_tokens_month"))
        out['request_limit'] = int(Config.get("usage.max_requests_month"))
        
        return out

    """
    Route [GET] /tools : renvoie les outils MCP actifs
    Auth    : Basic admin
    Entrée  : profile (query, optionnel) — si fourni, ne renvoie que les outils autorisés
              pour ce profil (`profiles.<profile>.mcp.tools_enabled`) ; sinon renvoie tous
              les outils enregistrés sur le serveur MCP (union de tous les profils)
    Sortie  : list[ToolInfo] { name, description }
    """
    async def list_tools(
            self,
            profile: str | None = Query(default=None),
            credentials: HTTPBasicCredentials = Depends(_rag_basic_auth),
    ) -> list[ToolInfo]:
        self._check_admin_auth(credentials)

        tools_enabled = None
        if profile is not None:
            if not ProfileManager.profileExists(profile):
                raise HTTPException(status_code=404, detail=f"Profile {profile} does not exist")
            tools_enabled = ProfileManager.getProfile(profile).getConfigValue(key="mcp.tools_enabled", default=[])

        try:
            tools = mcp_manager.tools
            if tools_enabled is not None:
                tools = [
                    t for t in tools
                    if ToolLoader.is_enabled(t.name, MCPTool.get_meta(t.name).get("namespace", ""), tools_enabled)
                ]
            return [ToolInfo(name=t.name, description=t.description) for t in tools]
        except Exception as e:
            Logger.write(f"[HTTP] [503] list_tools — Unable reading tools: {e}", type=ERROR)
            raise HTTPException(status_code=503, detail="Unable reading tools")

    """
    Route [WS] /ws : conversation avec l'agent via WebSocket
    Auth    : Bearer token (query param ?token=) issu de /auth
    Entrée  : token (query string)
              Messages JSON entrants :
                {"type": "message",      "message": "..."}   — envoi d'un message à l'agent
                                                                 (les fichiers joints via POST /files/upload sont
                                                                 automatiquement consultables par l'agent via le tool
                                                                 search_attached_files, pas besoin de les référencer ici)
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


        session_id: str | None = decodedToken.get("session_id")
        session = AuthSessionManager.get(session_id)
        language = session.getLanguage()
        t = Traduction(language=language)

        agent = AgentManager.getAgent(name=session.getProfile()) if session else None
        if agent is None:
            Logger.write("[HTTP] [WS] ws_chat — Agent non available", type=ERROR)
            await websocket.close(code=4503, reason="Agent non available")
            return

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
                        await websocket.send_text(ErrorEvent.get(error_code="RATE_LIMIT_EXCEEDED", message=t.trad("[agent.rate_limit_exceeded.usage]")))
                        continue

                    if LLMLimiter.isFloodDetected(session_id):
                        await websocket.send_text(ErrorEvent.get(error_code="RATE_LIMIT_EXCEEDED", message="[agent.rate_limit_exceeded.request]"))
                        continue

                    if active_stream and not active_stream.done():
                        await websocket.send_text(ErrorEvent.get(error_code="RESPONSE_IN_PROGRESS", message=t.trad("[agent.response_in_progress]")))
                        continue

                    #Appel LLM OK : on récupère le message
                    message = data.get("message", "").strip()
                    if not message:
                        continue

                    async def _stream(msg=message, sid=session_id, agent=agent):
                        try:
                            async for event in agent.chatStream(msg, sid):
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

        temp_root = Path(Config.get("directories.temp_dir")).resolve()
        file_path = (temp_root / key).resolve()
        if not file_path.is_relative_to(temp_root):
            Logger.write(f"[HTTP] [400] get_file — File path not valid : {file_path}", type=ERROR)
            raise HTTPException(status_code=400, detail="File path not valid")
        if not file_path.exists():
            Logger.write(f"[HTTP] [404] get_file — file not found : {filename}", type=ERROR)
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(file_path, filename=filename)

    """
    Route [GET] /files/rag/{collection}/{key}/{filename} : renvoie un fichier source conservé dans l'espace de stockage RAG
    Auth    : Bearer token (session active) OU hash du token via query param ?t= OU Basic admin
    Entrée  : collection (path)  — collection RAG concernée
              key        (path)  — identifiant du fichier dans RagStore
              filename   (path)  — nom du fichier à retourner dans la réponse
              Authorization      (header, optionnel) — "Bearer <token>"
              t                  (query,  optionnel)  — sha256 du token d'une session active
    Sortie  : FileResponse (contenu binaire du fichier)
    """
    async def get_rag_file(
        self,
        collection: str,
        key: str,
        filename: str,
        authorization: str | None = Header(default=None),
        t: str | None = Query(default=None),
        credentials: Optional[HTTPBasicCredentials] = Depends(_rag_basic_auth_optional),
    ) -> FileResponse:
        authorized = False

        if authorization and authorization.startswith("Bearer "):
            decoded = Auth.checkAuthentification(token=authorization[7:])
            authorized = bool(decoded and AuthSessionManager.get(decoded.get("session_id")))
        elif t:
            authorized = AuthSessionManager.get_by_token_hash(t) is not None
        elif credentials and AdminAuth.checkAdminCredentials(credentials.username, credentials.password):
            authorized = True

        if not authorized:
            Logger.write(f"[HTTP] [403] get_rag_file — Accès non autorisé à {collection}/{key}", type=ERROR)
            raise HTTPException(status_code=403, detail="Unauthorized")

        storage_root = Path(Config.get("directories.rag_storage_dir")).resolve()
        file_path = (storage_root / collection / key).resolve()
        if not file_path.is_relative_to(storage_root):
            Logger.write(f"[HTTP] [400] get_rag_file — File path not valid : {file_path}", type=ERROR)
            raise HTTPException(status_code=400, detail="File path not valid")
        if not file_path.exists():
            Logger.write(f"[HTTP] [404] get_rag_file — file not found : {filename}", type=ERROR)
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(file_path, filename=filename)

    """
    Route [POST] /files/upload : Upload d'une pièce jointe conversationnelle (texte extrait et rattaché à la session)
    Auth    : Bearer token (header Authorization)
    Entrée  : Authorization (header) — "Bearer <token>"
              file          (multipart, requis) — fichier à joindre à la conversation
    Sortie  : FileUploadResponse { key, filename, tokens }
    """
    async def upload_file(self, file: UploadFile = File(...), authorization: str | None = Header(default=None)) -> FileUploadResponse:
        #Check présent autorisation
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Authentication required")
        token = authorization[7:]

        #Vérifie le token
        decoded = Auth.checkAuthentification(token=token)
        if not decoded:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        #Récupère la session
        session = AuthSessionManager.get(decoded.get("session_id"))
        if not session:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        try:
            res = await Attachement.add(session=session, file=file)
            return res
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"{str(e)}")

    """
    Route [POST] /auth : Authentification au service, ouvre une session
    Auth    : (aucune — endpoint public)
    Entrée  : AuthRequest { authorization: dict, profile: str }
    Sortie  : AuthResponse { token: str }
    """
    async def auth(self, request: AuthRequest) -> AuthResponse:
        #Vérification profil
        profile = "default"
        if ProfileManager.profileExists(request.profile):
            profile = request.profile

        #Language
        language = Config.get("app.default_language")
        if request.language is not None:
            if LanguageManager.languageExists(request.language):
                language = request.language
            else:
                raise HTTPException(status_code=400, detail=f"Language '{request.language}' does not exist")
            if language not in Config.get(f"profiles.{profile}.languages", [Config.get("app.default_language")]):
                raise HTTPException(status_code=400, detail=f"Language '{language}' not allowed for profile '{profile}'")
        language = LanguageManager.getLanguage(code=language)
            
        try:
            token = Auth.authenticate(authorization=request.authorization, profile=profile, language=language)
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
        from lib.rag.indexer import Indexer
        try:
            indexer = Indexer(collection=req.collection)
            deleted = await indexer.deleteDocument(req.source, req.collection)
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

    async def pipeline_start(self, req: PipelineStartRequest = Depends(), body: Optional[PipelineStartBody] = None, credentials: HTTPBasicCredentials = Depends(_rag_basic_auth)) -> PipelineStartResponse:
        self._check_admin_auth(credentials)

        if not PipelineManager.pipelineExists(pipeline_uid=req.pipeline):
            Logger.write(f"[HTTP] [400] pipeline_start : pipeline {req.pipeline} does not exist", type=ERROR)
            raise HTTPException(status_code=400, detail=str(f"[HTTP] [400] pipeline_start : pipeline {req.pipeline} does not exist"))

        #Le payload JSON éventuel est transmis au pipeline via l'event : il atterrit dans le
        #contexte sous "trigger.data" (cf. PipelineRunner._run).
        payload = body.payload if body is not None and body.payload is not None else {}
        out = PipelineManager.trigger(event=triggerEvent(type=TRIGGER_API_CALL, data=payload), target_pipelines=[req.pipeline])

        out = {
            "pipelines" : out
        }

        return out

    async def pipeline_info(self, req: PipelineInfoRequest = Depends(), credentials: HTTPBasicCredentials = Depends(_rag_basic_auth)) -> PipelineInfoResponse:
        self._check_admin_auth(credentials)

        out = PipelineInfo.get(process_uid=req.process_uid)
        if out is None:
            Logger.write(f"[HTTP] [404] pipeline_info : process {req.process_uid} does not exist", type=ERROR)
            raise HTTPException(status_code=404, detail=str(f"[HTTP] [404] pipeline_info : process {req.process_uid} does not exist"))

        return out

    """
    Route [GET] /pipeline/process/{process_uid}/{id} : renvoie le détail d'une étape d'un process
    Auth    : Basic admin
    Entrée  : process_uid (path) — identifiant du process
              id          (path) — identifiant de l'étape (pipeline_block)
    Sortie  : PipelineStepInfoResponse { id, process_uid, pipeline_uid, name, created_at, is_success, logs }
    """
    async def pipeline_step_info(self, req: PipelineStepInfoRequest = Depends(), credentials: HTTPBasicCredentials = Depends(_rag_basic_auth)) -> PipelineStepInfoResponse:
        self._check_admin_auth(credentials)

        out = PipelineInfo.getStep(process_uid=req.process_uid, step_id=req.id)
        if out is None:
            Logger.write(f"[HTTP] [404] pipeline_step_info : step {req.id} of process {req.process_uid} does not exist", type=ERROR)
            raise HTTPException(status_code=404, detail=str(f"[HTTP] [404] pipeline_step_info : step {req.id} of process {req.process_uid} does not exist"))

        return out