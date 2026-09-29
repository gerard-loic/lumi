import litellm


"""
Embedder — Génération de vecteurs d'embedding via LiteLLM (pour rag)
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class LiteLLMEmbedder:
    #`config` : configuration de l'embedder de la collection RAG (rag.collections.<collection>.embedder)
    def __init__(self, config: dict):
        self._model    = config["model"]
        self._api_base = config["api_base"]
        self._api_key  = config["api_key"]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await litellm.aembedding(
            model=self._model,
            input=texts,
            api_base=self._api_base,
            api_key=self._api_key,
        )
        return [item["embedding"] for item in response.data]


