import importlib
from lib.config.config import Config
from lib.log.logger import Logger, ERROR

_ALLOWED_FILTERS = {
    "CodeFilter": ("lib.agent.filters.codefilter", "CodeFilter"),
}

"""
LLMFilter — Classe parente des filtres LLM
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class LLMFilter:
    def __init__(self, configuration:dict={}):
        self._configuration = configuration

    def filter(self, text:str=""):
        return text


"""
LLMFilterManager — Gestion des filtres LLM appliqués
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class LLMFilterManager:
    _filters = []

    #Initialise les filtres
    @staticmethod
    def init():
        filters = Config.get("llm.filters")
        for filter_name in filters:
            if filter_name in _ALLOWED_FILTERS:
                module_path, class_name = _ALLOWED_FILTERS[filter_name]
                cls = getattr(importlib.import_module(module_path), class_name)
                LLMFilterManager._filters.append(cls(configuration=filters[filter_name]))
            else:
                Logger.write(text=f"LLM filter {filter_name} not allowed !", type=ERROR)
                raise Exception(f"LLM filter {filter_name} not allowed !")

    #Filtre un contenu en fonction des filtres appliqués
    @staticmethod
    def filter(text:str=""):
        for f in LLMFilterManager._filters:
            text = f.filter(text=text)
        return text