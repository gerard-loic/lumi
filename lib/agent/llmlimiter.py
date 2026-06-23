import time
from lib.files.localdata import LocalData
from lib.config.config import Config

"""
LLMLimiter : classe permettant de gérer la limitation de l'usage au LLM
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class LLMLimiter:

    #Retourne la limite de requêtes par minute
    @staticmethod
    def getFloodLimit():
        limit = Config.get("llm.max_requests_minute")
        if limit is None or limit == -1:
            return None
        return limit

    #Retourne True si la session dépasse le nombre de requêtes autorisées par minute.
    @staticmethod
    def isFloodDetected(session_id: str) -> bool:
        
        limit = LLMLimiter.getFloodLimit()
        if not limit:
            return False
        from lib.session.session import AuthSessionManager
        session = AuthSessionManager.get(session_id)
        if not session:
            return False
        now = time.time()
        session.flood_timestamps[:] = [t for t in session.flood_timestamps if now - t < 60.0]
        if len(session.flood_timestamps) >= limit:
            return True
        session.flood_timestamps.append(now)
        return False

    #Retourne le nombre de tokens autorisés par mois
    @staticmethod
    def getTokenLimit():
        limit = Config.get("llm.max_tokens_month")
        if limit == None or limit == -1:
            return None
        else:
            return limit
    
    #Retourne le nombre de requeêtes autorisées par mois
    @staticmethod
    def getRequestLimit():
        limit = Config.get("llm.max_requests_month")
        if limit == None or limit == -1:
            return None
        else:
            return limit

    #Retourne l'usage actuel en nombre de tokens
    @staticmethod
    def getTokenUsage():
        return int(LocalData.getLLMUsage(currentMonth=True)[0]["token_used"])
    
    #Retourne le nombre de requetes actuel
    @staticmethod
    def getRequestUsage():
        return int(LocalData.getLLMUsage(currentMonth=True)[0]["request_count"])
    
    #Retourne TRUE si le nombre de tokens utilisés excède le nombre max autorisé
    @staticmethod
    def isTokenUsageExceeded():
        limit = LLMLimiter.getTokenLimit()
        if limit:
            usage = LLMLimiter.getTokenUsage()
            if usage >= limit:
                return True
        return False
    
    #Retourne TRUE si le nombre de requêtes effectuées excède le nombre max autorisé
    @staticmethod
    def isRequestUsageExceeded():
        limit = LLMLimiter.getRequestLimit()
        if limit:
            usage = LLMLimiter.getRequestUsage()
            if usage >= limit:
                return True
        return False
