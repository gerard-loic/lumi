from openai import AsyncOpenAI


"""
LlamaEmbedder — Génération de vecteurs d'embedding via une API Llama compatible OpenAI (pour rag)
Nécessite un serveur exposant /v1/embeddings (llama.cpp lancé avec --embeddings, Ollama ...)
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class LlamaEmbedder:
    #`config` : configuration de l'embedder de la collection RAG (rag.collections.<collection>.embedder)
    def __init__(self, config: dict):
        self._model    = config["model"]
        self._api_base = config["api_base"]
        self._client = AsyncOpenAI(base_url=config["api_base"], api_key=config.get("api_key") or "none")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.embeddings.create(
            model=self._model,
            input=texts,
        )
        return [item.embedding for item in response.data]
