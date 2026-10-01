import importlib.util

from lib.pipelines._abstract import Block
from lib.pipelines.pipelinecontext import PipelineContext
from lib.log.logger import Logger, ERROR, OK

#Bloc PythonScript : exécute un script Python situé dans le dossier de configuration du pipeline.
#Le script doit définir une fonction run(context, params), appelée avec le PipelineContext du run :
#elle peut donc lire (context.get / context.resolve) et modifier (context.set / context.merge) le contexte.
#  - run() renvoie False ou lève une exception -> échec du bloc (branche on_error) ;
#  - toute autre valeur de retour (y compris None)   -> succès du bloc (branche on_success).
#Le script est rechargé à chaque exécution : une modification est prise en compte sans redémarrage.
#Il s'exécute sans bac à sable, avec les droits du serveur : il a le même niveau de confiance que pipeline.json.
#
#Paramètres de configuration (clé "config" du bloc) :
#  - script   (str,  obligatoire)   : chemin du script, relatif au dossier du pipeline (ex : "scripts/calcul.py").
#                                     Non interpolé, doit rester dans le dossier du pipeline et finir par ".py".
#  - function (str,  défaut "run")  : nom de la fonction à appeler dans le script.
#  - params   (dict, défaut {})     : paramètres transmis à la fonction (2e argument), interpolés avec le contexte.
class PythonScript(Block):
    def __init__(self, block_uid:str, config:dict, on_success_block:str=None, on_error_block:str=None):
        super().__init__("PythonScript", block_uid, config, on_success_block=on_success_block, on_error_block=on_error_block)

    def execute(self, context:PipelineContext):
        #Le chemin du script n'est volontairement pas interpolé : une donnée du contexte (ex : payload du
        #trigger) ne doit pas pouvoir choisir le code exécuté
        script = self._config.get("script")
        function = context.getConfig(key="function", default="run")
        params = context.getConfig(key="params", default={})

        if not isinstance(script, str) or script == "":
            Logger.write(f"[Block PythonScript] Missing 'script' parameter", type=ERROR)
            return False

        pipeline_dir = self._pipeline_dir.resolve()
        path = (pipeline_dir / script).resolve()
        if not path.is_relative_to(pipeline_dir) or path.suffix != ".py":
            Logger.write(f"[Block PythonScript] Script '{script}' must be a .py file inside the pipeline directory", type=ERROR)
            return False
        if not path.is_file():
            Logger.write(f"[Block PythonScript] Script '{script}' does not exist", type=ERROR)
            return False

        #Module chargé hors de sys.modules : chaque exécution repart d'un état neuf, sans collision entre pipelines
        try:
            spec = importlib.util.spec_from_file_location(f"pipeline_script_{self.getUid()}", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            Logger.write(f"[Block PythonScript] Failed to load '{script}' : {type(e).__name__} : {e}", type=ERROR)
            return False

        func = getattr(module, function, None)
        if not callable(func):
            Logger.write(f"[Block PythonScript] Function '{function}' not found in '{script}'", type=ERROR)
            return False

        try:
            result = func(context, params)
        except Exception as e:
            Logger.write(f"[Block PythonScript] '{script}' raised {type(e).__name__} : {e}", type=ERROR)
            return False

        if result is False:
            Logger.write(f"[Block PythonScript] '{script}' returned False", type=ERROR)
            return False

        Logger.write(f"[Block PythonScript] '{script}' executed", type=OK)
        return True
