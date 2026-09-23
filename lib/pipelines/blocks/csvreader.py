import csv
import io

from lib.pipelines.block import Block
from lib.pipelines.pipelinecontext import PipelineContext
from lib.pipelines.utils.filesource import resolve_file_source, FileSourceError
from lib.pipelines.utils.tabular import build_records, to_output
from lib.log.logger import Logger, ERROR, OK

#Bloc CsvReader : lit un fichier CSV et écrit dans le contexte une table exploitable par le bloc
#DataView (list[dict], ou forme colonnaire). Le fichier peut être produit pendant le run (sortie
#d'un bloc DataViewFile / Agent, URL "/files/...", clé FileStore) ou situé ailleurs sur le serveur.
#
#Paramètres de configuration (clé "config" du bloc) :
#  - source      (str|dict, obligatoire) : fichier à lire. Voir lib/pipelines/utils/filesource.py.
#  - encoding    (str,  défaut "utf-8")  : encodage de décodage du fichier.
#  - delimiter   (str,  défaut ",")      : séparateur de colonnes ; "auto" -> détection (csv.Sniffer).
#  - quotechar   (str,  défaut '"')      : caractère de citation.
#  - has_header  (bool, défaut True)     : la première ligne porte les noms de colonnes.
#  - columns     (list, défaut [])       : noms de colonnes imposés (si has_header, la 1re ligne est sautée ;
#                                          sinon et si vide, colonnes nommées "col_1", "col_2", ...).
#  - skip_rows   (int,  défaut 0)        : lignes ignorées en tête du fichier (avant l'en-tête).
#  - skip_empty  (bool, défaut True)     : ignore les lignes entièrement vides.
#  - trim        (bool, défaut True)     : retire les espaces de début / fin des cellules.
#  - infer_types (bool, défaut False)    : convertit les cellules en nombre (int puis float) si possible.
#  - limit       (int,  défaut 0)        : nombre maximum de lignes de données retournées (0 = pas de limite).
#  - as          (str,  défaut "list")   : "list" -> list[dict] ; "dict" -> {colonne: [valeurs]}.
#  - output      (str,  défaut "result") : clé du contexte où stocker le résultat.
class CsvReader(Block):
    def __init__(self, block_uid:str, config:dict, on_success_block:str=None, on_error_block:str=None):
        super().__init__("CsvReader", block_uid, config, on_success_block=on_success_block, on_error_block=on_error_block)

    def execute(self, context:PipelineContext):
        encoding    = context.getConfig(key="encoding", default="utf-8")
        delimiter   = context.getConfig(key="delimiter", default=",")
        quotechar   = context.getConfig(key="quotechar", default='"')
        has_header  = bool(context.getConfig(key="has_header", default=True))
        columns     = context.getConfig(key="columns", default=[]) or []
        skip_rows   = int(context.getConfig(key="skip_rows", default=0) or 0)
        skip_empty  = bool(context.getConfig(key="skip_empty", default=True))
        trim        = bool(context.getConfig(key="trim", default=True))
        infer_types = bool(context.getConfig(key="infer_types", default=False))
        limit       = int(context.getConfig(key="limit", default=0) or 0)
        as_         = str(context.getConfig(key="as", default="list")).lower()
        output      = context.getConfig(key="output", default="result")

        try:
            content, filename = resolve_file_source(self._config.get("source"), context)
        except FileSourceError as e:
            Logger.write(f"[Block CsvReader] {e}", type=ERROR)
            return False

        try:
            text = content.decode(encoding, errors="strict")
        except (LookupError, UnicodeDecodeError) as e:
            Logger.write(f"[Block CsvReader] Decode failed ({encoding}) : {e}", type=ERROR)
            return False

        #newline="" : la gestion des sauts de ligne dans les champs cités est déléguée au module csv.
        buffer = io.StringIO(text, newline="")

        if str(delimiter).lower() == "auto":
            sample = text[:4096]
            try:
                delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
            except csv.Error:
                delimiter = ","

        try:
            reader = csv.reader(buffer, delimiter=str(delimiter), quotechar=str(quotechar) or '"')
            matrix = list(reader)
        except csv.Error as e:
            Logger.write(f"[Block CsvReader] Invalid CSV : {e}", type=ERROR)
            return False

        records = build_records(
            matrix,
            has_header=has_header,
            columns=list(columns) or None,
            skip_rows=skip_rows,
            skip_empty=skip_empty,
            trim=trim,
            infer_types=infer_types,
            limit=limit,
        )
        result = to_output(records, as_)
        context.set(output, result)

        Logger.write(f"[Block CsvReader] {filename} -> '{output}' ({len(records)} row(s))", type=OK)
        return True
