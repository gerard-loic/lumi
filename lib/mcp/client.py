"""
Gestion de la session MCP comme singleton.
La connexion est ouverte une seule fois au démarrage de FastAPI
et partagée entre toutes les requêtes — le serveur MCP tourne dans le
même processus via transport in-memory (pas de subprocess).
"""

import asyncio
import json
import anyio
from contextlib import asynccontextmanager, AsyncExitStack
from mcp import ClientSession
from mcp.shared.memory import create_client_server_memory_streams
from lib.mcp.toolloader import MCPTool, ToolLoader
from lib.session.session import AuthSessionManager
from lib.log.logger import Logger, ERROR

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
        self._loop: asyncio.AbstractEventLoop | None = None
        #Outils MCP servis par des serveurs externes (distants) plutôt que par le serveur
        #in-process : nom exposé au LLM (préfixé "ext__<service>__") -> (session, nom réel côté serveur).
        self._external_sessions: dict[str, tuple[ClientSession, str]] = {}

    #Context manager à utiliser dans le lifespan FastAPI.
    @asynccontextmanager
    async def run(self):
        from lib.mcp.server import create_app
        mcp_app = create_app()
        self._loop = asyncio.get_running_loop()

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
                    self._tools = list(tools_response.tools)
                    print(f"[MCP] Session started — {len(self._tools)} internal tools : "
                          f"{[t.name for t in self._tools]}")

                    #Connexion aux serveurs MCP externes déclarés comme services (cf. MCPExternalService) :
                    #ouverte pour toute la durée de vie de l'application, via un AsyncExitStack dédié.
                    async with AsyncExitStack() as external_stack:
                        await self._connect_external_servers(external_stack)
                        yield

                tg.cancel_scope.cancel()

        self._session = None
        self._tools = []
        self._external_sessions = {}
        print("[MCP] Session closed")

    #Se connecte à chaque service MCP externe configuré (handler MCPExternalService), récupère ses
    #outils et les fusionne dans self._tools avec un nom préfixé "ext__<service>__<outil>" pour éviter
    #toute collision avec les outils internes ou entre serveurs externes. Un serveur injoignable au
    #démarrage est loggé et ignoré plutôt que de bloquer le démarrage de l'application.
    #
    #Le repérage se fait sur le `handler` déclaré en config plutôt que via isinstance() : ServiceManager
    #charge chaque handler par importlib.spec_from_file_location sous le nom de module `services.<handler>`,
    #distinct du module `lib.services.mcpexternalservice` importé ici — isinstance() contre la classe
    #importée normalement échouerait donc toujours (deux objets classe différents pour le même code).
    async def _connect_external_servers(self, stack: AsyncExitStack) -> None:
        from lib.config.config import Config
        from lib.services.services import ServiceManager

        external_names = [
            name for name, conf in Config.get("services", default={}).items()
            if conf.get("handler") == "MCPExternalService"
        ]

        for name in external_names:
            service = ServiceManager.get(name=name)
            try:
                session = await service.connect(stack)
                tools_response = await session.list_tools()
            except Exception as e:
                Logger.write(f"[MCP] External server '{name}' unreachable, skipped : {e}", type=ERROR)
                continue

            for tool in tools_response.tools:
                exposed_name = f"ext__{name}__{tool.name}"
                self._external_sessions[exposed_name] = (session, tool.name)
                #Namespace "ext.<service>" : réutilise la convention de motifs "namespace.*" déjà
                #supportée par ToolLoader.is_enabled, pour activer ces outils via mcp.tools_enabled.
                MCPTool._registry.setdefault(exposed_name, {})["namespace"] = f"ext.{name}"
                self._tools.append(tool.model_copy(update={"name": exposed_name}))

            print(f"[MCP] External server '{name}' connected — {len(tools_response.tools)} tools : "
                  f"{[t.name for t in tools_response.tools]}")

    @property
    def session(self) -> ClientSession:
        if not self._session:
            Logger.write("MCPClientManager not started", type=ERROR)
            raise RuntimeError("MCPClientManager not started")
        return self._session

    #Boucle événementielle FastAPI (celle qui porte la session/le task group MCP), à utiliser pour
    #exécuter du code appelant call_tool() depuis un autre thread (cf. lib/pipelines/blocks/agent.py) :
    #la session MCP est liée à cette boucle, l'appeler depuis une autre (ex: asyncio.run() dans un thread) bloque indéfiniment.
    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if not self._loop:
            Logger.write("MCPClientManager not started", type=ERROR)
            raise RuntimeError("MCPClientManager not started")
        return self._loop

    @property
    def tools(self) -> list:
        return self._tools

    #Indique si un outil est autorisé pour un profil donné (liste de motifs `mcp.tools_enabled`).
    #tools_enabled=None désactive le filtrage (tous les outils enregistrés sont autorisés).
    def _is_allowed(self, tool_name: str, tools_enabled: list | None) -> bool:
        if tools_enabled is None:
            return True
        namespace = MCPTool.get_meta(tool_name).get("namespace", "")
        return ToolLoader.is_enabled(tool_name, namespace, tools_enabled)

    #Convertit les tools MCP au format attendu par le LLM.
    #tools_enabled : motifs `mcp.tools_enabled` du profil courant, pour ne présenter au LLM
    #que les outils autorisés pour ce profil (le serveur MCP, lui, les a tous enregistrés).
    def tools_as_openai_format(self, exclude_restricted: bool = False, tools_enabled: list | None = None) -> list[dict]:
        result = []
        for t in self._tools:
            if exclude_restricted and MCPTool.get_meta(t.name).get("restricted", False):
                continue
            if not self._is_allowed(t.name, tools_enabled):
                continue
            schema = dict(t.inputSchema)
            # lumi_session_id est un paramètre interne — on le masque au LLM
            properties = {k: v for k, v in schema.get("properties", {}).items() if k != "lumi_session_id"}
            required = [r for r in schema.get("required", []) if r != "lumi_session_id"]
            result.append({
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": {**schema, "properties": properties, "required": required},
                }
            })
        return result

    #Appelle un outil MCP.
    #tools_enabled : motifs `mcp.tools_enabled` du profil courant. Vérifié même si l'outil
    #n'a pas été proposé au LLM par tools_as_openai_format, pour ne pas se reposer uniquement
    #sur le fait que le LLM ne "voit" pas l'outil (ex. nom halluciné, ou disponible sur un autre profil).
    async def call_tool(self, name: str, arguments: dict, tools_enabled: list | None = None):
        if not self._is_allowed(name, tools_enabled):
            Logger.write(f"MCP tool {name} is not enabled for this profile", type=ERROR)
            raise MCPToolError(f"Tool '{name}' is not available")

        if name in self._external_sessions:
            # Outil d'un serveur MCP externe : l'authentification est statique (portée par le
            # service, cf. MCPExternalService), pas d'injection de lumi_session_id.
            external_session, real_name = self._external_sessions[name]
            result = await external_session.call_tool(real_name, arguments)
        else:
            # lumi_session_id est injecté ici pour que le wrapper de l'outil puisse
            # configurer l'auth de la bonne session sans passer par un état global.
            arguments = {**arguments, "lumi_session_id": AuthSessionManager.get_current_id() or ""}
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
