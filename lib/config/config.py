from dotenv import dotenv_values
from pathlib import Path
import os
import json

_MISSING = object()

"""
Config — Gestion des fichiers de configuration
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Config:
    @staticmethod
    def init():
        Config.conf = {}
        Config._loadConfFile(file_path="config/config.json")

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

    @staticmethod
    def _loadConfFile(file_path:str):
        with open(file_path, encoding='utf-8') as f:
            Config.conf = json.load(f)


class StaticConfig:
    @staticmethod
    def version():
        return "1.1.2"
    
    @staticmethod
    def versionName():
        return "Sense"