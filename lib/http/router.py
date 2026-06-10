from fastapi import APIRouter, HTTPException, Header, UploadFile, File, Form, Depends
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pathlib import Path
from typing import Optional
from lib.http.models import ChatRequest, ToolInfo, AuthRequest

from lib.http.auth import Auth, AdminAuth
from lib.mcp.client import mcp_manager
from lib.mcp.services import ServiceManager
from lib.log.logger import Logger, ERROR
from lib.config.config import StaticConfig
from lib.rag.raghelper import RagHelper

_rag_basic_auth = HTTPBasic()

"""
Router — Routeur endpoints serveur API

Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Router:
    def __init__(self):
        self.agent = None
        self.router = APIRouter()
        self.router.add_api_route("/health", self.health, methods=["GET"])
        self.router.add_api_route("/tools", self.list_tools, methods=["GET"], response_model=list[ToolInfo])
        self.router.add_api_route("/chat", self.chat, methods=["POST"])
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
            "version" : StaticConfig.version(),
            "version_name" : StaticConfig.versionName()
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
    Route [POST] /chat : conversation avec l'agent (streamée)
    header Authorization avec token issu de /auth
    """
    async def chat(self, request: ChatRequest, authorization: str | None = Header(default=None)):
        if not authorization:
            Logger.write(f"[HTTP] [401] chat — Authorization header is missing", type=ERROR)
            raise HTTPException(status_code=401, detail="Authorization header is missing")
        if not request.message.strip():
            Logger.write(f"[HTTP] [400] chat — Message is empty", type=ERROR)
            raise HTTPException(status_code=400, detail="Message is empty")

        #Vérification du token d'authentification
        try:
            decodedToken = Auth.checkAuthentification(token=authorization)
        except Exception as e:
            Logger.write(f"[HTTP] [500] chat — Internal authentification error : error while reading authentification token : {e}", type=ERROR)
            raise HTTPException(status_code=500, detail="Internal authentification error")

        if not decodedToken:
            Logger.write(f"[HTTP] [403] chat — Not authorized", type=ERROR)
            raise HTTPException(status_code=403, detail="Not authorized")

        if self.agent is None:
            Logger.write("[HTTP] [503] chat — Service agent not available", type=ERROR)
            raise HTTPException(status_code=503, detail="Service agent not available")

        return StreamingResponse(
            self.agent.chatStream(request.message, decodedToken, request.session_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    """
    Route [GET] /files/{key}/{filename} : renvoie un fichier
    """
    async def get_file(self, key: str, filename: str, authorization: str | None = Header(default=None)):
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