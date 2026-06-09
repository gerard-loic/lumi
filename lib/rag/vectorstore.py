"""
VectorStore : façade statique pour l'accès au store vectoriel RAG
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>

Sélectionne et délègue dynamiquement les opérations au connecteur configuré
via RAG_STORAGE_CONNECTOR (ex. PgVector). Expose les opérations de base :
création de table, insertion, recherche par similarité, statistiques, et
gestion des sources/collections.
"""
import asyncio
import json
import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector
from lib.config.config import Config
from lib.log.logger import Logger, ERROR
from lib.rag.ragconnector.pgvector import PgVector


class VectorStore:
    _connector = None

    @staticmethod
    def _connect():
        rag_connector = Config.get("RAG_STORAGE_CONNECTOR")
        if rag_connector == "PgVector":
            VectorStore._connector = PgVector
        else:
            Logger.write(f"RAG connector {rag_connector} not supported !", ERROR)
            raise Exception(f"RAG connector {rag_connector} not supported !")

    @staticmethod
    async def ensureTable() -> None:
        VectorStore._connect()
        return await VectorStore._connector.ensureTable()
        
    @staticmethod
    async def insert(collection: str, content: str, metadata: dict, embedding: list[float]) -> None:
        VectorStore._connect()
        return await VectorStore._connector.insert(collection=collection, content=content, metadata=metadata, embedding=embedding)

    @staticmethod
    async def search(collection: str, embedding: list[float], top_k: int) -> list[dict]:
        VectorStore._connect()
        return await VectorStore._connector.search(collection=collection, embedding=embedding, top_k=top_k)

    @staticmethod
    async def stats() -> dict:
        VectorStore._connect()
        return await VectorStore._connector.stats()

    @staticmethod
    async def sourceExists(collection: str, source: str) -> bool:
        VectorStore._connect()
        return await VectorStore._connector.sourceExists(collection=collection, source=source)
        
    @staticmethod
    async def deleteBySource(collection: str, source: str) -> int:
        VectorStore._connect()
        return await VectorStore._connector.deleteBySource(collection=collection, source=source)
        
    @staticmethod
    async def deleteCollection(collection: str) -> int:
        VectorStore._connect()
        return await VectorStore._connector.deleteCollection(collection=collection)
        
