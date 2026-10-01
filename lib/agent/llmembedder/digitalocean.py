from openai import AsyncOpenAI
from lib.agent.llmembedder._abstract import LLMEmbedder

"""
DigitalOceanEmbedder — Génération de vecteurs d'embedding via DigitalOcean (pour rag)
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class DigitalOceanEmbedder(LLMEmbedder):
    #`config` : configuration de l'embedder de la collection RAG (rag.collections.<collection>.embedder)
    def __init__(self, config: dict):
        super().__init__(config=config)
        self._client = AsyncOpenAI(base_url=self._api_base, api_key=self._api_key)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.embeddings.create(
            model=self._model,
            input=texts,
        )
        return [item.embedding for item in response.data]
