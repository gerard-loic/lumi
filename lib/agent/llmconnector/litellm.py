import litellm
from lib.config.config import Config
from lib.mcp.client import mcp_manager
from lib.files.localdata import LocalData
from lib.http.auth import Auth

"""
LiteLLMTrackingCallback — Gestion des callBack LiteLLM
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class LiteLLMTrackingCallback(litellm.integrations.custom_logger.CustomLogger):
    def __init__(self):
        super().__init__()

    #Enregistrement des données d'une requête passée avec succ_s
    def log_success_event(self, kwargs, response_obj, start_time, end_time):
        usage = getattr(response_obj, "usage", None)
        if usage:
            if getattr(usage, "total_tokens", 0) > 0:
                #On log les tokens utilisés
                LocalData.logLLMUsage(session_uid=Auth.getSessionId(), token_used=getattr(usage, "total_tokens", 0))

    #Callback après une requête passée avec succès
    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        self.log_success_event(kwargs, response_obj, start_time, end_time)



"""
LiteLLM — Gestion communication modèle LLM avec LiteLLM
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class LiteLLM:
    def __init__(self):
        self._model    = Config.get(key="llm.litellm.model")
        self._api_base = Config.get(key="llm.litellm.api_base")
        self._api_key  = Config.get(key="llm.litellm.api_key")
        self._tools              = mcp_manager.tools_as_openai_format(exclude_restricted=False)
        self._tools_no_restricted = mcp_manager.tools_as_openai_format(exclude_restricted=True)

        self._tracking = LiteLLMTrackingCallback()
        litellm.callbacks = [self._tracking]

        print(f"[Agent LiteLLM] {len(self._tools)} Loaded MCP tools : {[t['function']['name'] for t in self._tools]}")

    #Appel du LLM
    async def callLLM(self, messages: str, stream: bool, exclude_restricted: bool = False):
        tools = self._tools_no_restricted if exclude_restricted else self._tools
        response = await litellm.acompletion(
            model=self._model,
            messages=messages,
            tools=tools,
            stream=stream,
            api_base=self._api_base,
            api_key=self._api_key,
        )
        return response


"""
Embedder — Génération de vecteurs d'embedding via LiteLLM (pour rag)
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class LiteLLMEmbedder:
    def __init__(self):
        self._model    = Config.get("llm.litellm.embedding_model")
        self._api_base = Config.get("llm.litellm.api_base")
        self._api_key  = Config.get("llm.litellm.api_key")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await litellm.aembedding(
            model=self._model,
            input=texts,
            api_base=self._api_base,
            api_key=self._api_key,
        )
        return [item["embedding"] for item in response.data]


