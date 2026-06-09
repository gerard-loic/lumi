from fastapi import UploadFile, HTTPException
from lib.rag.indexer import Indexer
from pathlib import Path
from lib.rag.vectorstore import VectorStore
from lib.log.logger import Logger, ERROR
import tempfile, os

"""
RagHelper — Méthodes d'interaction avec le RAG

Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class RagHelper:
    @staticmethod
    async def addDocument(
        text:str=None,
        file:UploadFile=None,
        source:str=None,
        collection:str=None,
    ):
        
        try:
            indexer = Indexer(collection=collection)

            if file:
                #Indexation d'un fichier, il faut au préalable le convertir
                src    = source or file.filename
                suffix = Path(file.filename).suffix if file.filename else ""
                if src:
                    #Vérifie que le document n'existe pas déjà dans la collection
                    if await VectorStore.sourceExists(indexer._collection, src):
                        raise HTTPException(status_code=409, detail=f"Source '{src}' already exists in collection '{indexer._collection}'. Use PUT to update.")
                #Lecture du fichier
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(await file.read())
                    tmp_path = tmp.name
                #Indexation du contenu
                try:
                    count = await indexer.indexFile(tmp_path, source=src)
                finally:
                    os.unlink(tmp_path)
            else:
                #Indexation d'un texte directement
                if source:
                    #Vérifie que le document n'existe pas déjà dans la collection
                    if await VectorStore.sourceExists(indexer._collection, source):
                        raise HTTPException(status_code=409, detail=f"Source '{source}' already exists in collection '{indexer._collection}'. Use PUT to update.")
                metadata = {"source": source} if source else {}
                count    = await indexer.indexText(text, metadata=metadata)

            #Retourne des infos sur ce qui a été indexé
            return {"chunks_indexed": count, "collection": indexer._collection}
        except HTTPException:
            raise
        except Exception as e:
            Logger.write(f"[HTTP] [500] rag_index — {str(e)}", type=ERROR)
            raise HTTPException(status_code=500, detail=str(e))

    @staticmethod
    async def updateDocument(
        text:str=None,
        file:UploadFile=None,
        source:str=None,
        collection:str=None,
    ):
        try:
            
            indexer = Indexer(collection=collection)

            if file:
                #Fichier à réindexer
                src    = source or file.filename
                suffix = Path(file.filename).suffix if file.filename else ""
                #Lecture fichier
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(await file.read())
                    tmp_path = tmp.name
                #Réindexation
                try:
                    result = await indexer.reindexFile(tmp_path, source=src)
                finally:
                    os.unlink(tmp_path)
            else:
                #Texte à réindexer
                result = await indexer.reindexText(source, text)

            #Retourne info sur ce qui a été indexé
            return {**result, "source": source or file.filename, "collection": indexer._collection}
        except HTTPException:
            raise
        except Exception as e:
            Logger.write(f"[HTTP] [500] rag_update — {str(e)}", type=ERROR)
            raise HTTPException(status_code=500, detail=str(e))