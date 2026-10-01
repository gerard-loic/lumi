
from lib.log.logger import Logger, ERROR
from lib.rag.collection import RagCollection
from lib.rag.ragconnector.pgvector import PgVector

"""
VectorStore : façade statique pour l'accès au store vectoriel RAG
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>

Sélectionne et délègue dynamiquement les opérations au connecteur configuré
pour la collection via rag.collections.<collection>.connector (ex. PgVector). Expose les opérations de base :
création de table, insertion, recherche par similarité, statistiques, et
gestion des sources/collections.
"""
class VectorStore:
    #Connecteur de la collection
    @staticmethod
    def _connector(collection: str):
        rag_connector = RagCollection.get(collection)["connector"]
        if rag_connector == "PgVector":
            return PgVector
        Logger.write(f"[VectorStore] RAG connector {rag_connector} not supported !", ERROR)
        raise Exception(f"[VectorStore] RAG connector {rag_connector} not supported !")

    #S'assure de créer les prérequis nécessaire au niveau serveur vectoriel pour la collection
    @staticmethod
    async def ensureTable(collection: str) -> None:
        return await VectorStore._connector(collection).ensureTable(collection=collection)
    
    #Insertion
    @staticmethod
    async def insert(collection: str, content: str, metadata: dict, embedding: list[float]) -> None:
        return await VectorStore._connector(collection).insert(collection=collection, content=content, metadata=metadata, embedding=embedding)

    #Recherche
    @staticmethod
    async def search(collection: str, embedding: list[float], top_k: int) -> list[dict]:
        return await VectorStore._connector(collection).search(collection=collection, embedding=embedding, top_k=top_k)

    #Statistiques des collections déclarées
    @staticmethod
    async def stats() -> dict:
        collections = [
            {"name": name, "chunks": await VectorStore._connector(name).stats(collection=name)}
            for name in RagCollection.names()
        ]
        return {"total_chunks": sum(c["chunks"] for c in collections), "collections": collections}

    #Détermine si une source (document) existe
    @staticmethod
    async def sourceExists(collection: str, source: str) -> bool:
        return await VectorStore._connector(collection).sourceExists(collection=collection, source=source)

    #Retourne les métadonnées d'une source (document) déjà indexée, ou None si absente
    @staticmethod
    async def sourceMetadata(collection: str, source: str) -> dict | None:
        return await VectorStore._connector(collection).sourceMetadata(collection=collection, source=source)

    #Supprime une source (document)
    @staticmethod
    async def deleteBySource(collection: str, source: str) -> int:
        return await VectorStore._connector(collection).deleteBySource(collection=collection, source=source)
        
    #Supprime une collection (ensemble de documents)
    @staticmethod
    async def deleteCollection(collection: str) -> int:
        return await VectorStore._connector(collection).deleteCollection(collection=collection)
        
