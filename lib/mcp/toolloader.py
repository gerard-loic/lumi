import os
import fnmatch
import inspect
import importlib.util
from mcp.server.fastmcp import FastMCP
from lib.config.config import Config

def slow_tool(func=None):
    """Décorateur signalant qu'un outil peut être lent à s'exécuter."""
    def decorator(f):
        f.__slow_tool__ = True
        return f
    if func is not None:
        return decorator(func)
    return decorator

def tool_description(name:str):
    """Décorateur permettant de retourner un descriptif de l'outil appelé"""
    def decorator(f):
        f.__tool_description__ = name
        return f
    return decorator

def confirmation_tool(question:str, options:list, validation_option:int):
    """Décorateur permettant à l'outil de demander une confirmation avec execution"""
    def decorator(f):
        f.__tool_confirmation__ = True
        f.__tool_confirmation_question__ = question
        f.__tool_confirmation_options__ = options
        f.__tool_confirmation_validation_option__ = validation_option
        return f
    return decorator

def restricted_tool(func=None):
    """Décorateur signalant qu'un outil n'est pas disponible pour les agents non-chatbot"""
    def decorator(f):
        f.__restricted_tool__ = True
        return f
    if func is not None:
        return decorator(func)
    return decorator

def _inject_session_auth(session_id: str) -> None:
    """Définit l'auth et la session courante pour l'exécution d'un outil."""
    if not session_id:
        return
    from lib.session.session import AuthSessionManager
    from lib.services.services import ServiceManager
    from lib.http.auth import Auth
    session = AuthSessionManager.get(session_id)
    if session:
        ServiceManager.setAuthorization(authorization=session.authentication)
        Auth._session_id_var.set(session_id)


"""
MCPTool — classe parente outil MCP
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class MCPTool:
    name: str = ""
    description: str = ""
    _registry: dict = {}

    def __init__(self):
        self._events: list = []

    def emit(self, event) -> None:
        self._events.append(event)

    @classmethod
    def get_meta(cls, tool_name: str) -> dict:
        return cls._registry.get(tool_name, {})

    @classmethod
    def get_tools(cls) -> list:
        base_attrs = set(vars(MCPTool))
        tools = []
        for attr_name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
            if attr_name.startswith("_") or attr_name in base_attrs:
                continue
            tools.append(cls._wrap_method(method))
        return tools

    @classmethod
    def _wrap_method(cls, method):
        sig = inspect.signature(method)
        params_no_self = [p for p in sig.parameters.values() if p.name != "self"]

        # lumi_session_id est injecté par call_tool à chaque appel ; il est filtré
        # du schéma exposé au LLM dans tools_as_openai_format.
        _session_param = inspect.Parameter(
            "lumi_session_id",
            kind=inspect.Parameter.KEYWORD_ONLY,
            default="",
            annotation=str,
        )
        new_sig = sig.replace(
            parameters=params_no_self + [_session_param],
            return_annotation=inspect.Parameter.empty,
        )

        if inspect.iscoroutinefunction(method):
            async def wrapper(*args, **kwargs):
                _inject_session_auth(kwargs.pop("lumi_session_id", ""))
                instance = cls()
                result = await method(instance, *args, **kwargs)
                return {"result": result, "events": instance._events}
        else:
            def wrapper(*args, **kwargs):
                _inject_session_auth(kwargs.pop("lumi_session_id", ""))
                instance = cls()
                result = method(instance, *args, **kwargs)
                return {"result": result, "events": instance._events}

        wrapper.__name__ = method.__name__
        wrapper.__qualname__ = method.__qualname__
        wrapper.__doc__ = method.__doc__
        wrapper.__module__ = method.__module__
        wrapper.__annotations__ = {k: v for k, v in method.__annotations__.items() if k not in ("self", "return")}
        wrapper.__annotations__["lumi_session_id"] = str
        wrapper.__signature__ = new_sig

        MCPTool._registry[method.__name__] = {
            "slow": getattr(method, "__slow_tool__", False),
            "restricted" : getattr(method, "__restricted_tool__", False),
            "description": getattr(method, "__tool_description__", False),
            "confirmation" : getattr(method, "__tool_confirmation__", False),
            "confirmation_question" : getattr(method, "__tool_confirmation_question__", False),
            "confirmation_options" : getattr(method, "__tool_confirmation_options__", False),
            "confirmation_validation_option" : getattr(method, "__tool_confirmation_validation_option__", False)
        }

        return wrapper


"""
ToolLoader — chargement dynamique des tools MCP.

