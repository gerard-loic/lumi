from abc import ABC, abstractmethod

"""
Service — Classe parente de tout service
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Service(ABC):
    #name               str     Nom du service
    #data               dict    Données de configuration du service
    #serviceDataFormat  dict    Format attendu des données de configuration
    def __init__(self, name:str, data: dict, serviceDataFormat:dict):
        super().__init__()
        self.data = data
        self.name = name

        #Vérifie le format
        self._checkData(data=data, serviceDataFormat=serviceDataFormat)

    def getName(self)->str:
        return self.name

    #Retourne donnée de configuration du service
    def getConfValue(self, key:str):
        if key in self.data:
            return self.data[key]
        else:
            raise Exception(f"Config value {key} not found")

    #Authentifie un utilisateur auprès du service, à partir de la partie de la requête qui le concerne.
    #Renvoie le secret à conserver dans le wallet du process (ex: {"token": "..."}), ou False en cas d'échec.
    #Sans effet de bord : chaque service est une instance unique partagée par toutes les sessions
    #(cf. ServiceManager.services), l'authentification est donc portée par le process, pas par le service.
    #allow_credentials : autorise une connexion par identifiants (login/mot de passe). Réservé aux appelants de
    #confiance (config d'un pipeline) : côté HTTP (/auth), seul un token existant est accepté, pour que l'API ne
    #puisse pas servir de relais à une attaque par force brute sur les mots de passe.
    #Implémentation par défaut : service sans authentification par utilisateur (aucun secret).
    def authenticate(self, authorization:dict, allow_credentials:bool = False) -> dict | bool:
        return {}

    #Secret d'authentification du process courant pour ce service ({} si aucun), cf. Process.getWallet()
    def getAuth(self) -> dict:
        from lib.process.processmanager import ProcessManager
        process = ProcessManager.getCurrent()
        return process.getWallet().getSecret(self.name, default={}) if process else {}

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
