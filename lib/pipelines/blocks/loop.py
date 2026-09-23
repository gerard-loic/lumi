from lib.pipelines.block import Block
from lib.pipelines.pipelinecontext import PipelineContext
from lib.log.logger import Logger, ERROR, OK

#Bloc Loop : boucle sur les lignes d'une liste du contexte (typiquement la sortie d'un bloc
#DataView en as="list"), en écrivant la ligne courante dans le contexte à chaque itération. Le
#corps de boucle se branche via "on_success" et doit reboucler vers ce même bloc (même block_uid)
#pour passer à la ligne suivante. Une fois toutes les lignes parcourues, le bloc échoue et sort par
#"on_error" : c'est la sortie normale de fin de boucle, pas une erreur d'exécution.
#
#L'avancement (index courant) est conservé dans le contexte, jamais sur l'instance du bloc : une
#même instance (cf. Pipeline._loadBlocks, un seul objet par block_uid) est partagée par tous les
#runs concurrents du pipeline, alors que le contexte est propre à un run (cf. PipelineRunner._run).
#
#Paramètres de configuration (clé "config" du bloc) :
#  - input  (str, obligatoire)     : clé du contexte contenant la liste de lignes à parcourir.
#  - item   (str, défaut "item")   : clé du contexte recevant la ligne courante à chaque itération.
#  - index  (str, défaut "index")  : clé du contexte recevant l'index courant (0-based).
class Loop(Block):
    def __init__(self, block_uid:str, config:dict, on_success_block:str=None, on_error_block:str=None):
        super().__init__("Loop", block_uid, config, on_success_block=on_success_block, on_error_block=on_error_block)

    def execute(self, context:PipelineContext):
        input_key = context.getConfig(key="input", default="")
        item_key  = context.getConfig(key="item", default="item")
        index_key = context.getConfig(key="index", default="index")
        #Clé d'état privée à cette instance de bloc, isolée dans le contexte du run courant.
        state_key = f"_loop_state_{self.getUid()}"

        if not input_key:
            Logger.write("[Block Loop] Missing 'input' in config", type=ERROR)
            return False

        try:
            rows = context.get(key=input_key)
        except KeyError:
            Logger.write(f"[Block Loop] Context key '{input_key}' not found", type=ERROR)
            return False

        if not isinstance(rows, list):
            Logger.write(f"[Block Loop] Input '{input_key}' must be a list", type=ERROR)
            return False

        try:
            position = context.get(key=state_key)
        except KeyError:
            position = 0

        if position >= len(rows):
            #Fin de boucle : on réinitialise l'état pour permettre une réutilisation ultérieure du
            #même bloc dans le run (ex. boucle rejouée plus loin dans le pipeline), et on sort par
            #on_error, qui matérialise ici la fin normale de la boucle.
            context.set(state_key, 0)
            Logger.write(f"[Block Loop] Loop finished ({len(rows)} row(s))", type=OK)
            return False

        context.set(item_key, rows[position])
        context.set(index_key, position)
        context.set(state_key, position + 1)

        Logger.write(f"[Block Loop] Row {position + 1}/{len(rows)} -> '{item_key}'", type=OK)
        return True
