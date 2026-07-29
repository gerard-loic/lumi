from lib.config.config import Config
from lib.log.logger import Logger, OK, ERROR

class Profile:
    def __init__(self, name:str):
        self.name = name
        self.config = Config.get(f"profiles.{name}")
        Logger.write(f"[Profile] Profile {name} intialized", OK)

    def getConfigValue(self, key:str, default=None):
        value = self.config
        for part in key.split("."):
            if not isinstance(value, dict) or part not in value:
                return default
            value = value[part]
        return value

    def getName(self)->str:
        return self.name

class ProfileManager:
    @staticmethod
    def init():
        ProfileManager.profiles = {}
        for p in Config.get("profiles"):
            ProfileManager.profiles[p] = Profile(name=p)

    @staticmethod
    def getProfile(name:str):
        return ProfileManager.profiles[name]

    @staticmethod
    def profileExists(name:str)->bool:
        if name in ProfileManager.profiles:
            return True
        return False

    @staticmethod
    def getProfileNames()->list:
        return ProfileManager.profiles.keys()