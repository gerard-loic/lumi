from openai import AsyncOpenAI


"""
DigitalOceanEmbedder — Génération de vecteurs d'embedding via DigitalOcean (pour rag)
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class DigitalOceanEmbedder:
    #`config` : configuration de l'embedder de la collection RAG (rag.collections.<collection>.embedder)
    def __init__(self, config: dict):
        self._model    = config["model"]
        self._api_base = config["api_base"]
        self._client = AsyncOpenAI(base_url=config["api_base"], api_key=config["api_key"])

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.embeddings.create(
            model=self._model,
            input=texts,
        )
        return [item.embedding for item in response.data]
