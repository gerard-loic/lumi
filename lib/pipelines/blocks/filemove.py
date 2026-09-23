import os
import shutil
from pathlib import Path

from lib.pipelines.block import Block
from lib.pipelines.pipelinecontext import PipelineContext
from lib.pipelines.utils.filesource import resolve_file_refs, FileSourceError
from lib.log.logger import Logger, ERROR, OK

#Bloc FileMove : déplace (ou renomme) un ou plusieurs fichiers vers un emplacement du serveur.
#Déplacer un fichier produit pendant le run (clé FileStore) vers un chemin durable est le moyen de
#le conserver au-delà de la fin du run (le stockage temporaire est purgé à la fin du run).
#
#Paramètres de configuration (clé "config" du bloc) :
#  - source      (str | dict | list, obligatoire) : fichier(s) à déplacer. Règles de
#                                                   lib/pipelines/utils/filesource.py. Une entrée
#                                                   "{var}" pointant vers une liste déplace tous ses
#                                                   fichiers (destination = dossier obligatoire).
#  - destination (str, obligatoire)                : chemin cible. Si c'est un dossier existant ou se
#                                                   termine par "/", chaque fichier y est déplacé sous
#                                                   son nom d'origine ; sinon c'est le chemin complet
#                                                   cible (renommage, une seule source).
#  - overwrite   (bool, défaut False)              : autorise l'écrasement d'un fichier cible existant.
#  - create_dirs (bool, défaut True)               : crée les dossiers parents manquants.
#  - output      (str,  défaut "result")           : clé du contexte où stocker {"path","filename"}
#                                                   (ou une liste de ces dicts si plusieurs sources).
class FileMove(Block):
    def __init__(self, block_uid:str, config:dict, on_success_block:str=None, on_error_block:str=None):
        super().__init__("FileMove", block_uid, config, on_success_block=on_success_block, on_error_block=on_error_block)

    def execute(self, context:PipelineContext):
        destination = context.getConfig(key="destination", default="")
        overwrite   = bool(context.getConfig(key="overwrite", default=False))
        create_dirs = bool(context.getConfig(key="create_dirs", default=True))
        output      = context.getConfig(key="output", default="result")

        if not destination:
            Logger.write("[Block FileMove] Missing 'destination' in config", type=ERROR)
            return False

        try:
            refs = resolve_file_refs(self._config.get("source"), context)
        except FileSourceError as e:
            Logger.write(f"[Block FileMove] {e}", type=ERROR)
            return False

        if not refs:
            Logger.write("[Block FileMove] No source file", type=ERROR)
            return False

        dest = Path(destination).expanduser()
        into_dir = len(refs) > 1 or destination.endswith(("/", os.sep)) or dest.is_dir()

        results = []
        for ref in refs:
            if not ref.exists():
                Logger.write(f"[Block FileMove] Source not found : {ref.path or ref.filename}", type=ERROR)
                return False

            target = (dest / ref.filename) if into_dir else dest
            if target.is_dir():
                target = target / ref.filename

            if target.exists() and not overwrite:
                Logger.write(f"[Block FileMove] Target already exists : {target} (set 'overwrite')", type=ERROR)
                return False

            if create_dirs:
                target.parent.mkdir(parents=True, exist_ok=True)
            elif not target.parent.is_dir():
                Logger.write(f"[Block FileMove] Target directory missing : {target.parent}", type=ERROR)
                return False

            try:
                if target.exists():
                    target.unlink()
                shutil.move(str(ref.path), str(target))
            except OSError as e:
                Logger.write(f"[Block FileMove] Move failed ('{ref.filename}') : {e}", type=ERROR)
                return False

            #Le fichier a quitté le stockage temporaire : l'entrée éventuelle du registre du run
            #devient un no-op à la purge de fin de run, rien à nettoyer ici.
            results.append({"path": str(target), "filename": ref.filename})
            Logger.write(f"[Block FileMove] {ref.filename} -> {target}", type=OK)

        context.set(output, results if len(results) > 1 else results[0])
        return True
