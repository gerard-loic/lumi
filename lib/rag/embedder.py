from lib.config.config import Config
from lib.agent.llmconnector.litellm import LiteLLMEmbedder
from lib.log.logger import Logger, ERROR

"""
Embedder — Génération de vecteurs d'embedding
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Embedder:
    def __init__(self):
        model_connector = Config.get("llm.connector")
        if model_connector == "LiteLLM":
            self.embedder = LiteLLMEmbedder()
        else:
            Logger.write(text=f"LLM connector {model_connector} not supported", type=ERROR)
            raise Exception(f"LLM connector {model_connector} not supported")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self.embedder.embed(texts=texts)
