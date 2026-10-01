from lib.rag.vectorstore import VectorStore
from lib.rag.collection import RagCollection
from lib.rag.embedder import Embedder

"""
Retriever — Recherche sémantique dans le VectorStore
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Retriever:
    DEFAULT_TOP_K = 5

    #`top_k` : nombre de résultats (profiles.<profil>.rag.top_k), DEFAULT_TOP_K à défaut
    def __init__(self, collection: str = None, top_k: int = None):
        #Collection utilisée. Par défaut celle du profil "default" (utilisé hors contexte de session)
        self._collection = collection or RagCollection.ofProfile()
        self._top_k      = top_k or self.DEFAULT_TOP_K

        #Embedder de la collection, le même que celui utilisé à l'indexation (cf. Indexer)
        self._embedder = Embedder(self._collection)

    async def search(self, query: str, top_k: int = None) -> list[dict]:
        embeddings = await self._embedder.embed([query])
        return await VectorStore.search(self._collection, embeddings[0], top_k or self._top_k)
