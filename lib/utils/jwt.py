from datetime import datetime, timezone, timedelta
import jwt

"""
Jwt — Utilitaire de gestion de JWT
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Jwt:
    #Créer un token JWT
    @staticmethod
    def createToken(payload: dict, secret:str, algorithm:str, expires_in: int = 3600) -> str:
        payload["iat"] = datetime.now(tz=timezone.utc)
        payload["exp"] = datetime.now(tz=timezone.utc) + timedelta(seconds=expires_in)
        return jwt.encode(payload, secret, algorithm=algorithm)

    #Vérifier un token JWT
    @staticmethod
    def verifyToken(token: str, secret:str, algorithm:str) -> dict:
        try:
            return jwt.decode(token, secret, algorithms=[algorithm])
        except jwt.ExpiredSignatureError:
            raise Exception("Token expiré")
        except jwt.InvalidTokenError as e:
            raise Exception(f"Token invalide : {e}")