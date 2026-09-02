import litellm
from lib.mcp.client import mcp_manager
from lib.files.localdata import LocalData
from lib.session.session import AuthSessionManager

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
                LocalData.logLLMUsage(session_uid=AuthSessionManager.get_current_id(), token_used=getattr(usage, "total_tokens", 0))

    #Callback après une requête passée avec succès
    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        self.log_success_event(kwargs, response_obj, start_time, end_time)



"""
LiteLLM — Gestion communication modèle LLM avec LiteLLM
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class LiteLLM:
    def __init__(self, config:dict, tools_enabled:list=None):
        self._model    = config["model"]
        self._api_base = config["api_base"]
        self._api_key  = config["api_key"]
        self._tools_enabled        = tools_enabled
        self._tools               = mcp_manager.tools_as_openai_format(exclude_restricted=False, tools_enabled=tools_enabled)
        self._tools_no_restricted = mcp_manager.tools_as_openai_format(exclude_restricted=True, tools_enabled=tools_enabled)

        self._tracking = LiteLLMTrackingCallback()
        litellm.callbacks = [self._tracking]

        print(f"[Agent LiteLLM] {len(self._tools)} Loaded MCP tools : {[t['function']['name'] for t in self._tools]}")

    #Indique si au moins un outil est disponible pour ce profil (utilisé pour adapter le prompt système)
    def has_tools(self) -> bool:
        return bool(self._tools)

    #Retourne un résumé texte (nom + description) des outils réellement disponibles, pour grounder des appels LLM annexes (ex: follow-up)
    def tools_summary(self, exclude_restricted: bool = False) -> str:
        tools = self._tools_no_restricted if exclude_restricted else self._tools
        return "\n".join(f"- {t['function']['name']} : {t['function'].get('description', '')}" for t in tools)

    #Appel du LLM
    #extra_tools : outils des serveurs MCP externes en auth "session" connectés pour ce tour (cf.
    #MCPClientManager.open_session_external_tools) — recalcule la liste envoyée au LLM pour les inclure,
    #plutôt que d'utiliser self._tools/_tools_no_restricted, figés à la construction.
    async def callLLM(self, messages: str, stream: bool, exclude_restricted: bool = False, use_tools: bool = True, extra_tools: list | None = None):
        if not use_tools:
            tools = None
        elif extra_tools:
            tools = mcp_manager.tools_as_openai_format(exclude_restricted=exclude_restricted, tools_enabled=self._tools_enabled, extra_tools=extra_tools)
        else:
            tools = self._tools_no_restricted if exclude_restricted else self._tools
        tools = tools or None
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
        #Configuration issue du profil "default" (utilisé hors contexte de session, ex: RAG/indexation)
        from lib.agent.profile import ProfileManager
        config = ProfileManager.getProfile("default").getConfigValue("llm.LiteLLM")
        self._model    = config["embedding_model"]
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


