import os
import inspect
import importlib.util
from mcp.server.fastmcp import FastMCP


def slow_tool(message: str = ""):
    """Décorateur signalant qu'un outil peut être lent à s'exécuter."""
    def decorator(func):
        func.__slow_tool__ = True
        func.__slow_tool_message__ = message
        return func
    return decorator


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
        new_sig = sig.replace(parameters=params_no_self, return_annotation=inspect.Parameter.empty)

        def wrapper(*args, **kwargs):
            instance = cls()
            result = method(instance, *args, **kwargs)
            return {"result": result, "events": instance._events}

        wrapper.__name__ = method.__name__
        wrapper.__qualname__ = method.__qualname__
        wrapper.__doc__ = method.__doc__
        wrapper.__module__ = method.__module__
        wrapper.__annotations__ = {k: v for k, v in method.__annotations__.items() if k not in ("self", "return")}
        wrapper.__signature__ = new_sig

        MCPTool._registry[method.__name__] = {
            "slow": getattr(method, "__slow_tool__", False),
            "slow_message": getattr(method, "__slow_tool_message__", ""),
        }

        return wrapper


"""
ToolLoader — chargement dynamique des tools MCP.

Parcourt le répertoire `tools/`, importe chaque module Python,
détecte les sous-classes de MCPService et enregistre leurs outils
auprès de l'instance FastMCP fournie.

Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class ToolLoader:

    @staticmethod
    def registerTools(app: FastMCP, toolsDir: str = None):
        if toolsDir is None:
            toolsDir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "tools"
            )

        for filename in sorted(os.listdir(toolsDir)):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            modulename = f"tools.{filename[:-3]}"
            filepath = os.path.join(toolsDir, filename)

            spec = importlib.util.spec_from_file_location(modulename, filepath)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            for _, cls in inspect.getmembers(module, inspect.isclass):
                if not issubclass(cls, MCPTool) or cls is MCPTool:
                    continue
                if cls.__module__ != modulename:
                    continue
                for tool_fn in cls.get_tools():
                    app.tool()(tool_fn)
