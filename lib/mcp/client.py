"""
Gestion de la session MCP comme singleton.
La connexion est ouverte une seule fois au démarrage de FastAPI
et partagée entre toutes les requêtes — le serveur MCP tourne dans le
même processus via transport in-memory (pas de subprocess).
"""

import asyncio
import json
import anyio
from contextlib import asynccontextmanager
from mcp import ClientSession
from mcp.shared.memory import create_client_server_memory_streams
from lib.config.config import Config
from lib.mcp.services import ServiceManager
from lib.mcp.tools import MCPTool
from lib.http.auth import Auth
from lib.log.logger import Logger, ERROR
import sys

class MCPToolError(Exception):
    """Levée quand un outil MCP retourne une erreur applicative."""
    pass

"""
MCPClientManager — Gestion MCP
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class MCPClientManager:
    def __init__(self):
        self._session: ClientSession | None = None
        self._tools: list = []
        self._call_lock = asyncio.Lock()

    @asynccontextmanager
    async def run(self):
        """Context manager à utiliser dans le lifespan FastAPI."""
        from lib.mcp.server import create_app
        mcp_app = create_app()

        async with create_client_server_memory_streams() as (client_streams, server_streams):
            client_read, client_write = client_streams
            server_read, server_write = server_streams

            async with anyio.create_task_group() as tg:
                tg.start_soon(
                    mcp_app._mcp_server.run,
                    server_read,
                    server_write,
                    mcp_app._mcp_server.create_initialization_options(),
                )

                async with ClientSession(client_read, client_write) as session:
                    self._session = session
                    await session.initialize()
                    tools_response = await session.list_tools()
                    self._tools = tools_response.tools
                    print(f"[MCP] Session started — {len(self._tools)} tools : "
                          f"{[t.name for t in self._tools]}")
                    yield

                tg.cancel_scope.cancel()

        self._session = None
        self._tools = []
        print("[MCP] Session closed")

    @property
    def session(self) -> ClientSession:
        if not self._session:
            Logger.write("MCPClientManager not started", type=ERROR)
            raise RuntimeError("MCPClientManager not started")
        return self._session

    @property
    def tools(self) -> list:
        return self._tools

    def tools_as_openai_format(self, exclude_restricted: bool = False) -> list[dict]:
        """Convertit les tools MCP au format attendu par le LLM."""
        result = []
        for t in self._tools:
            if exclude_restricted and MCPTool.get_meta(t.name).get("restricted", False):
                continue
            schema = dict(t.inputSchema)
            properties = {k: v for k, v in schema.get("properties", {}).items()}
            required = [r for r in schema.get("required", [])]
            result.append({
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": {**schema, "properties": properties, "required": required},
                }
            })
        return result

    async def call_tool(self, name: str, arguments: dict):
        """Appelle un outil MCP. """

        async with self._call_lock:
            ServiceManager.setAuthorization(authorization=Auth.getAuthentication())
            result = await self.session.call_tool(name, arguments)

        if result.isError:
            error_text = result.content[0].text if result.content else "unknown error"
            Logger.write(f"MCP tool {name} returned an error : {error_text}")
            raise MCPToolError(error_text)

        if result.structuredContent:
            data = dict(result.structuredContent)
            events = data.pop("events", [])
            llm_result = json.dumps(data.get("result", data))
            return llm_result, events
        if not result.content:
            return "{}", []
        if len(result.content) == 1:
            try:
                data = json.loads(result.content[0].text)
                if isinstance(data, dict) and ("result" in data or "events" in data):
                    events = data.pop("events", [])
                    return json.dumps(data.get("result", data)), events
            except (json.JSONDecodeError, TypeError):
                pass
            return result.content[0].text, []
        # FastMCP sérialise une liste de Pydantic models en plusieurs TextContent séparés
        try:
            return json.dumps([json.loads(c.text) for c in result.content if hasattr(c, "text")]), []
        except (json.JSONDecodeError, ValueError):
            return "\n".join(c.text for c in result.content if hasattr(c, "text")), []


# Instance globale — un seul serveur MCP in-process pour tout le service
mcp_manager = MCPClientManager()
