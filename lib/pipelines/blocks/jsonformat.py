import json

from jsonschema import ValidationError, validate

from lib.pipelines._abstract import Block
from lib.pipelines.pipelinecontext import PipelineContext
from lib.log.logger import Logger, ERROR

#Bloc JsonFormat : parse une chaine JSON du contexte, la valide optionnellement contre un JSON Schema, et écrit la structure obtenue.
#
#Paramètres de configuration (clé "config" du bloc) :
#  - input  (str,          défaut "")    : clé du contexte contenant la chaine JSON sérialisée à parser (une valeur non-str provoque une erreur).
#  - format (dict | False, défaut False) : JSON Schema de validation ; si False, aucune validation n'est effectuée.
#  - format_file (str,     défaut None)  : fichier .json du JSON Schema, relatif au dossier du pipeline (exclusif avec format, non interpolé).
#  - output (str,          défaut "")    : clé du contexte où stocker la structure désérialisée.
class JsonFormat(Block):
    def __init__(self, block_uid:str, config:dict, on_success_block:str=None, on_error_block:str=None):
        super().__init__("JsonFormat", block_uid, config, on_success_block=on_success_block, on_error_block=on_error_block)

    def execute(self, context:PipelineContext):
        #Récupération de la configuration
        format = context.getConfig(key="format", default=False)
        input = context.getConfig(key="input", default="")
        output = context.getConfig(key="output", default="")
        #Le chemin du schéma n'est volontairement pas interpolé : une donnée du contexte ne doit pas choisir le fichier lu
        format_file = self._config.get("format_file")

        if format_file is not None:
            if format is not False:
                Logger.write(f"[Block JsonFormat] 'format' and 'format_file' are mutually exclusive", type=ERROR)
                return False
            path = self.resolvePipelineFile(format_file, (".json",)) if isinstance(format_file, str) and format_file != "" else None
            if path is None:
                Logger.write(f"[Block JsonFormat] Schema '{format_file}' must be a .json file inside the pipeline directory", type=ERROR)
                return False
            try:
                format = json.loads(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                Logger.write(f"[Block JsonFormat] Schema '{format_file}' does not exist", type=ERROR)
                return False
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
                Logger.write(f"[Block JsonFormat] Invalid JSON Schema '{format_file}' : {e}", type=ERROR)
                return False

        input_val = context.get(key=input)

        #Une chaine est interprétée comme du JSON sérialisé : on la parse pour obtenir la structure.
        #Toute autre valeur est supposée déjà désérialisée et utilisée telle quelle.
        if isinstance(input_val, str):
            try:
                value = json.loads(input_val)
            except json.JSONDecodeError as e:
                Logger.write(f"[Block JsonFormat] Invalid JSON on input '{input}' : {e}", type=ERROR)
                return False
        else:
            Logger.write(f"[Block JsonFormat] Initial value must be a string", type=ERROR)
            return False

        #format est un JSON Schema : on valide la structure quand il est fourni (format != False)
        if format is not False:
            try:
                validate(instance=value, schema=format)
            except ValidationError as e:
                Logger.write(f"[Block JsonFormat] Schema validation failed on input '{input}' : {e.message}", type=ERROR)
                return False

        context.set(output, value)
        return True
