from lib.pipelines.pipelinecontext import PipelineContext

class Block:
    def __init__(self, class_name:str, config:dict, next_block:str=None):
        self._class_name = class_name
        self._config = config
        self._next_block = next_block

    def execute(self, context:PipelineContext)->bool:
        return False

    def hasNextBloc(self)->bool:
        if self._next_block is None:
            return False
        return True

    def getNextBlock(self)->str:
        return self._next_block