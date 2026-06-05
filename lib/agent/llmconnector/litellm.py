import litellm
from lib.config.config import Config
from lib.mcp.client import mcp_manager

"""
LiteLLM — Gestion communication modèle LLM avec LiteLLM
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class LiteLLM:
    def __init__(self):
        self._model    = Config.get(key="LITELLM_MODEL")
        self._api_base = Config.get(key="LITELLM_API_BASE")
        self._api_key  = Config.get(key="LITELLM_API_KEY")
        self._tools    = mcp_manager.tools_as_openai_format()
        print(f"[Agent LiteLLM] {len(self._tools)} outil(s) chargé(s) : {[t['function']['name'] for t in self._tools]}")

    async def callLLM(self, messages:str, stream:bool):
        response = await litellm.acompletion(
            model=self._model,
            messages=messages,
            tools=self._tools,
            stream=stream,
            api_base=self._api_base,
            api_key=self._api_key,
        )
        return response
    
