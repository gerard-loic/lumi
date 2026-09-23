from lib.pipelines.block import Block
from lib.pipelines.pipelinecontext import PipelineContext
from lib.pipelines.utils.condition import evaluate, ConditionError
from lib.log.logger import Logger, ERROR, OK

#Bloc Condition : évalue une expression booléenne portant sur des variables de contexte et branche
#le pipeline selon le résultat (on_success si vrai, on_error si faux). Le booléen est aussi écrit
#dans le contexte pour être réutilisé plus loin (ex. dans un "{% if %}").
#
#L'expression n'est PAS interpolée : on y référence une variable par son chemin nu
#(trigger.data.role) ou entre accolades ({trigger.data.role}), et les chaines littérales sont entre
#guillemets. Voir lib/pipelines/utils/condition.py pour la grammaire complète.
#
#  - opérateurs de comparaison : =  ==  !=  <>  <  >  <=  >=  IN  "NOT IN"
#  - opérateurs logiques : AND  OR  NOT   + groupements par parenthèses
#  - opérandes : "chaine", nombre, true/false, none/null, [liste], chemin de variable
#
#Paramètres de configuration (clé "config" du bloc) :
#  - expression      (str,  obligatoire)  : l'expression à évaluer.
#                                           Ex. "trigger.data.age >= 18 AND (role == 'admin' OR
#                                           status IN ['active', 'trial'])".
#  - missing_as_null (bool, défaut False) : True  -> une variable de contexte absente vaut none ;
#                                           False -> une variable absente fait échouer le bloc.
#  - fail_on_false   (bool, défaut True)  : True  -> le bloc échoue quand l'expression est fausse
#                                           (branchement via "on_error") ;
#                                           False -> le bloc réussit toujours, le résultat se lit
#                                           dans le contexte ("{<output>}").
#  - output          (str,  défaut "result") : clé du contexte où stocker le booléen résultat.
class Condition(Block):
    def __init__(self, block_uid:str, config:dict, on_success_block:str=None, on_error_block:str=None):
        super().__init__("Condition", block_uid, config, on_success_block=on_success_block, on_error_block=on_error_block)

    def execute(self, context:PipelineContext):
        #expression lue brute (self._config) : l'interpolation substituerait les valeurs en texte et
        #casserait l'analyse ; les chemins de variables sont résolus par l'évaluateur, en typé.
        expression      = self._config.get("expression", "")
        missing_as_null = bool(context.getConfig(key="missing_as_null", default=False))
        fail_on_false   = bool(context.getConfig(key="fail_on_false", default=True))
        output          = context.getConfig(key="output", default="result")

        if not isinstance(expression, str) or expression.strip() == "":
            Logger.write("[Block Condition] Missing 'expression' in config", type=ERROR)
            return False

        def resolver(path):
            try:
                return context.resolve(path)
            except (KeyError, IndexError, ValueError, TypeError):
                if missing_as_null:
                    return None
                raise ConditionError(f"variable de contexte introuvable : {path}")

        try:
            result = evaluate(expression, resolver)
        except ConditionError as e:
            Logger.write(f"[Block Condition] {e}", type=ERROR)
            return False

        context.set(output, result)
        Logger.write(f"[Block Condition] {expression.strip()!r} -> {result}", type=OK)

        return result or not fail_on_false
