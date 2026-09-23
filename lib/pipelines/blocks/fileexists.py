from pathlib import Path

from lib.pipelines.block import Block
from lib.pipelines.pipelinecontext import PipelineContext
from lib.pipelines.utils.filesource import resolve_file_ref, FileSourceError
from lib.log.logger import Logger, ERROR, OK

#Bloc FileExists : teste la présence d'un fichier et écrit le résultat dans le contexte.
#Le fichier peut être un fichier produit pendant le run (sortie d'un bloc DataViewFile / Agent, URL
#"/files/...", clé FileStore) ou un fichier situé ailleurs sur le serveur (chemin).
#
#Paramètres de configuration (clé "config" du bloc) :
#  - source          (str | dict, obligatoire) : fichier à tester. Règles de
#                                                lib/pipelines/utils/filesource.py. Une entrée
#                                                "{var}" pointant vers une liste teste le 1er élément.
#  - fail_on_missing (bool, défaut True)        : True  -> le bloc échoue si le fichier est absent
#                                                (branchement immédiat via "on_error") ;
#                                                False -> le bloc réussit toujours et le test se lit
#                                                dans le contexte ("{<output>.exists}").
#  - output          (str,  défaut "result")    : clé du contexte où stocker
#                                                {"exists": bool, "path": str, "filename": str,
#                                                 "size": int|None}.
#
#Une "source" structurellement invalide (variable de contexte absente, dict mal formé, source vide)
#fait toujours échouer le bloc, indépendamment de fail_on_missing.
class FileExists(Block):
    def __init__(self, block_uid:str, config:dict, on_success_block:str=None, on_error_block:str=None):
        super().__init__("FileExists", block_uid, config, on_success_block=on_success_block, on_error_block=on_error_block)

    def execute(self, context:PipelineContext):
        fail_on_missing = bool(context.getConfig(key="fail_on_missing", default=True))
        output          = context.getConfig(key="output", default="result")

        try:
            ref = resolve_file_ref(self._config.get("source"), context)
        except FileSourceError as e:
            Logger.write(f"[Block FileExists] {e}", type=ERROR)
            return False

        exists = ref.exists()

        size = None
        if exists:
            try:
                size = Path(ref.path).stat().st_size
            except OSError:
                size = None

        context.set(output, {"exists": exists, "path": ref.path, "filename": ref.filename, "size": size})

        Logger.write(f"[Block FileExists] {ref.filename} : {'found' if exists else 'not found'}", type=OK)

        return exists or not fail_on_missing
