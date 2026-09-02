import asyncio
from lib.pipelines.block import Block
from lib.pipelines.pipelinecontext import PipelineContext
from lib.agent.agent import AgentManager
from lib.http.auth import Auth
from lib.mcp.client import mcp_manager
from lib.session.session import AuthSessionManager
from lib.localization.language import LanguageManager
from lib.config.config import Config
from lib.log.logger import Logger, ERROR

#Bloc Agent : déclenche une réflexion LLM (agent.reflect) à partir d'un prompt et écrit le résultat dans le contexte.
#
#Paramètres de configuration (clé "config" du bloc) :
#  - profile       (str,  défaut "default")        : nom du profil agent à charger (cf. AgentManager), définit le modèle LLM et les services/credentials associés.
#  - prompt        (str,  défaut "")               : prompt transmis à l'agent ; les variables de contexte y sont interpolées en amont.
#  - authorization (dict, défaut {})               : paramètres d'authentification du service (cf. Auth.authenticate), utilisés pour ouvrir la session MCP dédiée au bloc.
#  - language      (str,  défaut app.default_language) : code langue de la session (cf. LanguageManager).
#  - output        (str,  défaut "result")         : clé du contexte où stocker la réponse de l'agent.
class Agent(Block):
    def __init__(self, block_uid:str, config:dict, on_success_block:str=None, on_error_block:str=None):
        super().__init__("Agent", block_uid, config, on_success_block=on_success_block, on_error_block=on_error_block)

    def execute(self, context:PipelineContext):
        profile_name  = self._config.get("profile", "default")
        prompt        = self._config.get("prompt", "")
        authorization = self._config.get("authorization", {})
        output = self.getConfig(key="output", default="result")

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

        try:
            #Le bloc s'exécute dans un thread dédié au pipeline (cf. PipelineRunner), sans boucle événementielle
            #propre. La session MCP (cf. mcp_manager) est liée à la boucle FastAPI : on y planifie donc reflect()
            #plutôt que de le lancer via asyncio.run() dans ce thread, qui créerait une boucle isolée et bloquerait
            #indéfiniment les appels d'outils MCP faits par reflect() (attente sur une primitive d'une autre boucle).
            #run_coroutine_threadsafe recopie le contexte courant (contextvars) vers la coroutine : c'est ce qui
            #permet à Logger.capture() (cf. PipelineRunner._executeBlock) de récupérer les logs émis par reflect()
            #depuis le thread de la boucle MCP. Ne pas remplacer par un mécanisme qui perdrait cette propagation.
            result = asyncio.run_coroutine_threadsafe(agent.reflect(prompt), mcp_manager.loop).result()
        except Exception as e:
            Logger.write(f"[Block Agent] LLM reflection failed : {e}", type=ERROR)
            return False
        finally:
            AuthSessionManager.remove(session_id)

        context.set(output, result)
        return True