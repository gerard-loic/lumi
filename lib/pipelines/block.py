from lib.pipelines.pipelinecontext import PipelineContext

class Block:
    def __init__(self, class_name:str, block_uid:str, config:dict, on_success_block:str=None, on_error_block:str=None):
        self._class_name = class_name
        self._block_uid = block_uid
        self._config = config
        self._on_success_block = on_success_block
        self._on_error_block = on_error_block

    def getUid(self)->str:
        return self._block_uid

    def execute(self, context:PipelineContext)->bool:
        return False

    def getConfig(self, key:str, default=None):
        if key in self._config:
            return self._config[key]
        else:
            return default

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
    