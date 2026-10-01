from openai import AsyncOpenAI
from lib.agent.llmembedder._abstract import LLMEmbedder

"""
LlamaEmbedder — Génération de vecteurs d'embedding via une API Llama compatible OpenAI (pour rag)
Nécessite un serveur exposant /v1/embeddings (llama.cpp lancé avec --embeddings, Ollama ...)
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class LlamaEmbedder(LLMEmbedder):
    #`config` : configuration de l'embedder de la collection RAG (rag.collections.<collection>.embedder)
    def __init__(self, config: dict):
        super().__init__(config=config)
        self._client = AsyncOpenAI(base_url=self._api_base, api_key=self._api_key or "none")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.embeddings.create(
            model=self._model,
            input=texts,
        )
        return [item.embedding for item in response.data]
