import asyncio
from lib.pipelines.block import Block
from lib.pipelines.pipelinecontext import PipelineContext
from lib.agent.agent import AgentManager
from lib.http.auth import Auth
from lib.mcp.client import mcp_manager
from lib.session.session import AuthSessionManager
from lib.files.filestore import FileStore
from lib.localization.language import LanguageManager
from lib.config.config import Config
from lib.log.logger import Logger, ERROR

#Bloc Agent : déclenche une réflexion LLM (agent.reflect) à partir d'un prompt et écrit le résultat dans le contexte.
#
#Paramètres de configuration (clé "config" du bloc) :
#  - profile       (str,  défaut "default")        : nom du profil agent à charger (cf. AgentManager), définit le modèle LLM et les services/credentials associés.
#  - prompt        (str,  défaut "")               : prompt transmis à l'agent ; les variables de contexte y sont interpolées en amont.
#  - authorization (dict, défaut {})               : paramètres d'authentification du service (cf. Auth.authenticate), utilisés pour ouvrir la session MCP dédiée au bloc.
#  - auto_confirm  (bool, défaut False)            : si True, les outils MCP nécessitant une confirmation utilisateur (cf. @confirmation_tool)
#                                                    sont exécutés sans validation au lieu d'être refusés. À réserver aux pipelines de confiance :
#                                                    ces outils ont des effets de bord non triviaux (envoi de mail, suppression, écritures externes...).
#  - language      (str,  défaut app.default_language) : code langue de la session (cf. LanguageManager).
#  - output        (str,  défaut "result")         : clé du contexte où stocker la réponse de l'agent.
#  - files_output  (str,  défaut "files")          : clé du contexte où stocker les fichiers produits par les outils MCP
#                                                    pendant la réflexion (liste de {"key","filename","path"}). Ils restent
#                                                    disponibles pour les blocs suivants et sont purgés en fin de pipeline.
class Agent(Block):
    def __init__(self, block_uid:str, config:dict, on_success_block:str=None, on_error_block:str=None):
        super().__init__("Agent", block_uid, config, on_success_block=on_success_block, on_error_block=on_error_block)

    def execute(self, context:PipelineContext):
        #Récupération de la configuration
        profile_name = context.getConfig(key="profile", default="")
        prompt = context.getConfig(key="prompt", default="")
        authorization = context.getConfig(key="authorization", default={})
        auto_confirm = context.getConfig(key="auto_confirm", default=False)
        output  = context.getConfig(key="output", default="result")
        files_output = context.getConfig(key="files_output", default="files")

        Logger.write("PROMPT ::::::::::::::::")
        Logger.write(prompt)
       
        agent = AgentManager.getAgent(name=profile_name)
        if agent is None:
            Logger.write(f"[Block Agent] Profile {profile_name} not available", type=ERROR)
            return False

        #Authentification dédiée à cette session LLM : chaque bloc Agent peut porter sur un profil
        #(et donc des services/credentials) différent, la session est donc ouverte et fermée ici plutôt
        #qu'au niveau du pipeline. C'est elle qui permet aux outils MCP appelés pendant reflect()
        #d'accéder à une authentification de service valide (cf. lib/mcp/toolloader.py).
        language = LanguageManager.getLanguage(code=self._config.get("language", Config.get("app.default_language")))
        token = Auth.authenticate(authorization=authorization, profile=profile_name, language=language)
        if not token:
            Logger.write(f"[Block Agent] Authentification failed for profile {profile_name}", type=ERROR)
            return False
        session_id = AuthSessionManager.get_current_id()

        #Instantané des fichiers déjà rattachés au run : ce qui apparaît en plus après reflect() a été
        #produit par un outil MCP pendant cette réflexion. Le scope "pipeline:<id>" est propagé jusqu'aux
        #outils (cf. lib/mcp), donc ces fichiers appartiennent au run et survivent au retrait de la
        #sous-session ci-dessous ; ils seront purgés en fin de pipeline.
        file_scope = FileStore.current_scope()
        files_before = FileStore.scope_keys(file_scope)

        try:
            #Le bloc s'exécute dans un thread dédié au pipeline (cf. PipelineRunner), sans boucle événementielle
            #propre. La session MCP (cf. mcp_manager) est liée à la boucle FastAPI : on y planifie donc reflect()
            #plutôt que de le lancer via asyncio.run() dans ce thread, qui créerait une boucle isolée et bloquerait
            #indéfiniment les appels d'outils MCP faits par reflect() (attente sur une primitive d'une autre boucle).
            #run_coroutine_threadsafe recopie le contexte courant (contextvars) vers la coroutine : c'est ce qui
            #permet à Logger.capture() (cf. PipelineRunner._executeBlock) de récupérer les logs émis par reflect()
            #depuis le thread de la boucle MCP. Ne pas remplacer par un mécanisme qui perdrait cette propagation.
            result = asyncio.run_coroutine_threadsafe(agent.reflect(prompt, auto_confirm=auto_confirm), mcp_manager.loop).result()
        except Exception as e:
            Logger.write(f"[Block Agent] LLM reflection failed : {e}", type=ERROR)
            return False
        finally:
            AuthSessionManager.remove(session_id)

        produced = [
            {**entry, "path": FileStore.path(entry["key"])}
            for entry in FileStore.scope_entries(file_scope)
            if entry["key"] not in files_before
        ]
        context.set(files_output, produced)
        context.set(output, result)
        return True