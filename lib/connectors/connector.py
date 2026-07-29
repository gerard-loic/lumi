from lib.config.config import Config
from lib.log.logger import Logger, OK, ERROR, WARNING
from lib.agent.agent import Agent, AgentManager
from lib.agent.profile import ProfileManager
from lib.utils.dynamicimport import DynamicImport

"""
Connector — Classe parente d'un connecteur d'agent
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Connector:
    _config = {}
    _started = False
    _name = None

    def __init__(self, name:str, agent:Agent, config:dict={}, profile:str=None):
        self._config = config
        self._name = name
        self._agent = agent
        self._profile = profile

    #Démarre le connecteur
    async def start(self):
        Logger.write(text=f"[Connector {self._name}] started", type=OK)
        self._started = True

    #Arrête le connecteur
    async def stop(self):
        Logger.write(text=f"[Connector {self._name}] stopped", type=WARNING)
        self._started = False

    #Retourne les routes additionnelles pour le routeur
    def get_router(self):
        return None

    #Retourne une valeur de configuration
    def getConfValue(self, key:str):
        if key not in self._config:
            self.raiseException(message=f"[Connector {self._name}] Config key {key} does not exist")
        else:
            return self._config[key]

    def raiseException(self, message:str):
        Logger.write(text=f"[Connector {self._name}] {message}", type=ERROR)
        raise Exception(f"[Connector {self._name}] {message}")
    
    def log(self, message):
        Logger.write(text=f"[Connector {self._name}] {str(message)}")


"""
ConnectorManager — Gestion des connecteurs d'agent
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class ConnectorManager:
    _connectors = {}

    #Initialiser les connecteurs : chaque profil peut définir ses propres connecteurs
    #(profiles.<profil>.connectors), avec l'agent de ce profil. Un même type de connecteur
    #(ex: "webex") peut être activé sur plusieurs profils simultanément : chaque instance
    #expose alors ses propres routes, propres à son profil (cf WebexConnector.get_router).
    @staticmethod
    async def init():
        for profile_name in ProfileManager.getProfileNames():
            profile = ProfileManager.getProfile(name=profile_name)
            connectors = profile.getConfigValue(key="connectors", default={})
            for connector in connectors:
                if not connectors[connector]["enabled"]:
                    continue
                key = f"{profile_name}.{connector}"
                ConnectorManager._connectors[key] = DynamicImport.getInstance(className=connector.lower().capitalize()+"Connector",moduleName="connector", classPath="lib.connectors.webex", agent=AgentManager.getAgent(name=profile_name), config=connectors[connector], profile=profile_name)

        #Démarrage des connecteurs
        for connector in ConnectorManager._connectors:
            await ConnectorManager._connectors[connector].start()

    #Obtient les méthodes à ajouter au router
    @staticmethod
    def get_routers():
        routers = []
        for connector in ConnectorManager._connectors.values():
            router = connector.get_router()
            if router is not None:
                routers.append(router)
        return routers
