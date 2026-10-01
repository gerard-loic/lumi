TRIGGER_API_CALL = 1

"""
TriggerEvent — Evénement trigger
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class TriggerEvent:
    def __init__(self, type:int, data:dict=None):
        self._type = type
        self._data = data if data is not None else {}

    #Retourne le type
    def getType(self)->int:
        return self._type

    #Retourne les données de l'événement
    def getData(self)->dict:
        return self._data

