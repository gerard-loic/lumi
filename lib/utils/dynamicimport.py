import importlib
from lib.log.logger import Logger, ERROR

_AUTHORIZED_CLASS_PATH = [
    "lib.cron.tasks",
    "lib.agent.filters",
    "lib.agent.llmconnector",
    "lib.connectors.webex",
    "lib.pipelines.triggers",
    "lib.pipelines.blocks"
]

"""
DynamicImport — Gestion d'imports dynamiques
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class DynamicImport:
    @staticmethod
    def getInstance(className:str, moduleName:str, classPath:str, *args, **kwargs):
        #className = className.lower().capitalize()
        moduleName = moduleName.lower()

        if classPath not in _AUTHORIZED_CLASS_PATH:
            Logger.write(text=f"ClassPath {classPath} not authorized for dynamic instanciation !", type=ERROR)
            raise Exception(f"ClassPath {classPath} not authorized for dynamic instanciation !")
        try:
            module = importlib.import_module(f"{classPath}.{moduleName}")
            cls = getattr(module, className)
        except (ImportError, AttributeError):
            Logger.write(text=f"Class {className} not found for dynamic instanciation !", type=ERROR)
            raise Exception(f"Class {className} not found for dynamic instanciation !")
        return cls(*args, **kwargs)