from lib.config.config import Config
from lib.log.logger import Logger, OK, ERROR, WARNING
from lib.agent.agent import Agent, AgentManager
from lib.agent.profile import ProfileManager
from lib.utils.dynamicimport import DynamicImport


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
