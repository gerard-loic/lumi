import csv
import io
import json

from lib.pipelines.block import Block
from lib.pipelines.pipelinecontext import PipelineContext
from lib.files.filestore import FileStore
from lib.log.logger import Logger, ERROR, OK

#Bloc DataViewFile : sérialise une liste de lignes (typiquement la sortie d'un bloc DataView en
#as="list") dans un fichier temporaire, et écrit dans le contexte {"key","filename","path","url"}.
#Le fichier est rattaché au run de pipeline (cf. FileStore / PipelineRunner) : servi par la route
#GET /files via l'URL renvoyée le temps du run, puis purgé automatiquement à la fin du run.
#
#Paramètres de configuration (clé "config" du bloc) :
#  - input     (str,  obligatoire)   : clé du contexte contenant la liste de lignes (list[dict]).
#  - format    (str,  défaut "csv")  : "csv" | "json" | "jsonl".
#  - filename  (str,  défaut "dataview.<format>") : nom du fichier proposé au téléchargement.
#  - delimiter (str,  défaut ",")    : séparateur CSV (format "csv" uniquement).
#  - output    (str,  défaut "file") : clé du contexte où stocker {"key","filename","path","url"}.
class DataViewFile(Block):
    _FORMATS = ("csv", "json", "jsonl")

    def __init__(self, block_uid:str, config:dict, on_success_block:str=None, on_error_block:str=None):
        super().__init__("DataViewFile", block_uid, config, on_success_block=on_success_block, on_error_block=on_error_block)

    def execute(self, context:PipelineContext):
        input_key = context.getConfig(key="input", default="")
        fmt       = str(context.getConfig(key="format", default="csv")).lower()
        delimiter = context.getConfig(key="delimiter", default=",")
        output    = context.getConfig(key="output", default="file")
        filename  = context.getConfig(key="filename", default=f"dataview.{fmt if fmt in self._FORMATS else 'txt'}")

        if not input_key:
            Logger.write("[Block DataViewFile] Missing 'input' in config", type=ERROR)
            return False
        if fmt not in self._FORMATS:
            Logger.write(f"[Block DataViewFile] Unsupported format '{fmt}' (csv|json|jsonl)", type=ERROR)
            return False

        try:
            rows = context.get(key=input_key)
        except KeyError:
            Logger.write(f"[Block DataViewFile] Context key '{input_key}' not found", type=ERROR)
            return False

        if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            Logger.write("[Block DataViewFile] 'input' must be a list of dict rows", type=ERROR)
            return False

        if fmt == "json":
            content = json.dumps(rows, ensure_ascii=False, indent=2)
        elif fmt == "jsonl":
            content = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
        else:
            #colonnes = union des clés dans l'ordre de première apparition
            columns = list(dict.fromkeys(k for r in rows for k in r))
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore", delimiter=delimiter)
            writer.writeheader()
            writer.writerows(rows)
            content = buffer.getvalue()

        url = FileStore.save(filename=filename, content=content)
        key = FileStore.key_from_url(url)
        context.set(output, {"key": key, "filename": filename, "path": FileStore.path(key), "url": url})

        Logger.write(f"[Block DataViewFile] {len(rows)} row(s) -> {filename} ({fmt})", type=OK)
        return True