Parcourt récursivement le répertoire `tools/` (les outils peuvent être
regroupés dans des sous-dossiers, ex. `tools/word/`), importe chaque
module Python, détecte les sous-classes de MCPService et enregistre
leurs outils auprès de l'instance FastMCP fournie. Le répertoire
`directories.custom_mcp_tools_dir` (s'il existe) est ensuite parcouru
de la même façon, pour permettre l'ajout d'outils supplémentaires sans
toucher à `tools/`.

Les fichiers et dossiers dont le nom commence par `_` (modules internes,
`__pycache__`) sont ignorés : un fichier de ce type n'est jamais exposé
comme outil mais reste importable par les autres modules du sous-dossier
via un import Python classique (ex. `tools.word._word_common`).

`profiles.<profil>.mcp.tools_enabled` contrôle quels outils sont exposés : elle
accepte des noms d'outils exacts, ainsi que des motifs "namespace.*" comparés au
chemin du module relatif à `tools.` (ex. `tools.word.word` -> "word.word") :
"word.*" active ainsi tous les outils situés dans `tools/word/`, et
"datetime.*" active tous les outils du module `tools/datetime.py`, quel que
soit leur nombre. Elle accepte aussi un motif "namespace/nom_outil" pour
n'activer qu'un seul outil précis d'un sous-dossier ou module, ex.
"pdf/generer_fichier_pdf" n'active que cet outil parmi ceux de `tools/pdf/`.
Un outil non couvert par la liste d'AUCUN profil n'est pas enregistré sur le
serveur MCP (celui-ci est unique et partagé : `registerTools` enregistre
l'union des `tools_enabled` de tous les profils). Le filtrage effectif par
profil — quels outils un profil donné voit et peut appeler — se fait ensuite
côté `MCPClientManager` (`lib/mcp/client.py`), à partir du même motif.

Les outils servis par un serveur MCP externe (cf. `MCPExternalService`,
`lib/services/mcpexternalservice.py`) ne passent pas par ce loader : ils sont
récupérés à l'exécution via `list_tools()` sur la session distante, par
`MCPClientManager._connect_external_servers`. Ils suivent néanmoins la même
convention de motifs, sous le namespace réservé "ext.<nom_du_service>" (le nom
d'outil exposé au LLM est préfixé "ext__<nom_du_service>__<outil>") : ex.
"ext.mon_serveur.*" active tous les outils de ce serveur externe.

Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class ToolLoader:

    @staticmethod
    def is_enabled(tool_name: str, namespace: str, enabled_tools: list) -> bool:
        # `namespace` est le chemin du module relatif à `tools.` (ex. "tools.word.word" -> "word.word"),
        # utilisé par les motifs "namespace.*" désignant tout un sous-dossier ou module.
        relative_module = namespace
        for pattern in enabled_tools:
            if pattern == tool_name:
                return True
            if pattern.endswith(".*"):
                prefix = pattern[:-2]
                if relative_module == prefix or relative_module.startswith(prefix + "."):
                    return True
            elif "/" in pattern:
                pattern_namespace, _, name = pattern.rpartition("/")
                if name == tool_name and (relative_module == pattern_namespace or relative_module.startswith(pattern_namespace + ".")):
                    return True
            elif ("*" in pattern or "?" in pattern) and fnmatch.fnmatch(relative_module, pattern):
                return True
        return False

    @staticmethod
    def _enabled_tools_union() -> list:
        """Union des `mcp.tools_enabled` de tous les profils : le serveur MCP est
        unique et partagé, il doit donc exposer tout ce dont un profil au moins a besoin.
        Le filtrage effectif par profil se fait ensuite côté MCPClientManager/LiteLLM."""
        enabled = []
        for profile_config in Config.get("profiles").values():
            enabled.extend(profile_config.get("mcp", {}).get("tools_enabled", []))
        return enabled

    @staticmethod
    def registerTools(app: FastMCP, toolsDir: str = None):
        toolsDir = "lib/mcp/tools"

        enabled_tools = ToolLoader._enabled_tools_union()

        ToolLoader._registerToolsFromDir(app, toolsDir, enabled_tools)

        customToolsDir = Config.get("directories.custom_mcp_tools_dir", default=None)
        if customToolsDir and os.path.isdir(customToolsDir):
            ToolLoader._registerToolsFromDir(app, customToolsDir, enabled_tools)

    @staticmethod
    def _registerToolsFromDir(app: FastMCP, toolsDir: str, enabled_tools: list):
        for dirpath, dirnames, filenames in os.walk(toolsDir):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("_") and not d.startswith("."))
            package_parts = os.path.relpath(dirpath, toolsDir).split(os.sep) if dirpath != toolsDir else []

            for filename in sorted(filenames):
                if not filename.endswith(".py") or filename.startswith("_"):
                    continue

                modulename = ".".join(["tools", *package_parts, filename[:-3]])
                filepath = os.path.join(dirpath, filename)

                spec = importlib.util.spec_from_file_location(modulename, filepath)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                for _, cls in inspect.getmembers(module, inspect.isclass):
                    if not issubclass(cls, MCPTool) or cls is MCPTool:
                        continue
                    if cls.__module__ != modulename:
                        continue
                    namespace = modulename.removeprefix("tools.")
                    for tool_fn in cls.get_tools():
                        if not ToolLoader.is_enabled(tool_fn.__name__, namespace, enabled_tools):
                            continue
                        MCPTool._registry[tool_fn.__name__]["namespace"] = namespace
                        app.tool()(tool_fn)
