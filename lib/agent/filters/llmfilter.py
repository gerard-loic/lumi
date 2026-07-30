from lib.log.logger import Logger, ERROR
from lib.utils.dynamicimport import DynamicImport
from lib.agent.profile import Profile

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
    #Initialise les filtres
    def __init__(self, profile:Profile):
        self.filters = []
        for filter_name in profile.getConfigValue("llm.filters", default={}):
            Logger.write("INIT F")
            self.filters.append(DynamicImport.getInstance(className=filter_name, moduleName=filter_name, classPath="lib.agent.filters", configuration=profile.getConfigValue(f"llm.filters.{filter_name}")))

    #Filtre un contenu en fonction des filtres appliqués
    def filter(self, text:str=""):
        for f in self.filters:
            text = f.filter(text=text)
        return text