from abc import ABC, abstractmethod

class LLMEmbedder(ABC):
    #---------------------------------------------------------------------------------------------------------
    #Méthodes généralistes

    def __init__(self, config: dict):
        super().__init__()
        self._model    = config["model"]
        self._api_base = config["api_base"]
        self._api_key = config["api_key"]

    #---------------------------------------------------------------------------------------------------------
    #Interface

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]: ...