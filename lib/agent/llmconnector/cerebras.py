from openai import AsyncOpenAI
from lib.mcp.client import mcp_manager
from lib.files.localdata import LocalData
from lib.process.processmanager import ProcessManager
from lib.agent.llmconnector._abstract import LLMConnector

"""
Cerebras — Gestion communication modèle LLM avec Cerebras (Cerebras Cloud Inference API, compatible OpenAI)
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Cerebras(LLMConnector):
    def __init__(self, config:dict, tools_enabled:list=None):
        super().__init__(config=config, tools_enabled=tools_enabled)
        self._client = AsyncOpenAI(base_url=self._api_base, api_key=self._api_key)
 
        print(f"[Agent Cerebras] {len(self._tools)} Loaded MCP tools : {[t['function']['name'] for t in self._tools]}")


    #Enregistrement des tokens utilisés pour la session courante
    def _logUsage(self, usage):
        if usage and getattr(usage, "total_tokens", 0) > 0:
            LocalData.logLLMUsage(session_uid=ProcessManager.getCurrentRootId(), token_used=getattr(usage, "total_tokens", 0))

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

        if not stream:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=tools,
                stream=False,
            )
            self._logUsage(getattr(response, "usage", None))
            return response

        return await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=tools,
            stream=True,
        )
