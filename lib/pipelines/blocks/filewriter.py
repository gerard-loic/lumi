import os
from pathlib import Path

from lib.pipelines.block import Block
from lib.pipelines.pipelinecontext import PipelineContext
from lib.pipelines.utils.filesource import resolve_file_refs, FileSourceError
from lib.log.logger import Logger, ERROR, OK

#Bloc FileWriter : écrit sur le disque du serveur une copie d'un ou plusieurs fichiers du stockage
#temporaire (fichiers générés pendant le run : sortie d'un bloc DataViewFile / Agent, URL "/files/...",
#clé FileStore). Contrairement à FileMove, le fichier temporaire est conservé : son URL de
#téléchargement reste valide jusqu'à la fin du run.
#
#Paramètres de configuration (clé "config" du bloc) :
#  - source      (str | dict | list, obligatoire) : fichier(s) temporaire(s) à écrire. Règles de
#                                                   lib/pipelines/utils/filesource.py, restreintes aux
#                                                   fichiers du FileStore (un chemin serveur est refusé).
#                                                   Une entrée "{var}" pointant vers une liste écrit
#                                                   tous ses fichiers (destination = dossier obligatoire).
#  - destination (str, obligatoire)                : chemin cible. Si c'est un dossier existant ou se
#                                                   termine par "/", chaque fichier y est écrit sous
#                                                   son nom d'origine ; sinon c'est le chemin complet
#                                                   cible (renommage, une seule source).
#  - overwrite   (bool, défaut False)              : autorise l'écrasement d'un fichier cible existant.
#  - create_dirs (bool, défaut True)               : crée les dossiers parents manquants.
#  - output      (str,  défaut "result")           : clé du contexte où stocker {"path","filename","size"}
#                                                   (ou une liste de ces dicts si plusieurs sources).
class FileWriter(Block):
    def __init__(self, block_uid:str, config:dict, on_success_block:str=None, on_error_block:str=None):
        super().__init__("FileWriter", block_uid, config, on_success_block=on_success_block, on_error_block=on_error_block)

    def execute(self, context:PipelineContext):
        destination = context.getConfig(key="destination", default="")
        overwrite   = bool(context.getConfig(key="overwrite", default=False))
        create_dirs = bool(context.getConfig(key="create_dirs", default=True))
        output      = context.getConfig(key="output", default="result")

        if not destination:
            Logger.write("[Block FileWriter] Missing 'destination' in config", type=ERROR)
            return False

        try:
            refs = resolve_file_refs(self._config.get("source"), context)
        except FileSourceError as e:
            Logger.write(f"[Block FileWriter] {e}", type=ERROR)
            return False

        if not refs:
            Logger.write("[Block FileWriter] No source file", type=ERROR)
            return False

        dest = Path(destination).expanduser()
        into_dir = len(refs) > 1 or destination.endswith(("/", os.sep)) or dest.is_dir()

        results = []
        for ref in refs:
            if not ref.is_filestore:
                Logger.write(f"[Block FileWriter] Source is not a temporary file : {ref.path or ref.filename} (use FileMove)", type=ERROR)
                return False

            #Lecture via FileStore : n'accepte que les fichiers rattachés au run courant
            try:
                content = ref.read()
            except FileSourceError as e:
                Logger.write(f"[Block FileWriter] Cannot read '{ref.filename}' : {e}", type=ERROR)
                return False

            target = (dest / ref.filename) if into_dir else dest
            if target.is_dir():
                target = target / ref.filename

            if target.exists() and not overwrite:
                Logger.write(f"[Block FileWriter] Target already exists : {target} (set 'overwrite')", type=ERROR)
                return False

            if create_dirs:
                target.parent.mkdir(parents=True, exist_ok=True)
            elif not target.parent.is_dir():
                Logger.write(f"[Block FileWriter] Target directory missing : {target.parent}", type=ERROR)
                return False

            #Écriture dans un fichier voisin puis remplacement atomique : pas de fichier cible tronqué en cas d'échec
            tmp_target = target.with_name(f".{target.name}.part")
            try:
                tmp_target.write_bytes(content)
                os.replace(tmp_target, target)
            except OSError as e:
                tmp_target.unlink(missing_ok=True)
                Logger.write(f"[Block FileWriter] Write failed ('{ref.filename}') : {e}", type=ERROR)
                return False

            results.append({"path": str(target), "filename": ref.filename, "size": len(content)})
            Logger.write(f"[Block FileWriter] {ref.filename} -> {target}", type=OK)

        context.set(output, results if len(results) > 1 else results[0])
        return True
