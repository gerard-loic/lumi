from lib.config.config import Config
from lib.log.logger import Logger, OK


"""
Profile : gère un profil de configuration d'un agent défini dans la configuration
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Profile:
    def __init__(self, name:str):
        self.name = name
        self.config = Config.get(f"profiles.{name}")
        Logger.write(f"[Profile] Profile {name} intialized", OK)

    #Retourne une valeur de configuration d'un profil
    def getConfigValue(self, key:str, default=None):
        value = self.config
        for part in key.split("."):
            if not isinstance(value, dict) or part not in value:
                return default
            value = value[part]
        return value

    #Retourne le nom du profile
    def getName(self)->str:
        return self.name


"""
ProfileManager : gère la gestion des profils de configuration d'agents
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class ProfileManager:
    @staticmethod
    def init():
        ProfileManager.profiles = {}
        for p in Config.get("profiles"):
            ProfileManager.profiles[p] = Profile(name=p)
            #La collection RAG du profil doit être déclarée dans rag.collections (lève une exception sinon)
            collection = ProfileManager.profiles[p].getConfigValue("rag.collection")
            if collection is not None:
                from lib.rag.collection import RagCollection
                RagCollection.get(collection)

    #Retourne un profile en fonction de son nom
    @staticmethod
    def getProfile(name:str):
        return ProfileManager.profiles[name]

    #Retourne si un profil existe
    @staticmethod
    def profileExists(name:str)->bool:
        if name in ProfileManager.profiles:
            return True
        return False

    #Retourne la liste de tous les profiles existant
    @staticmethod
    def getProfileNames()->list:
        return ProfileManager.profiles.keys()