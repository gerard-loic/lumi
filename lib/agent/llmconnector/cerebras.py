from openai import AsyncOpenAI
from lib.mcp.client import mcp_manager
from lib.files.localdata import LocalData
from lib.http.auth import Auth

"""
Cerebras — Gestion communication modèle LLM avec Cerebras (Cerebras Cloud Inference API, compatible OpenAI)
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Cerebras:
    def __init__(self, config:dict, tools_enabled:list=None):
        self._model    = config["model"]
        self._client   = AsyncOpenAI(base_url=config["api_base"], api_key=config["api_key"])
        self._tools               = mcp_manager.tools_as_openai_format(exclude_restricted=False, tools_enabled=tools_enabled)
        self._tools_no_restricted = mcp_manager.tools_as_openai_format(exclude_restricted=True, tools_enabled=tools_enabled)

        print(f"[Agent Cerebras] {len(self._tools)} Loaded MCP tools : {[t['function']['name'] for t in self._tools]}")

    #Indique si au moins un outil est disponible pour ce profil (utilisé pour adapter le prompt système)
    def has_tools(self) -> bool:
        return bool(self._tools)

    #Retourne un résumé texte (nom + description) des outils réellement disponibles, pour grounder des appels LLM annexes (ex: follow-up)
    def tools_summary(self, exclude_restricted: bool = False) -> str:
        tools = self._tools_no_restricted if exclude_restricted else self._tools
        return "\n".join(f"- {t['function']['name']} : {t['function'].get('description', '')}" for t in tools)

    #Enregistrement des tokens utilisés pour la session courante
    def _logUsage(self, usage):
        if usage and getattr(usage, "total_tokens", 0) > 0:
            LocalData.logLLMUsage(session_uid=Auth.getSessionId(), token_used=getattr(usage, "total_tokens", 0))

    #Appel du LLM
    async def callLLM(self, messages: str, stream: bool, exclude_restricted: bool = False, use_tools: bool = True):
        tools = (self._tools_no_restricted if exclude_restricted else self._tools) if use_tools else None
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
