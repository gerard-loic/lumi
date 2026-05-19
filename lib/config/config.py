from dotenv import dotenv_values
from pathlib import Path
import os
import json

class Config:
    @staticmethod
    def init():
        Config.conf = {}
        Config._loadConfFile(file_path=".env", type="env")
        Config._loadConfFile(file_path="../../../.env", type="env")
        Config._loadConfFile(file_path="config/crud.json", type="crud")

    @staticmethod
    def get(type:str, key:str=None):
        if key is None:
            return Config.conf[type]
        else:
            return Config.conf[type][key]

    @staticmethod
    def getArray(type:str, key:str=None):
        return Config.get(type, key).split(",")

    @staticmethod
    def _loadConfFile(file_path:str, type:str):
        fp = Path(file_path)
        format = fp.suffix
        print(format)
        if format == '':
            if type not in Config.conf:
                Config.conf[type] = {}
            Config.conf[type].update(dotenv_values(dotenv_path=fp))
        elif format == '.json':
            with open(file_path) as f:
                Config.conf[type] = json.load(f)


