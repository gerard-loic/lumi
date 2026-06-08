from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import StreamingResponse, FileResponse
from pathlib import Path

from lib.http.models import ChatRequest, ToolInfo, AuthRequest, IndexRequest
from lib.http.auth import Auth
from lib.mcp.client import mcp_manager
from lib.mcp.services import ServiceManager
from lib.log.logger import Logger, ERROR

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
        self.router.add_api_route("/rag/collections/{collection}", self.rag_delete_collection, methods=["DELETE"])

    """
    Route [GET] /health : renvoie l'état de santé du service
    """
    async def health(self):
        out = {
            "status" : "ok",
            "services" : []
        }
        for name in ServiceManager.services:
            out["services"].append(name)

        return out

    """
    Route [GET] /tools : renvoie les outils MCP actifs
    """
    async def list_tools(self) -> list[ToolInfo]:
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

    """
    Route [POST] /rag/documents : Indexe un document dans la base de connaissances
    """
    async def rag_index(self, request: IndexRequest):
        from lib.rag.indexer import Indexer
        try:
            indexer = Indexer(collection=request.collection)
            metadata = {"source": request.source} if request.source else {}
            count = await indexer.index_text(request.text, metadata=metadata)
            return {"chunks_indexed": count, "collection": indexer._collection}
        except Exception as e:
            Logger.write(f"[HTTP] [500] rag_index — {str(e)}", type=ERROR)
            raise HTTPException(status_code=500, detail=str(e))

    """
    Route [DELETE] /rag/collections/{collection} : Supprime tous les documents d'une collection
    """
    async def rag_delete_collection(self, collection: str):
        from lib.rag.indexer import Indexer
        try:
            indexer = Indexer(collection=collection)
            deleted = await indexer.delete_collection(collection)
            return {"deleted_chunks": deleted, "collection": collection}
        except Exception as e:
            Logger.write(f"[HTTP] [500] rag_delete_collection — {str(e)}", type=ERROR)
            raise HTTPException(status_code=500, detail=str(e))