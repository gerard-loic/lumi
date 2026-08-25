from pathlib import Path
from lib.config.config import Config
from lib.pipelines.pipeline import Pipeline
from lib.log.logger import Logger, OK, WARNING
from lib.pipelines.pipelinerunner import PipelineRunner
from lib.pipelines.trigger import triggerEvent

class PipelineManager:

    @staticmethod
    def init():
        Logger.write("[PipelineManager] Pipeline manager initialization...", type=WARNING)
        PipelineManager._pipelines_run = {}
        PipelineManager._pipelines = {}

        dossier_racine = Path(Config.get('directories.custom_pipelines'))
        for dossier in dossier_racine.iterdir():
            if not dossier.is_dir():
                continue

            pipeline_uid = dossier.name
            if PipelineManager.pipelineExists(pipeline_uid=pipeline_uid):
                PipelineManager._pipelines[pipeline_uid] = Pipeline(pipeline_uid=pipeline_uid)

    @staticmethod
    def trigger(event:triggerEvent, target_pipelines:list=[]):
        for pipeline in PipelineManager._pipelines:
            if len(target_pipelines) == 0 or pipeline in target_pipelines:
                pipeline = PipelineManager._pipelines[pipeline]
                if pipeline.trigger(event=event):
                    pipeline_run = PipelineRunner(pipeline=pipeline)
                    PipelineManager._pipelines_run[pipeline_run.getProcess()] = pipeline_run
                    pipeline_run.launch()
    

    @staticmethod
    def pipelineExists(pipeline_uid:str)->bool:
        dossier = Path(f"{Config.get('directories.custom_pipelines')}/{pipeline_uid}")
        if dossier.is_dir():
            fichier = Path(f"{Config.get('directories.custom_pipelines')}/{pipeline_uid}/pipeline.json")
            if fichier.is_file():
                return True
            return False
        return False