import litellm
from lib.agent.llmembedder._abstract import LLMEmbedder

"""
Embedder — Génération de vecteurs d'embedding via LiteLLM (pour rag)
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class LiteLLMEmbedder(LLMEmbedder):
    #`config` : configuration de l'embedder de la collection RAG (rag.collections.<collection>.embedder)
    def __init__(self, config: dict):
        super().__init__(config=config)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await litellm.aembedding(
            model=self._model,
            input=texts,
            api_base=self._api_base,
            api_key=self._api_key,
        )
        return [item["embedding"] for item in response.data]


