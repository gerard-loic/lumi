"""
Retriever — Recherche sémantique dans le VectorStore

Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""

from lib.rag.vectorstore import VectorStore
from lib.config.config import Config
from lib.log.logger import Logger, ERROR
from lib.agent.llmconnector.litellm import LiteLLMEmbedder


class Retriever:
    def __init__(self, collection: str = None):
        self._collection = collection or Config.get("rag.collection")
        self._top_k      = Config.get("rag.top_k")

        model_connector = Config.get("llm.connector")
        if model_connector == "LiteLLM":
            self._embedder = LiteLLMEmbedder()
        else:
            Logger.write(text=f"LLM connector {model_connector} not supported", type=ERROR)
            raise Exception(f"LLM connector {model_connector} not supported")

    async def search(self, query: str, top_k: int = None) -> list[dict]:
        embeddings = await self._embedder.embed([query])
        return await VectorStore.search(self._collection, embeddings[0], top_k or self._top_k)
