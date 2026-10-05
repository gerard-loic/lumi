import json
from lib.utils.configfilechecker import ConfigFileChecker

_MISSING = object()

"""
Config — Gestion des fichiers de configuration
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Config:
    @staticmethod
    def init():
        Config.conf = {}
        Config._loadConfFile(file_path="config/config.json", jsonformat_path="lib/_references/config.schema.json")

    #Récupération d'une clé de configuration (peut être une clé composée ex. cle.souscle)
    @staticmethod
    def get(key: str, default=_MISSING):
        node = Config.conf
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                if default is not _MISSING:
                    return default
                raise Exception(f"Config {key} does not exist")
            node = node[part]
        return node

    #Chargement fichier de configuration
    @staticmethod
    def _loadConfFile(file_path:str, jsonformat_path:str = None):
        with open(file_path, encoding='utf-8') as f:
            v = json.load(f)
            if jsonformat_path:
                cfc = ConfigFileChecker(schemaPath=jsonformat_path)
                if not cfc.check(data=v):
                    raise Exception(f"Config file {file_path} does not match the requested JSON schema {jsonformat_path}")
            Config.conf = v


"""
StaticConfig — Gestion de la configuration statique
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class StaticConfig:
    @staticmethod
    def version():
        return "1.6.2"
    
    @staticmethod
    def versionName():
        return "Abyss"