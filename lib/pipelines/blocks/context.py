from lib.pipelines.block import Block
from lib.pipelines.pipelinecontext import PipelineContext

class Context(Block):
    def __init__(self, config:dict, next_block:str=None):
        super().__init__("Context", config, next_block)

    def execute(self, context:PipelineContext):
        context.merge(self._config)
        return True