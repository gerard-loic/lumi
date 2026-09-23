from lib.pipelines.block import Block
from lib.pipelines.pipelinecontext import PipelineContext
from lib.pipelines.utils.dataview import DataView as _DataView, OPERATORS
from lib.log.logger import Logger, ERROR, OK


#Dict tolérant aux clés absentes pour str.format_map : une variable inconnue du template
#(colonne manquante sur la ligne) est rendue comme chaine vide plutot que de lever KeyError.
class _SafeDict(dict):
    def __missing__(self, key):
        return ""


#Bloc DataView : construit une vue tabulaire manipulable (lib/pipelines/utils/dataview.py) à partir
#d'un dict ou d'une liste du contexte, lui applique une suite ordonnée d'opérations décrites en
#configuration, puis réécrit le résultat dans le contexte (liste ou dict).
#
#Paramètres de configuration (clé "config" du bloc) :
#  - input        (str,  obligatoire)     : clé du contexte contenant le dict ou la liste source.
#  - key_column   (str,  défaut "key")    : nom de colonne recevant la clé quand la source est un dict.
#  - value_column (str,  défaut "value")  : nom de colonne recevant la valeur pour une source de scalaires.
#  - operations   (list, défaut [])       : opérations appliquées dans l'ordre (voir ci-dessous).
#  - as           (str,  défaut "list")   : "list" -> liste de lignes ; "dict" -> voir "key".
#  - key          (str,  défaut None)     : si as="dict" + key -> {ligne[key]: ligne} ;
#                                           si as="dict" sans key -> forme colonnaire {colonne: [valeurs]}.
#  - flatten      (bool, défaut False)    : si as="list" et une seule colonne -> liste de scalaires.
#  - output       (str,  défaut "result") : clé du contexte où stocker le résultat.
#
#Opérations supportées (chaque entrée de "operations" est un dict avec une clé "op") :
#  - {"op":"filter","where":[[champ,op,val],...],"match":"all"|"any"} : conserve les lignes qui valident.
#  - {"op":"drop_rows","where":[...],"match":...}                     : supprime les lignes qui valident.
#  - {"op":"drop_rows","indices":[0,-1]}                              : supprime des lignes par position.
#  - {"op":"add_rows","rows":[{...},...]}                             : ajoute des lignes.
#  - {"op":"order","by":"champ"|["a","b"],"desc":false}               : trie (alias "sort").
#  - {"op":"drop_columns","columns":["a","b"]}                        : supprime des colonnes.
#  - {"op":"select","columns":["a","b"]}                              : ne conserve que ces colonnes (ordre inclus).
#  - {"op":"rename_column","from":"a","to":"b"}                       : renomme une colonne.
#  - {"op":"add_column","name":"x","value":<const>}                   : ajoute une colonne constante.
#  - {"op":"add_column","name":"label","template":"{nom} ({age})"}    : ajoute une colonne calculée par ligne.
#
#Opérateurs de "where" : == != > < >= <= in "not in" contains startswith endswith.
#
#Interpolation : les chaines de "operations" sont interpolées avec le contexte au moment de
#l'application (variables {ma_var}, boucles/conditions), à l'exception de la clé "template" d'un
#add_column, dont les {colonne} sont résolus ligne par ligne (colonne absente -> chaine vide).
class DataView(Block):
    def __init__(self, block_uid:str, config:dict, on_success_block:str=None, on_error_block:str=None):
        super().__init__("DataView", block_uid, config, on_success_block=on_success_block, on_error_block=on_error_block)

    def execute(self, context:PipelineContext):
        input_key    = context.getConfig(key="input", default="")
        key_column   = context.getConfig(key="key_column", default="key")
        value_column = context.getConfig(key="value_column", default="value")
        #operations est lu brut (self._config) : getConfig interpolerait les chaines, or la clé
        #"template" d'un add_column contient volontairement des "{colonne}" destinés au rendu
        #par ligne, pas au contexte. L'interpolation contexte est appliquée champ par champ dans
        #_apply, en épargnant "template".
        operations   = self._config.get("operations", []) or []
        output_as    = str(context.getConfig(key="as", default="list")).lower()
        dict_key     = context.getConfig(key="key", default=None)
        flatten      = context.getConfig(key="flatten", default=False)
        output       = context.getConfig(key="output", default="result")

        if not input_key:
            Logger.write("[Block DataView] Missing 'input' in config", type=ERROR)
            return False

        try:
            source = context.get(key=input_key)
        except KeyError:
            Logger.write(f"[Block DataView] Context key '{input_key}' not found", type=ERROR)
            return False

        if not isinstance(source, (list, dict)):
            Logger.write(f"[Block DataView] Input '{input_key}' must be a list or a dict", type=ERROR)
            return False

        view = _DataView.from_data(source, key_column=key_column, value_column=value_column)

        try:
            for step in operations:
                self._apply(context, view, step)
        except (ValueError, TypeError, KeyError, IndexError) as e:
            Logger.write(f"[Block DataView] Invalid operation : {e}", type=ERROR)
            return False

        result = view.to_dict(key=dict_key) if output_as == "dict" else view.to_list(flatten=bool(flatten))
        context.set(output, result)

        Logger.write(f"[Block DataView] {len(view)} row(s), {len(view.columns)} column(s) -> '{output}'", type=OK)
        return True

    #Applique une opération unique à la vue. Lève ValueError/TypeError/KeyError sur config invalide,
    #interceptées par execute pour faire échouer proprement le bloc. Les chaines de l'opération sont
    #interpolées avec le contexte, sauf la clé "template" (rendue par ligne, cf. _apply add_column).
    def _apply(self, context, view, step):
        if not isinstance(step, dict) or "op" not in step:
            raise ValueError(f"opération invalide : {step!r}")
        step = {k: (v if k == "template" else self._interpolate(context, v)) for k, v in step.items()}
        op = str(step["op"]).lower()

        if op == "filter":
            view.filter(self._predicate(step))
        elif op == "drop_rows":
            if "indices" in step:
                view.drop_rows(indices=[int(i) for i in step["indices"]])
            else:
                view.drop_rows(predicate=self._predicate(step))
        elif op == "add_rows":
            view.add_rows(step.get("rows", []))
        elif op in ("order", "sort"):
            view.order_by(step.get("by", []), desc=bool(step.get("desc", False)))
        elif op == "drop_columns":
            view.drop_columns(step.get("columns", []))
        elif op == "select":
            view.select(step.get("columns", []))
        elif op == "rename_column":
            view.rename_column(step["from"], step["to"])
        elif op == "add_column":
            name = step["name"]
            if "template" in step:
                template = step["template"]
                view.add_column(name, lambda row, t=template: t.format_map(_SafeDict(row)))
            else:
                view.add_column(name, step.get("value"))
        else:
            raise ValueError(f"opération inconnue : {op}")

    #Interpole récursivement les chaines (chaine / dict / list) avec le contexte, comme le fait
    #ApiRequest : getConfig ne transforme que les chaines de premier niveau.
    def _interpolate(self, context, value):
        if isinstance(value, str):
            return context.transform(text=value)
        if isinstance(value, dict):
            return {k: self._interpolate(context, v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._interpolate(context, v) for v in value]
        return value

    #Construit un prédicat callable(row) -> bool à partir des clauses "where" [[champ, op, valeur], ...].
    #match="all" (défaut) -> ET logique ; match="any" -> OU logique.
    def _predicate(self, step):
        match = str(step.get("match", "all")).lower()
        compiled = []
        for clause in step.get("where", []) or []:
            if not isinstance(clause, (list, tuple)) or len(clause) != 3:
                raise ValueError(f"clause 'where' invalide : {clause!r}")
            field, clause_op, value = clause
            test = OPERATORS.get(str(clause_op))
            if test is None:
                raise ValueError(f"opérateur non supporté : {clause_op}")
            compiled.append((field, test, value))

        def predicate(row):
            results = [test(row.get(field), value) for field, test, value in compiled]
            return any(results) if match == "any" else all(results)

        return predicate
