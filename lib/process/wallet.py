from lib.services.servicemanager import ServiceManager

"""
Wallet — Authentifications aux services portées par un process racine (cf. Process.getWallet)
Les services lisent le secret du process courant via Service.getAuth().
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Wallet:
    def __init__(self):
        self._secrets: dict[str, dict] = {}     # Nom du service -> secret (ex: {"token": "..."})

    def store(self, key:str, secret:dict):
        self._secrets[key] = secret

    #Authentifie le process auprès d'un service (cf. Service.authenticate, dont allow_credentials) et conserve le secret obtenu
    def authenticateAndStore(self, service:str, authorization:dict, allow_credentials:bool = False)->bool:
        s = ServiceManager.get(name=service)
        secret = s.authenticate(authorization=authorization, allow_credentials=allow_credentials)
        if isinstance(secret, dict):
            self.store(key=service, secret=secret)
            return True
        return False

    def getSecret(self, key:str, default=None):
        return self._secrets.get(key, default)
