import time
import secrets
from typing import TYPE_CHECKING
from lib.process.wallet import Wallet

if TYPE_CHECKING:
    from lib.process.agentcontext import AgentContext

#Origine d'un process racine. Seules les sessions KIND_HTTP (ouvertes par POST /auth) sont accessibles
#via un token de session HTTP (cf. Auth.checkAuthentification) : les autres ont des identifiants
#prévisibles ou exposés (ex: "webex_<person_id>", id de run de pipeline) et ne doivent pas pouvoir être ciblées.
KIND_HTTP     = "http"
KIND_WEBEX    = "webex"
KIND_PIPELINE = "pipeline"
KIND_INTERNAL = "internal"

"""
Process — État d'une exécution, organisé en arbre
  - racine : session (HTTP/Webex, durée de vie du JWT) ou run de pipeline. Porte les ressources partagées :
    wallet (authentification aux services), token de signature des URLs, fichiers, connexion WS, expiration.
  - enfant : exécution ponctuelle rattachée à une racine (tour de conversation, reflect() d'un bloc Agent).
    Les ressources partagées sont lues sur la racine ; l'AgentContext est cherché en remontant l'arbre.
Instancié et enregistré par ProcessManager (cf. lib/process/processmanager.py)
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Process:
    def __init__(self, process_id: str, parent: "Process | None" = None, expires_at: float | None = None, fingerprint: str = "", kind: str = KIND_INTERNAL):
        self._process_id = process_id                   # Identifiant unique du process (= session_id du JWT pour une session)
        self._parent = parent
        self._children: dict[str, Process] = {}
        self._agent: "AgentContext | None" = None

        #Ressources partagées, portées uniquement par la racine
        self._kind = kind if parent is None else None                  # Origine du process (cf. KIND_*)
        self._expires_at = expires_at if parent is None else None      # Timestamp d'expiration (None : pas d'expiration)
        self._fingerprint = fingerprint if parent is None else ""      # Empreinte de la source d'authentification (ex: "webex_<person_id>")
        self._wallet = Wallet() if parent is None else None
        self._token = secrets.token_hex(32) if parent is None else None  # Signature des URLs (ex: accès fichiers)
        self._files: dict[str, str] = {}                # Fichiers FileStore rattachés (clé -> nom), supprimés à la fermeture
        self._connected = False                         # Un client WebSocket est connecté

        if parent is not None:
            parent._children[process_id] = self

    def getUid(self) -> str:
        return self._process_id

    def getParent(self) -> "Process | None":
        return self._parent

    def getRoot(self) -> "Process":
        return self._parent.getRoot() if self._parent else self

    def getChildren(self) -> list["Process"]:
        return list(self._children.values())

    def getKind(self) -> str:
        return self.getRoot()._kind

    def isExpired(self) -> bool:
        root = self.getRoot()
        return root._expires_at is not None and root._expires_at <= time.time()

    #Timestamp d'expiration de la racine (None : pas d'expiration)
    def getExpiresAt(self) -> float | None:
        return self.getRoot()._expires_at

    def getFingerprint(self) -> str:
        return self.getRoot()._fingerprint

    def getWallet(self) -> Wallet:
        return self.getRoot()._wallet

    def getToken(self) -> str:
        return self.getRoot()._token

    #Contexte agent : on remonte jusqu'au premier ancêtre qui en porte un
    def getAgentContext(self) -> "AgentContext | None":
        if self._agent is not None:
            return self._agent
        return self._parent.getAgentContext() if self._parent else None

    def setAgentContext(self, agent: "AgentContext") -> None:
        self._agent = agent

    #Fichiers : rattachés à la racine, pour rester accessibles après la fin du tour (ou du bloc) qui les a produits
    def addFile(self, key: str, filename: str = "") -> None:
        self.getRoot()._files[key] = filename

    def hasFile(self, key: str) -> bool:
        return key in self.getRoot()._files

    #Fichiers rattachés : [{"key", "filename"}, ...] dans l'ordre d'ajout
    def getFiles(self) -> list[dict]:
        return [{"key": key, "filename": filename} for key, filename in list(self.getRoot()._files.items())]

    #Connexion WebSocket (une seule par session)
    def claimCnx(self) -> bool:
        root = self.getRoot()
        if root._connected:
            return False
        root._connected = True
        return True

    def releaseCnx(self) -> None:
        self.getRoot()._connected = False

    def isConnected(self) -> bool:
        return self.getRoot()._connected

    #Libère les ressources du process. Les enfants sont fermés par ProcessManager.remove() avant l'appel.
    def close(self) -> None:
        if self._parent is not None:
            self._parent._children.pop(self._process_id, None)
            return
        from lib.files.filestore import FileStore
        for key in list(self._files):
            FileStore.delete(key=key)
        self._files = {}
