import litellm
from lib.config.config import Config


class Embedder:
    def __init__(self):
        self._model    = Config.get("LITELLM_EMBEDDING_MODEL")
        self._api_base = Config.get("LITELLM_API_BASE")
        self._api_key  = Config.get("LITELLM_API_KEY")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await litellm.aembedding(
            model=self._model,
            input=texts,
            api_base=self._api_base,
            api_key=self._api_key,
        )
        return [item["embedding"] for item in response.data]
