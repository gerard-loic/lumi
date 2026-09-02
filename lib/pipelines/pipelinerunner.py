
import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from lib.utils.uuid import Uuid
from lib.log.logger import Logger, ERROR
from lib.pipelines.pipelinecontext import PipelineContext
from lib.pipelines.pipelinelog import PipelineLog

if TYPE_CHECKING:
    from lib.pipelines.pipeline import Pipeline
    from lib.pipelines.block import Block
    from lib.pipelines.trigger import triggerEvent


class PipelineRunner:
    def __init__(self, pipeline:"Pipeline", event:"triggerEvent"=None):
        self._pipeline = pipeline
        self._event = event
        self._process = Uuid.getUuid()
        self._thread = None
        self._log_id = None

    def getProcess(self)->str:
        return self._process

    def launch(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        Logger.write("RUN PIPELINE")

        #On définit l'objet de conservation de contexte
        context = PipelineContext()

        #On injecte les données portées par le trigger dans le contexte : elles deviennent
        #accessibles aux blocs via {trigger.type} et {trigger.data.<clé>} (ex : payload d'un
        #appel API, email reçu, fichier détecté...). Sans event (déclenchement interne), le
        #contexte démarre vide comme auparavant.
        if self._event is not None:
            context.set("trigger", {
                "type": self._event.getType(),
                "data": self._event.getData(),
            })

        #On écrit le log initial
        self._log_id = PipelineLog.createProcess(pipeline_uid=self._pipeline.getUid(), process_uid=self._process)

        #On cherche le noeud de départ
        root_block = self._pipeline.getRootBlock()

        #On commence en executant le noeud de départ
        self._executeBlock(block=root_block, context=context)


    def _executeBlock(self, block:"Block", context:PipelineContext):
        #On écrit le log du noeud initial
        block_log_id = PipelineLog.createBlock(pipeline_process_id=self._log_id, name=block.getUid())

        logs = ""
        result = False

        #Récupérer les logs spécifiques à ce bloc
        with Logger.capture() as log_buffer:
            try:
                result = block.execute(context)
            except Exception as e:
                result = False
                Logger.write(f"[PipelineRunner {self._process}] Erreur pendant l'exécution : {e}", type=ERROR)
            finally:
                #On conserve l'intégralité des logs produits par ce bloc, concaténés
                logs = log_buffer.getvalue()

        #On persiste les logs et le statut du bloc
        PipelineLog.updateBlock(block_id=block_log_id, is_success=result, logs=logs)

        if result:
            #On écrit le succès
            PipelineLog.updateBlock(block_id=block_log_id, is_success=True, logs=logs)
            if block.hasOnSuccessBlock():
                if block.getOnSuccessBlock() == "exit(0)":
                    self._end(success=False)
                elif block.getOnSuccessBlock() == "exit(1)":
                    self._end(success=True)
                else:
                    #On cherche le prochain block
                    next_block = self._pipeline.getBlock(block_uid=block.getOnSuccessBlock())
                    self._executeBlock(block=next_block, context=context)
            else:
                self._end(success=True)
        else:
            #On écrit l'échec
            PipelineLog.updateBlock(block_id=block_log_id, is_success=False, logs=logs)
            if block.hasOnErrorBlock():
                if block.getOnErrorBlock() == "exit(0)":
                    self._end(success=False)
                elif block.getOnErrorBlock() == "exit(1)":
                    self._end(success=True)
                else:
                    #On cherche le prochain block
                    next_block = self._pipeline.getBlock(block_uid=block.getOnErrorBlock())
                    self._executeBlock(block=next_block, context=context)
            else:
                self._end(success=False)

    def _end(self, success:bool):
        ended_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        PipelineLog.updateProcess(process_id=self._log_id, is_success=success, ended_at=ended_at)

