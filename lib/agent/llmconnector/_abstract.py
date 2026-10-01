from abc import ABC, abstractmethod
from lib.mcp.client import mcp_manager

class LLMConnector(ABC):

    #---------------------------------------------------------------------------------------------------------
    #Méthodes généralistes

    #Constructeur
    def __init__(self, config:dict, tools_enabled:list=None):
        super().__init__()
        self._model    = config["model"]
        self._api_base = config["api_base"]
        self._api_key  = config.get("api_key")
        self._tools_enabled        = tools_enabled
        self._tools               = mcp_manager.tools_as_openai_format(exclude_restricted=False, tools_enabled=tools_enabled)
        self._tools_no_restricted = mcp_manager.tools_as_openai_format(exclude_restricted=True, tools_enabled=tools_enabled)
        

    #Indique si au moins un outil est disponible pour ce profil (utilisé pour adapter le prompt système)
    def has_tools(self) -> bool:
        return bool(self._tools)
    
    #Retourne un résumé texte (nom + description) des outils réellement disponibles, pour grounder des appels LLM annexes (ex: follow-up)
    def tools_summary(self, exclude_restricted: bool = False) -> str:
        tools = self._tools_no_restricted if exclude_restricted else self._tools
        return "\n".join(f"- {t['function']['name']} : {t['function'].get('description', '')}" for t in tools)

    #---------------------------------------------------------------------------------------------------------
    #Interface
        
    @abstractmethod
    async def callLLM(self, messages: str, stream: bool, exclude_restricted: bool = False, use_tools: bool = True, extra_tools: list | None = None): ...

