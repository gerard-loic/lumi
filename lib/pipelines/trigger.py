TRIGGER_API_CALL = 1

class triggerEvent:
    def __init__(self, type:int, data:dict={}):
        self._type = type
        self._data = data

    def getType(self)->int:
        return self._type

    def getData(self)->dict:
        return self._data

class Trigger:
    def __init__(self, type:str, config:dict):
        self._type = type
        self._config = config

    def executable(self, event:triggerEvent)->bool:
        return False


