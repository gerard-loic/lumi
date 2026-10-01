import litellm
from lib.mcp.client import mcp_manager
from lib.files.localdata import LocalData
from lib.process.processmanager import ProcessManager
from lib.agent.llmconnector._abstract import LLMConnector

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
                LocalData.logLLMUsage(session_uid=ProcessManager.getCurrentRootId(), token_used=getattr(usage, "total_tokens", 0))

    #Callback après une requête passée avec succès
    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        self.log_success_event(kwargs, response_obj, start_time, end_time)



"""
LiteLLM — Gestion communication modèle LLM avec LiteLLM
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class LiteLLM(LLMConnector):
    def __init__(self, config:dict, tools_enabled:list=None):
        super().__init__(config=config, tools_enabled=tools_enabled)

        self._tracking = LiteLLMTrackingCallback()
        litellm.callbacks = [self._tracking]

        print(f"[Agent LiteLLM] {len(self._tools)} Loaded MCP tools : {[t['function']['name'] for t in self._tools]}")

    
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
