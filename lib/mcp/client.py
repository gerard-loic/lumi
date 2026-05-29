"""
Gestion de la session MCP comme singleton.
La connexion est ouverte une seule fois au démarrage de FastAPI
et partagée entre toutes les requêtes — évite de respawner app.py
à chaque appel.
"""

import json
import sys
from contextlib import asynccontextmanager
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import lib.config.settings as settings
from lib.config.config import Config

class MCPClientManager:
    def __init__(self):
        self._session: ClientSession | None = None
        self._tools: list = []

    @asynccontextmanager
    async def run(self):
        """Context manager à utiliser dans le lifespan FastAPI."""
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[settings.MCP_SERVER],
            env=None
        )
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                self._session = session
                await session.initialize()
                tools_response = await session.list_tools()
                self._tools = tools_response.tools
                print(f"[MCP] Session démarrée — {len(self._tools)} outil(s) : "
                      f"{[t.name for t in self._tools]}")
                yield
        self._session = None
        self._tools = []
        print("[MCP] Session fermée.")

    @property
    def session(self) -> ClientSession:
        if not self._session:
            raise RuntimeError("MCPClientManager non démarré.")
        return self._session

    @property
    def tools(self) -> list:
        return self._tools

    def tools_as_openai_format(self) -> list[dict]:
        """Convertit les tools MCP au format attendu par Ollama.
        bearer_token est retiré du schéma : le LLM ne doit pas le fournir."""
        result = []
        for t in self._tools:
            schema = dict(t.inputSchema)
            properties = {k: v for k, v in schema.get("properties", {}).items() if k != "bearer_token"}
            required = [r for r in schema.get("required", []) if r != "bearer_token"]
            result.append({
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": {**schema, "properties": properties, "required": required},
                }
            })
        return result

    async def call_tool(self, name: str, arguments: dict, bearer: str | None = None):
        """Appelle un outil MCP. Injecte bearer_token si le tool le requiert."""
        tool = next((t for t in self._tools if t.name == name), None)
        if bearer and tool and "bearer_token" in tool.inputSchema.get("properties", {}):
            arguments = {**arguments, "bearer_token": bearer}
        result = await self.session.call_tool(name, arguments)
        if result.structuredContent:
            return json.dumps(result.structuredContent)
        return result.content[0].text if result.content else "{}"


# Instance globale — un seul subprocess MCP pour tout le service
mcp_manager = MCPClientManager()
