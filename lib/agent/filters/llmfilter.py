import importlib
from lib.config.config import Config
from lib.log.logger import Logger, ERROR
from lib.utils.dynamicimport import DynamicImport


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
            LLMFilterManager._filters.append(DynamicImport.getInstance(className=filter_name, moduleName=filter_name, classPath="lib.agent.filters", configuration=Config.get(f"llm.filters.{filter_name}")))

    #Filtre un contenu en fonction des filtres appliqués
    @staticmethod
    def filter(text:str=""):
        for f in LLMFilterManager._filters:
            text = f.filter(text=text)
        return text