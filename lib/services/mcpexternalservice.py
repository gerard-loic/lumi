from contextlib import AsyncExitStack
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.sse import sse_client
from lib.services.services import Service

"""
MCPExternalService — Service représentant un serveur MCP externe (distant, HTTP/SSE).
La connexion réelle (ouverture de session MCP) est pilotée par MCPClientManager
(lib/mcp/client.py), qui possède la boucle événementielle et le task group dans
lesquels la session doit vivre. Ce service ne porte que la configuration de connexion,
au même titre que les autres services (ex: LumePackAPI porte url/timeout).
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class MCPExternalService(Service):

    def __init__(self, name:str, data: dict):
        #`auth` ("static" par défaut, "session" pour une auth par utilisateur — cf. connect()) est lu
        #directement en config par MCPClientManager, pas par cette classe : retiré de `data` avant
        #validation (Service._checkData rejette toute clé absente de serviceDataFormat) pour ne pas
        #casser les configs existantes qui ne le déclarent pas, même principe que `handler`, déjà
        #retiré de `data` par ServiceManager avant l'appel à ce constructeur.
        data = {k: v for k, v in data.items() if k != "auth"}
        #`headers` est optionnel (défaut {}) : un serveur en auth "session" n'a souvent aucun header
        #statique, tout venant du token par utilisateur injecté dans connect(). Défaulté ici plutôt
        #que rendu optionnel dans service_format (Service._checkData exige la présence de chaque clé
        #déclarée, qu'elle accepte ou non `None`).
        data.setdefault("headers", {})
        service_format = {
            "transport": "str",
            "url": "str",
            "headers": "dict",
        }
        super().__init__(name=name, data=data, serviceDataFormat=service_format)

    def checkAuthentication(self, authorization:dict):
        if self.name not in authorization:
            return False
    
        authorization = authorization[self.name]
        if "token" not in authorization:
            return False

        self.authenticated = True
        self.authData = authorization
        return True

    #Ouvre la connexion au serveur MCP distant et l'enregistre dans `stack` (AsyncExitStack
    #possédé par l'appelant — MCPClientManager, pour toute la durée de vie de l'application quand le
    #service est déclaré `auth: "static"` en config (défaut), ou pour la durée de vie d'une session
    #utilisateur quand il est déclaré `auth: "session"` — cf. MCPClientManager.ensure_session_external_tools,
    #qui lit ce champ directement sur la config du service (même logique que le filtrage sur `handler`
    #déjà fait par MCPClientManager._connect_external_servers).
    #`auth_data` : authentification propre à un utilisateur (mode "session"), ex. {"token": "..."}
    #issu de AuthSession.authentication — fusionnée dans les headers en plus de ceux de la config.
    async def connect(self, stack: AsyncExitStack, auth_data: dict | None = None) -> ClientSession:
        transport = self.getConfValue(key="transport")
        url = self.getConfValue(key="url")
        headers = dict(self.getConfValue(key="headers") or {})
        if auth_data and auth_data.get("token"):
            headers["Authorization"] = f"Bearer {auth_data['token']}"

        if transport == "http":
            read, write, _ = await stack.enter_async_context(streamablehttp_client(url, headers=headers))
        elif transport == "sse":
            read, write = await stack.enter_async_context(sse_client(url, headers=headers))
        else:
            raise ValueError(f"Unsupported MCP transport '{transport}' (expected 'http' or 'sse')")

        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        return session
    
