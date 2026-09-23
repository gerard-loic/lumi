from lib.pipelines.block import Block
from lib.pipelines.pipelinecontext import PipelineContext
from lib.pipelines.utils.filesource import resolve_file_source, FileSourceError
from lib.log.logger import Logger, ERROR, OK

#Bloc TxtReader : lit un fichier texte brut (txt, md, log, ...) et écrit son contenu dans le contexte.
#Le fichier peut être un fichier produit pendant le run (sortie d'un bloc DataViewFile ou d'un bloc
#Agent, URL "/files/..." ou clé FileStore) ou un fichier situé ailleurs sur le serveur (chemin).
#
#Paramètres de configuration (clé "config" du bloc) :
#  - source   (str|dict, obligatoire)   : fichier à lire. Voir lib/pipelines/utils/filesource.py :
#                                         chemin serveur, "{var}" (dict/list de fichier de pipeline),
#                                         URL "/files/<key>/<nom>", ou clé FileStore (32 hexa).
#  - encoding (str,  défaut "utf-8")     : encodage de décodage du fichier.
#  - errors   (str,  défaut "strict")    : politique de décodage ("strict", "replace", "ignore").
#  - strip    (bool, défaut False)       : retire les espaces / sauts de ligne de début et de fin.
#  - as       (str,  défaut "text")      : "text" -> chaine ; "lines" -> liste de lignes.
#  - keepends (bool, défaut False)       : conserve le "\n" en fin de ligne (as="lines" uniquement).
#  - output   (str,  défaut "result")    : clé du contexte où stocker le résultat.
class TxtReader(Block):
    def __init__(self, block_uid:str, config:dict, on_success_block:str=None, on_error_block:str=None):
        super().__init__("TxtReader", block_uid, config, on_success_block=on_success_block, on_error_block=on_error_block)

    def execute(self, context:PipelineContext):
        encoding = context.getConfig(key="encoding", default="utf-8")
        errors   = context.getConfig(key="errors", default="strict")
        strip    = bool(context.getConfig(key="strip", default=False))
        as_      = str(context.getConfig(key="as", default="text")).lower()
        keepends = bool(context.getConfig(key="keepends", default=False))
        output   = context.getConfig(key="output", default="result")

        try:
            content, filename = resolve_file_source(self._config.get("source"), context)
        except FileSourceError as e:
            Logger.write(f"[Block TxtReader] {e}", type=ERROR)
            return False

        try:
            text = content.decode(encoding, errors=errors)
        except (LookupError, UnicodeDecodeError) as e:
            Logger.write(f"[Block TxtReader] Decode failed ({encoding}) : {e}", type=ERROR)
            return False

        if strip:
            text = text.strip()

        result = text.splitlines(keepends=keepends) if as_ == "lines" else text
        context.set(output, result)

        size = len(result) if as_ == "lines" else len(text)
        unit = "line(s)" if as_ == "lines" else "char(s)"
        Logger.write(f"[Block TxtReader] {filename} -> '{output}' ({size} {unit})", type=OK)
        return True
