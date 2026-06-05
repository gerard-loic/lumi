import importlib
import importlib.util
import sys
import os
from lib.config.config import Config
from lib.log.logger import Logger, ERROR, OK, WARNING

_SERVICES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "services"
)


"""
Service — Classe parente de tout service

Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Service:
    #data               dict    Données de configuration du service
    #serviceDataFormat  dict    Format attendu des données de configuration
    def __init__(self, data: dict, serviceDataFormat:dict):
        self.data = data

        #Vérifie le format
        self._checkData(data=data, serviceDataFormat=serviceDataFormat)
        self.authenticated = False
        self.authData = {}

    #Retourne donnée de configuration du service
    def getConfValue(self, key:str):
        if key in self.data:
            return self.data[key]
        else:
            raise Exception(f"Config value {key} not found")
        
    #Réalise l'authentification au service
    def authenticate(self, data:dict={}):
        self.authenticated = True
        return True
    
    #Vérifie l'authentification
    def checkAuthentication(self, authorization:dict):
        return self.authenticated
    
    #Retourne les données d'authentification
    def getAuthentication(self):
        return self.authData
    
    #Définit les données d'authentification
    def setAuthentication(self, authorization:dict):
        self.authData = authorization

    def _checkData(self, data: dict, serviceDataFormat: dict, path: str = ""):
        data_keys = set(data.keys())
        format_keys = set(serviceDataFormat.keys())

        missing = format_keys - data_keys
        extra = data_keys - format_keys
        if missing or extra:
            location = f" at '{path}'" if path else ""
            parts = []
            if missing:
                parts.append(f"missing keys: {missing}")
            if extra:
                parts.append(f"unexpected keys: {extra}")
            raise ValueError(f"Data structure mismatch{location}: {', '.join(parts)}")

        for key in format_keys:
            if isinstance(serviceDataFormat[key], dict):
                if not isinstance(data[key], dict):
                    raise ValueError(f"Expected dict at '{path}.{key}' but got {type(data[key]).__name__}")
                self._checkData(data[key], serviceDataFormat[key], path=f"{path}.{key}" if path else key)


"""
ServiceManager — Gestionnaire de services

Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class ServiceManager:
    services: dict = {}

    @staticmethod
    def init(authorization:dict = None):
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
                ServiceManager.services[name] = cls(data)
                print(f"[ServiceManager] Service {name} initialized")
            except Exception as e:
                Logger.write(f"[ServiceManager] Handler '{handler}' failed for service '{name}' : {str(e)}", type=ERROR)

        #Gestion de l'authentification aux services
        if authorization:
            for name in authorization:
                if name in ServiceManager.services:
                    ServiceManager.services[name].setAuthentication(authorization=authorization[name])

        Logger.write("[ServiceManager] All services initialized !", type=OK)

    @staticmethod
    def setAuthorization(authorization: dict):
        for name, auth_data in authorization["services"].items():
            if name in ServiceManager.services and isinstance(auth_data, dict):
                ServiceManager.services[name].setAuthentication(authorization=auth_data)

    @staticmethod
    def get(name:str) -> Service:
        if name in ServiceManager.services:
            return ServiceManager.services[name]
        else:
            raise Exception(f"[ServiceManager] Service {name} does not exists")
    

    
