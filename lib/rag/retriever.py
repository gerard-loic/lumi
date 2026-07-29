

from lib.rag.vectorstore import VectorStore
from lib.config.config import Config
from lib.log.logger import Logger, ERROR
from lib.agent.llmconnector.litellm import LiteLLMEmbedder

"""
Retriever — Recherche sémantique dans le VectorStore
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Retriever:
    def __init__(self, collection: str = None):
        #Collection et connecteur LLM utilisés. Par défaut ceux du profil "default" (utilisé hors contexte de session)
        from lib.agent.profile import ProfileManager
        default_profile = ProfileManager.getProfile("default")
        self._collection = collection or default_profile.getConfigValue("rag.collection")
        self._top_k      = Config.get("rag.top_k")

        model_connector = default_profile.getConfigValue("llm.connector")
        if model_connector == "LiteLLM":
            self._embedder = LiteLLMEmbedder()
        else:
            Logger.write(text=f"LLM connector {model_connector} not supported", type=ERROR)
            raise Exception(f"LLM connector {model_connector} not supported")

    async def search(self, query: str, top_k: int = None) -> list[dict]:
        embeddings = await self._embedder.embed([query])
        return await VectorStore.search(self._collection, embeddings[0], top_k or self._top_k)
