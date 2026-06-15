import time
from collections import defaultdict
from lib.files.localdata import LocalData
from lib.config.config import Config

class LLMLimiter:
    _session_timestamps: dict[str, list[float]] = defaultdict(list)

    @staticmethod
    def getFloodLimit():
        limit = Config.get("llm.max_requests_minute")
        if limit is None or limit == -1:
            return None
        return limit

    @staticmethod
    def isFloodDetected(session_id: str) -> bool:
        """Retourne True si la session dépasse le nombre de requêtes autorisées par minute."""
        limit = LLMLimiter.getFloodLimit()
        if not limit:
            return False
        now = time.time()
        timestamps = LLMLimiter._session_timestamps[session_id]
        timestamps[:] = [t for t in timestamps if now - t < 60.0]
        if len(timestamps) >= limit:
            return True
        timestamps.append(now)
        return False

    @staticmethod
    def getTokenLimit():
        limit = Config.get("llm.max_tokens_month")
        if limit == None or limit == -1:
            return None
        else:
            return limit
        
    @staticmethod
    def getRequestLimit():
        limit = Config.get("llm.max_requests_month")
        if limit == None or limit == -1:
            return None
        else:
            return limit
        
    @staticmethod
    def getTokenUsage():
        return int(LocalData.getLLMUsage(currentMonth=True)[0]["token_used"])
    
    @staticmethod
    def getRequestUsage():
        return int(LocalData.getLLMUsage(currentMonth=True)[0]["request_count"])
    
    @staticmethod
    def isTokenUsageExceeded():
        limit = LLMLimiter.getTokenLimit()
        if limit:
            usage = LLMLimiter.getTokenUsage()
            if usage >= limit:
                return True
        return False
    
    @staticmethod
    def isRequestUsageExceeded():
        limit = LLMLimiter.getRequestLimit()
        if limit:
            usage = LLMLimiter.getRequestUsage()
            if usage >= limit:
                return True
        return False
