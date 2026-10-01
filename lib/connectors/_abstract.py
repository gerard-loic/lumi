from lib.log.logger import Logger, ERROR
from lib.agent.agent import Agent
from abc import ABC, abstractmethod
from fastapi import APIRouter

"""
Connector — Classe parente d'un connecteur d'agent
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Connector(ABC):
    #---------------------------------------------------------------------------------------------------------
    #Méthodes généralistes

    _config = {}
    _started = False
    _name = None

    def __init__(self, name:str, agent:Agent, config:dict={}, profile:str=None):
        super().__init__()
        self._config = config
        self._name = name
        self._agent = agent
        self._profile = profile

    #Lever une exception
    def raiseException(self, message:str):
        Logger.write(text=f"[Connector {self._name}] {message}", type=ERROR)
        raise Exception(f"[Connector {self._name}] {message}")

    #Log d'un message concernant le connecteur
    def log(self, message):
        Logger.write(text=f"[Connector {self._name}] {str(message)}")

    #Retourne une valeur de configuration
    def getConfValue(self, key:str):
        if key not in self._config:
            self.raiseException(message=f"[Connector {self._name}] Config key {key} does not exist")
        else:
            return self._config[key]

    #---------------------------------------------------------------------------------------------------------
    #Interface

    #Démarrer le service
    @abstractmethod
    async def start(self): ...

    #Arrêter le service
    @abstractmethod
    async def stop(self): ...

    #Récupérer les routes à instancier dans le router
    @abstractmethod
    def get_router(self) -> APIRouter: ...




    

    