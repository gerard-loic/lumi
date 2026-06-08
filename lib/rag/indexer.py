from lib.rag.embedder import Embedder
from lib.rag.vectorstore import VectorStore
from lib.config.config import Config


class Indexer:
    def __init__(self, collection: str = None):
        self._collection    = collection or Config.get("RAG_COLLECTION")
        self._chunk_size    = Config.get("RAG_CHUNK_SIZE")
        self._chunk_overlap = Config.get("RAG_CHUNK_OVERLAP")
        self._embedder      = Embedder()

    async def index_text(self, text: str, metadata: dict = None) -> int:
        await VectorStore.ensure_table()
        chunks = self._chunk(text)
        embeddings = await self._embedder.embed(chunks)
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            m = {**(metadata or {}), "chunk_index": i, "total_chunks": len(chunks)}
            await VectorStore.insert(self._collection, chunk, m, emb)
        return len(chunks)

    async def delete_collection(self, collection: str = None) -> int:
        return await VectorStore.delete_collection(collection or self._collection)

    def _chunk(self, text: str) -> list[str]:
        size, overlap = self._chunk_size, self._chunk_overlap
        chunks, start = [], 0
        while start < len(text):
            chunks.append(text[start : start + size])
            start += size - overlap
        return [c for c in chunks if c.strip()]
