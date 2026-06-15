from lib.files.localdata import LocalData
from lib.config.config import Config

class LLMLimiter:
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
