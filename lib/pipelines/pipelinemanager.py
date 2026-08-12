from pathlib import Path
from lib.config.config import Config

class PipelineManager:
    @staticmethod
    def launch(pipeline:str):
        if PipelineManager.pipelineExists(pipeline=pipeline):

        raise Exception(f"[PipelineManager] Pipeline {pipeline} does not exists")
          

    @staticmethod
    def pipelineExists(pipeline:str)->bool:
        dossier = Path(f"{Config.get('directories.custom_pipelines')}/{pipeline}")
        if dossier.is_dir():
            fichier = Path(f"{Config.get('directories.custom_pipelines')}/{pipeline}.pipeline.json")
            if fichier.is_file():
                return True
            return False
        return False