import json
from jsonschema import validators
from jsonschema.exceptions import SchemaError
from lib.log.logger import Logger, ERROR

"""
ConfigFileChecker — Vérification de la structure d'un fichier JSON à partir d'un JSON Schema
La version du schéma est déduite de sa clé "$schema" (Draft 2020-12 par défaut).
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class ConfigFileChecker:
    def __init__(self, schemaPath:str):
        self.errors = []
        try:
            with open(schemaPath, "r", encoding="utf-8") as f:
                schema = json.load(f)
            validatorClass = validators.validator_for(schema)
            validatorClass.check_schema(schema)
        except (OSError, json.JSONDecodeError, SchemaError) as e:
            e = getattr(e, "message", e)
            Logger.write(text=f"JSON Schema {schemaPath} unreadable : {e}", type=ERROR)
            raise Exception(f"JSON Schema {schemaPath} unreadable : {e}")
        self.validator = validatorClass(schema, format_checker=validatorClass.FORMAT_CHECKER)

    #Vérifie le fichier JSON à partir de son emplacement
    def checkFile(self, jsonPath:str) -> bool:
        try:
            with open(jsonPath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            self.errors = [f"JSON {jsonPath} unreadable : {e}"]
            Logger.write(text=self.errors[0], type=ERROR)
            return False
        return self.check(data, source=jsonPath)

    #Vérifie une variable au format JSON
    def check(self, data, source:str="<data>") -> bool:
        self.errors = [
            f"{error.json_path} : {error.message}"
            for error in sorted(self.validator.iter_errors(data), key=lambda e: list(e.absolute_path))
        ]
        for error in self.errors:
            Logger.write(text=f"Config {source} invalid - {error}", type=ERROR)
        return len(self.errors) == 0
