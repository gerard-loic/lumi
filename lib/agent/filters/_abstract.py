from abc import ABC, abstractmethod

"""
LLMFilter — Classe parente des filtres LLM
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class LLMFilter(ABC):
    #---------------------------------------------------------------------------------------------------------
    #Méthodes généralistes

    def __init__(self, configuration:dict={}):
        super().__init__()
        self._configuration = configuration

    #---------------------------------------------------------------------------------------------------------
    #Interface

    @abstractmethod
    def filter(self, text:str=""): ...

