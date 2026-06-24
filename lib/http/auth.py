import jwt
import json
import hashlib
import contextvars
from datetime import datetime, timezone, timedelta
from lib.mcp.services import ServiceManager, Service
from lib.config.config import Config
import sys
import secrets
from lib.log.logger import Logger, ERROR, WARNING
from lib.session.session import AuthSession, AuthSessionManager
"""
Auth — Gestion de l'authentification sur l'agent
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Auth:
    #Clé spécifique par session (isolée par contexte)
    _session_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar('session_id', default=None)


    #S'authentifier sur l'agent
    @staticmethod
    def authenticate(authorization: dict):
        #On récupère le service utilisé pour gérer l'authentification
        auth_service = ServiceManager.get(name=Config.get(key="authentication.service"))
        result = auth_service.checkAuthentication(authorization=authorization)
        if result:
            fingerprint = hashlib.sha256(
                json.dumps(authorization, sort_keys=True).encode()
            ).hexdigest()

            if AuthSessionManager.has_active_ws_for(fingerprint):
                Logger.write("[AUTH] Authentification refusée : une session WebSocket est déjà ouverte pour cet utilisateur", type=WARNING)
                return None

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

            token = Auth._create_token(payload=payload, expires_in=Config.get("authentication.session_duration"))
            Auth._session_id_var.set(payload["session_id"])

            token_hash = hashlib.sha256(token.encode()).hexdigest()
            AuthSessionManager.add(payload["session_id"], payload["exp"].timestamp(), payload, auth_fingerprint=fingerprint, token_hash=token_hash)

            #Le token comprend toutes les couches d'authentification aux services
            return token
        return False

    #Vérifie un token d'authentification et le renvoie décodé
    @staticmethod
    def checkAuthentification(token:str) -> bool | dict:
        try:
            decoded = Auth._verify_token(token=token)
            session = AuthSessionManager.get(decoded["session_id"])
            if session is None:
                return False
            Auth._session_id_var.set(decoded["session_id"])
            return session.authentication
        except Exception:
            return False


    #Retourne l'ID de session courant
    @staticmethod
    def getSessionId() -> str:
        return Auth._session_id_var.get()

    #Retourne le payload du token d'authentification courant
    @staticmethod
    def getAuthentication() -> dict:
        session = AuthSessionManager.get(Auth.getSessionId())
        return session.authentication if session else None

    @staticmethod
    def _create_token(payload: dict, expires_in: int = 3600) -> str:
        secret = Config.get(key="authentication.jwt_secret")
        algorithm = Config.get(key="authentication.jwt_algorithm")

        payload["iat"] = datetime.now(tz=timezone.utc)
        payload["exp"] = datetime.now(tz=timezone.utc) + timedelta(seconds=expires_in)

        return jwt.encode(payload, secret, algorithm=algorithm)

    @staticmethod
    def _verify_token(token: str) -> dict:
        secret = Config.get(key="authentication.jwt_secret")
        algorithm = Config.get(key="authentication.jwt_algorithm")

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
        users = Config.get("app.admin_users")
        for user in users:
            u_ok = secrets.compare_digest(username.encode(), user["username"].encode())
            p_ok = secrets.compare_digest(password.encode(), user["password"].encode())
            if u_ok and p_ok:
                return True
        Logger.write(f"[HTTP] [401] rag — Unauthorized access attempt for user '{username}'", type=ERROR)
        return False


