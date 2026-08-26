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
        service_format = {
            "transport": "str",
            "url": "str",
            "headers": "dict",
        }
        super().__init__(name=name, data=data, serviceDataFormat=service_format)

    #Ouvre la connexion au serveur MCP distant et l'enregistre dans `stack` (AsyncExitStack
    #possédé par MCPClientManager) pour qu'elle reste ouverte pour toute la durée de vie de
    #l'application et soit proprement fermée à l'arrêt.
    async def connect(self, stack: AsyncExitStack) -> ClientSession:
        transport = self.getConfValue(key="transport")
        url = self.getConfValue(key="url")
        headers = self.getConfValue(key="headers") or {}

        if transport == "http":
            read, write, _ = await stack.enter_async_context(streamablehttp_client(url, headers=headers))
        elif transport == "sse":
            read, write = await stack.enter_async_context(sse_client(url, headers=headers))
        else:
            raise ValueError(f"Unsupported MCP transport '{transport}' (expected 'http' or 'sse')")

        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        return session
