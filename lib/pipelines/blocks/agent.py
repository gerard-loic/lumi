import re
import asyncio
from lib.pipelines._abstract import Block
from lib.pipelines.pipelinecontext import PipelineContext
from lib.agent.agent import AgentManager
from lib.mcp.client import mcp_manager
from lib.process.processmanager import ProcessManager
from lib.process.agentcontext import AgentContext
from lib.files.filestore import FileStore
from lib.localization.language import LanguageManager
from lib.config.config import Config
from lib.log.logger import Logger, ERROR

#Bloc Agent : déclenche une réflexion LLM (agent.reflect) à partir d'un prompt et écrit le résultat dans le contexte.
#
#Paramètres de configuration (clé "config" du bloc) :
#  - profile       (str,  défaut "default")        : nom du profil agent à charger (cf. AgentManager), définit le modèle LLM et les services/credentials associés.
#  - prompt        (str,  défaut "")               : prompt transmis à l'agent ; les variables de contexte y sont interpolées en amont.
#  - auto_confirm  (bool, défaut False)            : si True, les outils MCP nécessitant une confirmation utilisateur (cf. @confirmation_tool)
#                                                    sont exécutés sans validation au lieu d'être refusés. À réserver aux pipelines de confiance :
#                                                    ces outils ont des effets de bord non triviaux (envoi de mail, suppression, écritures externes...).
#  - language      (str,  défaut app.default_language) : code langue de la session (cf. LanguageManager).
#  - output        (str,  défaut "result")         : clé du contexte où stocker la réponse de l'agent.
#  - files_output  (str,  défaut "files")          : clé du contexte où stocker les fichiers produits par les outils MCP
#                                                    pendant la réflexion (liste de {"key","filename","path"}). Ils restent
#                                                    disponibles pour les blocs suivants et sont purgés en fin de pipeline.
#  - micro_rag       (str|list, défaut None)       : fichiers préparés par un ou plusieurs blocs MicroRag, sous la forme d'une
#                                                    référence de contexte "{var}" (ou d'une liste de références). Ils sont joints
#                                                    à la réflexion : leur contenu complet ou leurs extraits les plus pertinents
#                                                    sont ajoutés au prompt, selon micro_rag_mode.
#  - micro_rag_mode  (str,  défaut profil)         : "rag" (extraits), "full" (texte complet) ou "auto" (texte complet si le
#                                                    total tient dans micro_rag_max_tokens, extraits sinon). Défaut :
#                                                    attachments.mode du profil, sinon "auto" (cf. AttachmentRetriever).
#  - micro_rag_max_tokens (int, défaut profil)     : seuil du mode "auto" (défaut : attachments.full_text_max_tokens du profil,
#                                                    sinon 20000).
#  - micro_rag_query (str,  défaut prompt)         : requête de recherche des extraits, si le prompt (souvent une consigne)
#                                                    n'est pas représentatif de l'information à retrouver.
#  - micro_rag_top_k (int,  défaut profil)         : nombre d'extraits ajoutés au prompt (défaut : attachments.file_context_top_k
#                                                    du profil, sinon 8).
class Agent(Block):
    _SINGLE_TOKEN_RE = re.compile(r'^\s*\{([\w\.\[\]]+)\}\s*$')

    def __init__(self, block_uid:str, config:dict, on_success_block:str=None, on_error_block:str=None):
        super().__init__("Agent", block_uid, config, on_success_block=on_success_block, on_error_block=on_error_block)

    def execute(self, context:PipelineContext):
        #Récupération de la configuration
        profile_name = context.getConfig(key="profile", default="")
        prompt = context.getConfig(key="prompt", default="")
        auto_confirm = context.getConfig(key="auto_confirm", default=False)
        output  = context.getConfig(key="output", default="result")
        files_output = context.getConfig(key="files_output", default="files")
        micro_rag_query = context.getConfig(key="micro_rag_query", default=None) or None
        micro_rag_top_k = context.getConfig(key="micro_rag_top_k", default=None)
        micro_rag_mode  = context.getConfig(key="micro_rag_mode", default=None) or None
        micro_rag_max_tokens = context.getConfig(key="micro_rag_max_tokens", default=None)

        try:
            attachments = self._resolveMicroRag(self._config.get("micro_rag"), context)
        except (KeyError, IndexError, ValueError) as e:
            Logger.write(f"[Block Agent] Invalid micro_rag reference : {e}", type=ERROR)
            return False

        agent = AgentManager.getAgent(name=profile_name)
        if agent is None:
            Logger.write(f"[Block Agent] Profile {profile_name} not available", type=ERROR)
            return False

        #Process dédié à cette réflexion, enfant du process du run : il porte le contexte agent propre au bloc
        #(profil, langue) et hérite du wallet du pipeline (services déclarés dans la config du pipeline, cf.
        #PipelineRunner). Les outils MCP appelés pendant reflect() y accèdent via lumi_session_id (cf. lib/mcp).
        language = LanguageManager.getLanguage(code=self._config.get("language", Config.get("app.default_language")))
        process, process_token = ProcessManager.start(parent=ProcessManager.getCurrent())
        agent_ctx = AgentContext(profile=profile_name, language=language)
        for attachment in attachments:
            agent_ctx.addAttachment(attachment["key"], attachment["filename"], attachment["text"], attachment["tokens"], pages=attachment.get("pages"))
            if attachment.get("chunks") is not None:
                agent_ctx.cacheAttachmentChunks(attachment["key"], attachment["chunks"], attachment.get("embedding_model"))
        process.setAgentContext(agent_ctx)

        #Instantané des fichiers déjà rattachés au run : ce qui apparaît en plus après reflect() a été
        #produit par un outil MCP pendant cette réflexion. Les fichiers sont rattachés à la racine (le run),
        #donc ils survivent au retrait du process du bloc ci-dessous ; ils seront purgés en fin de pipeline.
        run = process.getRoot()
        files_before = {entry["key"] for entry in run.getFiles()}

        try:
            #Le bloc s'exécute dans un thread dédié au pipeline (cf. PipelineRunner), sans boucle événementielle
            #propre. La session MCP (cf. mcp_manager) est liée à la boucle FastAPI : on y planifie donc reflect()
            #plutôt que de le lancer via asyncio.run() dans ce thread, qui créerait une boucle isolée et bloquerait
            #indéfiniment les appels d'outils MCP faits par reflect() (attente sur une primitive d'une autre boucle).
            #run_coroutine_threadsafe recopie le contexte courant (contextvars) vers la coroutine : c'est ce qui
            #permet à Logger.capture() (cf. PipelineRunner._executeBlock) de récupérer les logs émis par reflect()
            #depuis le thread de la boucle MCP. Ne pas remplacer par un mécanisme qui perdrait cette propagation.
            result = asyncio.run_coroutine_threadsafe(agent.reflect(
                prompt, auto_confirm=auto_confirm,
                attachment_query=micro_rag_query,
                attachment_top_k=int(micro_rag_top_k) if micro_rag_top_k not in (None, "") else None,
                attachment_mode=micro_rag_mode,
                attachment_max_tokens=int(micro_rag_max_tokens) if micro_rag_max_tokens not in (None, "") else None,
            ), mcp_manager.loop).result()
        except Exception as e:
            Logger.write(f"[Block Agent] LLM reflection failed : {e}", type=ERROR)
            return False
        finally:
            ProcessManager.exit(process_token)
            ProcessManager.remove(process.getUid())
            #Embeddings calculés pendant la réflexion (cf. AttachmentRetriever, cache de l'AgentContext) : recopiés, avec
            #le modèle qui les a produits, dans les fichiers du contexte de pipeline pour que les blocs Agent suivants
            #n'aient pas à les recalculer (sauf s'ils utilisent un autre modèle d'embedding)
            cached = {a["key"]: a for a in agent_ctx.getAttachments()}
            for attachment in attachments:
                computed = cached.get(attachment["key"])
                if computed and computed["chunks"] is not None and computed["chunks"] is not attachment.get("chunks"):
                    attachment["chunks"] = computed["chunks"]
                    attachment["embedding_model"] = computed["embedding_model"]

        produced = [
            {**entry, "path": FileStore.path(entry["key"])}
            for entry in run.getFiles()
            if entry["key"] not in files_before
        ]
        context.set(files_output, produced)
        context.set(output, result)
        return True

    #Résout la clé "micro_rag" en liste de pièces jointes préparées par des blocs MicroRag. Les références
    #"{var}" sont résolues sans passer par le moteur de template, qui sérialiserait la structure en chaine.
    def _resolveMicroRag(self, value, context:PipelineContext)->list:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [a for item in value for a in self._resolveMicroRag(item, context)]
        if isinstance(value, dict):
            if "text" not in value or "filename" not in value:
                raise ValueError(f"not a MicroRag file : keys {list(value)}")
            return [value]
        if isinstance(value, str):
            token = self._SINGLE_TOKEN_RE.match(value)
            if token is None:
                raise ValueError(f"'{value}' is not a context reference like \"{{var}}\"")
            return self._resolveMicroRag(context.resolve(token.group(1)), context)
        raise ValueError(f"unsupported value {value!r}")
