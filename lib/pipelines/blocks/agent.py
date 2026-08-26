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

class Agent(Block):
    def __init__(self, config:dict, next_block:str=None):
        super().__init__("Agent", config, next_block)

    def execute(self, context:PipelineContext):
        profile_name  = self._config.get("profile", "default")
        prompt        = self._config.get("prompt", "")
        authorization = self._config.get("authorization", {})

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
            result = asyncio.run_coroutine_threadsafe(agent.reflect(prompt), mcp_manager.loop).result()
        except Exception as e:
            Logger.write(f"[Block Agent] LLM reflection failed : {e}", type=ERROR)
            return False
        finally:
            AuthSessionManager.remove(session_id)

        context.set("result", result)
        return True