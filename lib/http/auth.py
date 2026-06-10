import jwt
import threading
from datetime import datetime, timezone, timedelta
from lib.mcp.services import ServiceManager, Service
from lib.config.config import Config
import sys
import secrets
from lib.log.logger import Logger, ERROR
"""
Auth — Gestion de l'authentification sur l'agent
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Auth:
    _local = threading.local()

    """
    S'authentifier sur l'agent
    """
    @staticmethod
    def authenticate(authorization: dict):
        #On récupère le service utilisé pour gérer l'authentification
        auth_service = ServiceManager.get(name=Config.get(key="authentication_service"))
        result = auth_service.checkAuthentication(authorization=authorization)
        if result:
            #On authentifie tous les services
            payload = {
                "session_id" : secrets.token_hex(16),   #ID de session de la conversation
                "services" : {}
            }
            for name in ServiceManager.services:
                service = ServiceManager.services[name]
                authenticated = service.checkAuthentication(authorization=authorization)
                if not authenticated:
                    service.authenticate()
                if authenticated:
                    payload["services"][name] = service.getAuthentication()

            token = Auth._create_token(payload=payload)
            Auth._local.sessionId = payload["session_id"]

            AuthSessionManager.add(payload["session_id"], payload["exp"].timestamp(), payload)

            #Le token comprend toutes les couches d'authentification aux services
            return token
        return False

    """
    Vérifie un token d'authentification et le renvoie décodé
    """
    @staticmethod
    def checkAuthentification(token:str) -> bool | dict:
        try:
            decoded = Auth._verify_token(token=token)
            session = AuthSessionManager.get(decoded["session_id"])
            if session is None:
                return False
            Auth._local.sessionId = decoded["session_id"]
            return session.authentication
        except Exception:
            return False

    """
    Retourne l'ID de session courant
    """
    @staticmethod
    def getSessionId() -> str:
        return getattr(Auth._local, 'sessionId', None)

    """
    Retourne le payload du token d'authentification courant
    """
    @staticmethod
    def getAuthentication() -> dict:
        session = AuthSessionManager.get(Auth.getSessionId())
        return session.authentication if session else None

    @staticmethod
    def _create_token(payload: dict, expires_in: int = 3600) -> str:
        secret = Config.get(key="jwt_secret")
        algorithm = Config.get(key="jwt_algorithm")

        payload["iat"] = datetime.now(tz=timezone.utc)
        payload["exp"] = datetime.now(tz=timezone.utc) + timedelta(seconds=expires_in)

        return jwt.encode(payload, secret, algorithm=algorithm)

    @staticmethod
    def _verify_token(token: str) -> dict:
        secret = Config.get(key="jwt_secret")
        algorithm = Config.get(key="jwt_algorithm")

        try:
            return jwt.decode(token, secret, algorithms=[algorithm])
        except jwt.ExpiredSignatureError:
            raise Exception("Token expiré")
        except jwt.InvalidTokenError as e:
            raise Exception(f"Token invalide : {e}")


"""
Auth — Gestion de l'authentification sur les routes d'administration
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class AdminAuth:
    @staticmethod
    def checkAdminCredentials(username: str, password: str) -> bool:
        users = Config.get("ADMIN_AUTHORIZED_USERS")
        for user in users:
            u_ok = secrets.compare_digest(username.encode(), user["username"].encode())
            p_ok = secrets.compare_digest(password.encode(), user["password"].encode())
            if u_ok and p_ok:
                return True
        Logger.write(f"[HTTP] [401] rag — Unauthorized access attempt for user '{username}'", type=ERROR)
        return False


class AuthSession:
    def __init__(self, session_id:str, expires_at:int, authentication:dict):
        self.session_id = session_id
        self.expires_at = expires_at
        self.authentication = authentication
        self.files = []

    def clear(self):
        from lib.files.filestore import FileStore
        for file in self.files:
            FileStore.delete(key=file)

    def addFile(self, key:str):
        self.files.append(key)


class AuthSessionManager:
    _sessions = []

    @staticmethod
    def add(session_id:str, expires_at:int, authentication:dict):
        AuthSessionManager._sessions.append(AuthSession(session_id=session_id, expires_at=expires_at, authentication=authentication))

    @staticmethod
    def get(session_id:str) -> 'AuthSession | None':
        for session in AuthSessionManager._sessions:
            if session.session_id == session_id:
                return session
        return None

    @staticmethod
    def count() -> int:
        return len(AuthSessionManager._sessions)

    @staticmethod
    def clear(all:bool=False):
        current_ts = datetime.now(tz=timezone.utc).timestamp()
        remaining = []
        for session in AuthSessionManager._sessions:
            if all or session.expires_at < current_ts:
                session.clear()
            else:
                remaining.append(session)
        AuthSessionManager._sessions = remaining
