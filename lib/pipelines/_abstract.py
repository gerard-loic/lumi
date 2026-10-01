from abc import ABC, abstractmethod
from lib.pipelines.triggerevent import TriggerEvent
from pathlib import Path
from lib.pipelines.pipelinecontext import PipelineContext

"""
Trigger — Classe de base pour les types de Trigger
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Trigger(ABC):
    #---------------------------------------------------------------------------------------------------------
    #Méthodes généralistes

    def __init__(self, type:str, config:dict):
        super().__init__()
        self._type = type
        self._config = config

    #Retourne si le trigger est exécutable
    def executable(self, event:TriggerEvent)->bool:
        return False


class Block(ABC):
    #---------------------------------------------------------------------------------------------------------
    #Méthodes généralistes
    
    def __init__(self, class_name:str, block_uid:str, config:dict, on_success_block:str=None, on_error_block:str=None):
        super().__init__()
        self._class_name = class_name
        self._block_uid = block_uid
        self._config = config
        self._on_success_block = on_success_block
        self._on_error_block = on_error_block
        self._pipeline_dir = None

    def getUid(self)->str:
        return self._block_uid

    #Dossier de configuration du pipeline propriétaire du bloc (renseigné par Pipeline au chargement)
    def setPipelineDir(self, pipeline_dir:Path):
        self._pipeline_dir = pipeline_dir

    def hasOnSuccessBlock(self)->bool:
        if self._on_success_block is None:
            return False
        return True
    
    def hasOnErrorBlock(self)->bool:
        if self._on_error_block is None:
            return False
        return True

    def getOnSuccessBlock(self)->str:
        return self._on_success_block

    def getOnErrorBlock(self)->str:
        return self._on_error_block

    #---------------------------------------------------------------------------------------------------------
    #Interface
    
    @abstractmethod
    def execute(self, context:PipelineContext)->bool: ...
