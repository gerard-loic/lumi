import importlib
import importlib.util
import os
from lib.config.config import Config
from lib.log.logger import Logger, ERROR, OK, WARNING
from lib.services._abstract import Service

_SERVICES_DIR = 'lib/services/'


"""
ServiceManager — Gestionnaire de services
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class ServiceManager:
    services: dict = {}

    @staticmethod
    def init():
        Logger.write("[ServiceManager] services initialization...", type=WARNING)

        services_config = Config.get(key="services")
        for name, config in services_config.items():
            #Initialisation des services
            handler = config.get("handler")
            data = {k: v for k, v in config.items() if k != "handler"}
            module_name = f"services.{handler.lower()}"
            filepath = os.path.join(_SERVICES_DIR, f"{handler.lower()}.py")
            try:
                spec = importlib.util.spec_from_file_location(module_name, filepath)
                if spec is None:
                    raise ImportError(f"File not found: {filepath}")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                cls = getattr(module, handler)
                ServiceManager.services[name] = cls(name, data)
                print(f"[ServiceManager] Service {name} initialized")
            except Exception as e:
                filepath = os.path.join(Config.get("directories.custom_services_dir"), f"{handler.lower()}.py")
                try:
                    spec = importlib.util.spec_from_file_location(module_name, filepath)
                    if spec is None:
                        raise ImportError(f"File not found: {filepath}")
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    cls = getattr(module, handler)
                    ServiceManager.services[name] = cls(name, data)
                    print(f"[ServiceManager] Service {name} initialized")
                except Exception as e:
                                    
                    Logger.write(f"[ServiceManager] Handler '{handler}' failed for service '{name}' : {str(e)}", type=ERROR)

        Logger.write("[ServiceManager] All services initialized !", type=OK)

    @staticmethod
    def get(name:str) -> Service:
        if name in ServiceManager.services:
            return ServiceManager.services[name]
        else:
            raise Exception(f"[ServiceManager] Service {name} does not exists")
    

    
