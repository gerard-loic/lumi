from pathlib import Path

from lib.pipelines.block import Block
from lib.pipelines.pipelinecontext import PipelineContext
from lib.pipelines.utils.filesource import resolve_file_refs, FileSourceError
from lib.files.filestore import FileStore
from lib.log.logger import Logger, ERROR, OK

#Bloc FileDelete : supprime un ou plusieurs fichiers.
#Le fichier peut être un fichier produit pendant le run (sortie d'un bloc DataViewFile / Agent, URL
#"/files/...", clé FileStore) ou un fichier situé ailleurs sur le serveur (chemin).
#
#Paramètres de configuration (clé "config" du bloc) :
#  - source     (str | dict | list, obligatoire) : fichier(s) à supprimer. Chaque entrée suit les
#                                                  règles de lib/pipelines/utils/filesource.py.
#                                                  Une entrée "{var}" pointant vers une liste (ex.
#                                                  "{files}" d'un bloc Agent) supprime tous ses
#                                                  fichiers.
#  - missing_ok (bool, défaut True)               : ne pas faire échouer le bloc si un fichier est
#                                                  déjà absent.
#  - output     (str,  défaut "result")           : clé du contexte où stocker
#                                                  {"deleted": [noms...], "missing": [noms...]}.
class FileDelete(Block):
    def __init__(self, block_uid:str, config:dict, on_success_block:str=None, on_error_block:str=None):
        super().__init__("FileDelete", block_uid, config, on_success_block=on_success_block, on_error_block=on_error_block)

    def execute(self, context:PipelineContext):
        missing_ok = bool(context.getConfig(key="missing_ok", default=True))
        output     = context.getConfig(key="output", default="result")

        raw = self._config.get("source", self._config.get("sources"))

        try:
            refs = resolve_file_refs(raw, context)
        except FileSourceError as e:
            Logger.write(f"[Block FileDelete] {e}", type=ERROR)
            return False

        if not refs:
            Logger.write("[Block FileDelete] No file to delete", type=ERROR)
            return False

        deleted, missing = [], []
        for ref in refs:
            #Fichier du run : on le retire du FileStore (supprime le fichier temporaire).
            removed = FileStore.delete(ref.key) if ref.key is not None else False

            if not removed and ref.exists():
                try:
                    Path(ref.path).unlink()
                    removed = True
                except OSError as e:
                    Logger.write(f"[Block FileDelete] Cannot delete '{ref.filename}' : {e}", type=ERROR)
                    return False

            (deleted if removed else missing).append(ref.filename)

        if missing and not missing_ok:
            Logger.write(f"[Block FileDelete] File(s) not found : {missing}", type=ERROR)
            return False

        context.set(output, {"deleted": deleted, "missing": missing})
        Logger.write(f"[Block FileDelete] {len(deleted)} deleted, {len(missing)} already absent", type=OK)
        return True
