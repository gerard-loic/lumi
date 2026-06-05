from dotenv import dotenv_values
from pathlib import Path
import os
import json

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
    def get(key:str):
        if key in Config.conf:
            return Config.conf[key]
        raise Exception(f"Config {key} does not exist")

    @staticmethod
    def _loadConfFile(file_path:str):
        with open(file_path, encoding='utf-8') as f:
            Config.conf = json.load(f)


