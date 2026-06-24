import asyncio
import secrets
from datetime import datetime, timezone
"""
AuthSession — Session d'authentification
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class AuthSession:
    def __init__(self, session_id: str, expires_at: int, authentication: dict, auth_fingerprint: str = "", token_hash: str = ""):
        self.session_id      = session_id
        self.expires_at      = expires_at
        self.authentication  = authentication
        self.auth_fingerprint = auth_fingerprint
        self.token_hash      = token_hash if token_hash else secrets.token_hex(32)
        self.files:   list[str]   = []
        self.history: list[dict]  = []
        self.ws_connected: bool   = False
        self.flood_timestamps: list[float] = []

    #Supprimer les ressources associées à la session
    def clear(self):
        from lib.files.filestore import FileStore
        for file in self.files:
            FileStore.delete(key=file)

    #Ajouter une ressource à la session
    def addFile(self, key: str):
        self.files.append(key)

"""
AuthSessionManager — Gestionnaire de sessions d'authentification
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class AuthSessionManager:
    _sessions: list['AuthSession'] = []
    _confirmation_queues: dict[str, asyncio.Queue] = {}

    #Ajout d'une session
    @staticmethod
    def add(session_id: str, expires_at: int, authentication: dict, auth_fingerprint: str = "", token_hash: str = ""):
        AuthSessionManager._sessions.append(
            AuthSession(session_id=session_id, expires_at=expires_at, authentication=authentication, auth_fingerprint=auth_fingerprint, token_hash=token_hash)
        )

    #Récupération d'une session en fonction de sa signature
    @staticmethod
    def get_by_token_hash(token_hash: str) -> 'AuthSession | None':
        for session in AuthSessionManager._sessions:
            if session.token_hash == token_hash:
                return session
        return None

    #permet de savoir si une connexion WS est active pour la session
    @staticmethod
    def has_active_ws_for(auth_fingerprint: str) -> bool:
        for session in AuthSessionManager._sessions:
            if session.auth_fingerprint == auth_fingerprint and session.ws_connected:
                return True
        return False

    #Obtenir une session à partir de son id
    @staticmethod
    def get(session_id: str) -> 'AuthSession | None':
        current_ts = datetime.now(tz=timezone.utc).timestamp()
        for session in AuthSessionManager._sessions:
            if session.session_id == session_id:
                return session if session.expires_at > current_ts else None
        return None

    #Obtenir l'historique des message
    @staticmethod
    def get_history(session_id: str | None) -> list[dict]:
        if not session_id:
            return []
        session = AuthSessionManager.get(session_id)
        return session.history if session else []

    #Sauvegarder l'historique des messages dans la session
    @staticmethod
    def save_history(session_id: str | None, history: list[dict]) -> None:
        if not session_id:
            return
        session = AuthSessionManager.get(session_id)
        if session:
            session.history = history

    #Obtenir le nombre de sessions ouvertes
    @staticmethod
    def count() -> int:
        return len(AuthSessionManager._sessions)

    #Gestion des sessions en attente de confirmation
    @staticmethod
    async def wait_confirmation(session_id: str, timeout: int = 120) -> int:
        queue = asyncio.Queue(maxsize=1)
        AuthSessionManager._confirmation_queues[session_id] = queue
        try:
            return await asyncio.wait_for(queue.get(), timeout=timeout)
        finally:
            AuthSessionManager._confirmation_queues.pop(session_id, None)

    #Résolution d'une confirmation en attente
    @staticmethod
    def resolve_confirmation(session_id: str, option: int) -> bool:
        queue = AuthSessionManager._confirmation_queues.get(session_id)
        if not queue:
            return False
        queue.put_nowait(option)
        return True

    #Réserve un slot WS pour la session (retourne FALSE si ça n'est pas possible)
    @staticmethod
    def claim_ws(session_id: str) -> bool:
        session = AuthSessionManager.get(session_id)
        if not session or session.ws_connected:
            return False
        session.ws_connected = True
        return True

    #Libère le slot WS pour la session d'authentification
    @staticmethod
    def release_ws(session_id: str) -> None:
        session = AuthSessionManager.get(session_id)
        if session:
            session.ws_connected = False

    #Supprime une session
    @staticmethod
    def remove(session_id: str) -> bool:
        for i, session in enumerate(AuthSessionManager._sessions):
            if session.session_id == session_id:
                session.clear()
                AuthSessionManager._sessions.pop(i)
                return True
        return False

    #Supprime les sessions expirées
    @staticmethod
    def clear(all: bool = False):
        current_ts = datetime.now(tz=timezone.utc).timestamp()
        remaining = []
        for session in AuthSessionManager._sessions:
            if all or session.expires_at < current_ts:
                session.clear()
            else:
                remaining.append(session)
        AuthSessionManager._sessions = remaining
