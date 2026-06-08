from lib.rag.embedder import Embedder
from lib.rag.vectorstore import VectorStore
from lib.config.config import Config


class Retriever:
    def __init__(self, collection: str = None):
        self._collection = collection or Config.get("RAG_COLLECTION")
        self._top_k      = Config.get("RAG_TOP_K")
        self._embedder   = Embedder()

    async def search(self, query: str, top_k: int = None) -> list[dict]:
        embeddings = await self._embedder.embed([query])
        return await VectorStore.search(self._collection, embeddings[0], top_k or self._top_k)
