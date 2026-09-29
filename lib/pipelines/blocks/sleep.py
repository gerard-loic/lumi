import math
import time

from lib.pipelines.block import Block
from lib.pipelines.pipelinecontext import PipelineContext
from lib.log.logger import Logger, ERROR

#Bloc Sleep : met le run en pause pendant N secondes avant de passer au bloc suivant.
#Le run s'exécute dans son propre thread (PipelineRunner) : la pause ne bloque que ce run.
#
#Paramètres de configuration (clé "config" du bloc) :
#  - seconds (int | float | str, défaut 0) : durée de la pause en secondes (décimales acceptées).
#                                            Une chaine est convertie (ex : "{trigger.data.delai}").
#                                            Une valeur non numérique ou négative fait échouer le bloc.
class Sleep(Block):
    def __init__(self, block_uid:str, config:dict, on_success_block:str=None, on_error_block:str=None):
        super().__init__("Sleep", block_uid, config, on_success_block=on_success_block, on_error_block=on_error_block)

    def execute(self, context:PipelineContext):
        seconds = context.getConfig(key="seconds", default=0)

        #bool est un sous-type d'int : on l'exclut explicitement
        if isinstance(seconds, bool):
            Logger.write(f"[Block Sleep] Invalid duration '{seconds}'", type=ERROR)
            return False
        try:
            seconds = float(seconds)
        except (TypeError, ValueError):
            Logger.write(f"[Block Sleep] Invalid duration '{seconds}'", type=ERROR)
            return False
        if not math.isfinite(seconds) or seconds < 0:
            Logger.write(f"[Block Sleep] Invalid duration '{seconds}'", type=ERROR)
            return False

        time.sleep(seconds)
        return True
