import asyncio
import secrets
from datetime import datetime, timezone
from lib.localization.language import Language

"""
AuthSession — Session d'authentification
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class AuthSession:
    def __init__(self, session_id: str, expires_at: int, authentication: dict, auth_fingerprint: str = "", token_hash: str = "", profile: str = "default", language: Language = None):
        self.session_id      = session_id                              # Identifiant unique de la session
        self.expires_at      = expires_at                              # Timestamp d'expiration de la session
        self.authentication  = authentication                          # Payload d'authentification (infos utilisateur/connecteur)
        self.auth_fingerprint = auth_fingerprint                       # Empreinte identifiant la source d'authentification (ex: "webex_<person_id>")
        self.token_hash      = token_hash if token_hash else secrets.token_hex(32)  # Signature de l'authentification. utilisé pour les URLs signées (ex: accès fichiers)
        self.files:   list[str]   = []                                 # Clés des fichiers stockés (FileStore) à nettoyer lors de clear()
        self.history: list[dict]  = []                                 # Historique de la conversation
        self.ws_connected: bool   = False                              # Indique si un client WebSocket est actuellement connecté à la session
        self.flood_timestamps: list[float] = []                        # Horodatages des derniers appels LLM, utilisés pour le rate-limiting (voir llmlimiter.py)
        self.attachments: dict[str, dict] = {}                         # Pièces jointes conversationnelles (texte extrait, tokens, chunks RAG), indexées par clé
        self.profile = profile                                         # Profil de configuration LLM
        self.language = language                                       # Language appliqué

    #Supprimer les ressources associées à la session
    def clear(self):
        from lib.files.filestore import FileStore
        for file in self.files:
            FileStore.delete(key=file)

    #Ajouter une ressource à la session
    def addFile(self, key: str):
        self.files.append(key)

    def getProfile(self)->str:
        return self.profile

    def getLanguage(self)->Language:
        return self.language

    #Ajouter une pièce jointe conversationnelle (texte déjà extrait) à la session
    #`pages` : list[tuple[int,str]] pour un PDF (texte par page), None si le format n'a pas de pagination.
    #`chunks` est rempli paresseusement au premier passage en micro-RAG (cache des embeddings pour la session)
    def addAttachment(self, key: str, filename: str, text: str, tokens: int, pages: list | None = None):
        self.attachments[key] = {"key": key, "filename": filename, "text": text, "tokens": tokens, "chunks": None, "pages": pages}

"""
AuthSessionManager — Gestionnaire de sessions d'authentification
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class AuthSessionManager:
    _sessions: list['AuthSession'] = []
    _confirmation_queues: dict[str, asyncio.Queue] = {}

    #Ajout d'une session
    @staticmethod
    def add(session_id: str, expires_at: int, authentication: dict, auth_fingerprint: str = "", token_hash: str = "", profile: str = "default", language: Language = None):
        AuthSessionManager._sessions.append(
            AuthSession(session_id=session_id, expires_at=expires_at, authentication=authentication, auth_fingerprint=auth_fingerprint, token_hash=token_hash, profile=profile, language=language)
        )

    #Recupération d'une session par son ID
    @staticmethod
    def get_by_session_id(session_id:str) -> 'AuthSession | None':
        for session in AuthSessionManager._sessions:
            if session.session_id == session_id:
                return session
        return None

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

    #Obtenir toutes les pièces jointes de la session (utilisé par le tool MCP search_attached_files)
    @staticmethod
    def get_all_attachments(session_id: str | None) -> list[dict]:
        session = AuthSessionManager.get(session_id) if session_id else None
        return list(session.attachments.values()) if session else []

    #Obtenir la langue utilisée par la session
    def get_language(session_id: str | None) -> dict:
        session = AuthSessionManager.get(session_id) if session_id else None
        return session.language

    #Obtenir le profil de configuration associé à une session
    @staticmethod
    def get_profile(session_id: str | None):
        from lib.agent.profile import ProfileManager
        session = AuthSessionManager.get(session_id) if session_id else None
        return ProfileManager.getProfile(session.getProfile()) if session else None

    #Met en cache les chunks/embeddings calculés pour une pièce jointe (évite de les recalculer aux tours suivants)
    @staticmethod
    def cache_attachment_chunks(session_id: str | None, key: str, chunks: list[dict]) -> None:
        session = AuthSessionManager.get(session_id) if session_id else None
        if session and key in session.attachments:
            session.attachments[key]["chunks"] = chunks

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
