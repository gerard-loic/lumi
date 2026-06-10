import jwt
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
    sessionId = None

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
            Auth.authentication = payload
            Auth.sessionId = payload["session_id"]

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
            Auth.authentication = decoded
            Auth.sessionId = decoded["session_id"]
            return decoded
        except Exception:
            return False
        
    """
    Retourne l'ID de session courant
    """
    @staticmethod
    def getSessionId() -> str:
        return Auth.sessionId
    
    """
    Retourne le payload du token d'authentification courant
    """
    @staticmethod
    def getAuthentication() -> dict:
        return Auth.authentication

    @staticmethod
    def _create_token(payload: dict, expires_in: int = 3600) -> str:
        secret = Config.get(key="jwt_secret")
        algorithm = Config.get(key="jwt_algorithm")

        data = payload.copy()
        data["iat"] = datetime.now(tz=timezone.utc)
        data["exp"] = datetime.now(tz=timezone.utc) + timedelta(seconds=expires_in)

        return jwt.encode(data, secret, algorithm=algorithm)

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