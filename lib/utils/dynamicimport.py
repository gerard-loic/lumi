import importlib
from lib.config.config import Config
from lib.log.logger import Logger, ERROR

_AUTHORIZED_CLASS_PATH = [
    "lib.cron.tasks"
]

class DynamicImport:
    @staticmethod
    def getInstance(className:str, moduleName:str, classPath:str, *args, **kwargs):
        className = className.lower().capitalize()

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