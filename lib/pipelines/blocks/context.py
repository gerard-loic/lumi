from lib.pipelines.block import Block
from lib.pipelines.pipelinecontext import PipelineContext

#Bloc Context : injecte des valeurs statiques dans le contexte du pipeline.
#
#Paramètres de configuration (clé "config" du bloc) :
#  - <toute clé> : l'intégralité du dict "config" est fusionnée telle quelle dans le contexte (context.merge).
#                  Chaque paire clé/valeur devient donc une variable de contexte réutilisable par les blocs suivants.
class Context(Block):
    def __init__(self, block_uid:str, config:dict, on_success_block:str=None, on_error_block:str=None):
        super().__init__("Context", block_uid, config, on_success_block=on_success_block, on_error_block=on_error_block)

    def execute(self, context:PipelineContext):
        context.merge(self._config)
        return True