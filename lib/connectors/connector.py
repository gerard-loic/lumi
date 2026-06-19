from lib.config.config import Config
from lib.log.logger import Logger, OK, ERROR, WARNING
from lib.agent.agent import Agent

class Connector:
    _config = {}
    _started = False
    _name = None

    def __init__(self, name:str, agent:Agent, config:dict={},):
        self._config = config
        self._name = name
        self._agent = agent

    async def start(self):
        Logger.write(text=f"[Connector {self._name}] started", type=OK)
        self._started = True

    async def stop(self):
        Logger.write(text=f"[Connector {self._name}] stopped", type=WARNING)
        self._started = False

    def get_router(self):
        return None

    def getConfValue(self, key:str):
        if key not in self._config:
            self.raiseException(message=f"Config key {key} does not exist")
        else:
            return self._config[key]

    def raiseException(self, message:str):
        Logger.write(text=f"[Connector {self._name}] {message}", type=ERROR)


class ConnectorManager:
    _connectors = {}

    @staticmethod
    async def init(agent:Agent):
        from lib.connectors.webex.connector import WebexConnector
        #Initialisation
        connectors = Config.get("connectors")
        for connector in connectors:
            if connector == "webex":
                ConnectorManager._connectors[connector] = WebexConnector(agent=agent, config=connectors[connector])
            else:
                Logger.write(f"[ConnectorManager] Connector {connector} does not exists", ERROR)
                raise Exception(f"[ConnectorManager] Connector {connector} does not exists")

        #Démarrage des connecteurs
        for connector in ConnectorManager._connectors:
            await ConnectorManager._connectors[connector].start()

    @staticmethod
    def get_routers():
        routers = []
        for connector in ConnectorManager._connectors.values():
            router = connector.get_router()
            if router is not None:
                routers.append(router)
        return routers
