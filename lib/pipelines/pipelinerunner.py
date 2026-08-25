
import threading
from typing import TYPE_CHECKING
from lib.utils.uuid import Uuid
from lib.log.logger import Logger, ERROR
from lib.pipelines.pipelinecontext import PipelineContext

if TYPE_CHECKING:
    from lib.pipelines.pipeline import Pipeline
    from lib.pipelines.block import Block


class PipelineRunner:
    def __init__(self, pipeline:"Pipeline"):
        self._pipeline = pipeline
        self._process = Uuid.getUuid()
        self._thread = None

    def getProcess(self)->str:
        return self._process

    def launch(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        Logger.write("RUN PIPELINE")

        #On définit l'objet de conservation de contexte
        context = PipelineContext()

        #On cherche le noeud de départ
        root_block = self._pipeline.getRootBlock()

        #On commence en executant le noeud de départ
        self._executeBlock(block=root_block, context=context)


    def _executeBlock(self, block:"Block", context:PipelineContext):
        try:
            block.execute(context)
        except Exception as e:
            Logger.write(f"[PipelineRunner {self._process}] Erreur pendant l'exécution : {e}", type=ERROR)

        if block.hasNextBloc():
            #On cherche le prochain block
            next_block = self._pipeline.getBlock(block_uid=block.getNextBlock())
            self._executeBlock(block=next_block, context=context)
        else:
            self._end()

    def _end(self):
        Logger.write("END PIPELINE")
        pass

