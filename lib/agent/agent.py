import json
from contextlib import AsyncExitStack
from typing import AsyncGenerator
from lib.mcp.client import mcp_manager, MCPToolError
from lib.mcp.toolloader import MCPTool
from lib.agent.events import TokenEvent, DoneEvent, ToolEvent, ThinkingEvent, ErrorEvent, ConfirmationEvent, ConfirmationRefusedEvent, FollowUpEvent, RagEvent
from lib.agent.eventshelper import RagAccumulator
from lib.rag.attachmentretriever import AttachmentRetriever
from lib.log.logger import Logger, ERROR, OK, WARNING
from lib.files.localdata import LocalData
from lib.agent.filtershelper import LLMFilterManager
import datetime
from lib.utils.dynamicimport import DynamicImport
from lib.agent.profile import ProfileManager, Profile
from lib.localization.traduction import Traduction
from lib.utils.uuid import Uuid
from lib.process.processmanager import ProcessManager
from lib.process.process import Process

"""
Agent — Agent d'orchestration / communication LLM
Stratégie :
1. Appel LiteLLM NON streamé pour détecter les tool calls
2. Exécution des tools via MCP si nécessaire
3. Appel LiteLLM STREAMÉ réponse finale token par token
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Agent:
    #Constructeur d'un agent. Connector:la classe llmConnecteor utilisée, profile:le profile utilisé
    def __init__(self, connector:str, profile:Profile):
        self.profile = profile

        #Initialisation du connecteur LLM
        self._connector = DynamicImport.getInstance(
            className=connector,
            moduleName=connector,
            classPath="lib.agent.llmconnector",
            config=self.profile.getConfigValue(f"llm.{connector}"),
            tools_enabled=self.profile.getConfigValue(key="mcp.tools_enabled", default=[]),
        )
      
        #Prompt systeme (issu du fichier de configuration ou d'un fichier joint)
        system_prompt_file = self.profile.getConfigValue(key="llm.system_prompt_file", default=None)
        system_prompt      = self.profile.getConfigValue(key="llm.system_prompt", default=None)
        if system_prompt_file:
            with open(system_prompt_file, encoding="utf-8") as f:
                self._system = f.read()
        elif system_prompt:
            self._system = system_prompt
        else:
            Logger.write(f"[AGENT {profile.getName()}] LLM system prompt not configured: set 'profile.{self.profile.getName()}.system_prompt_file' or 'llm.{self.profile.getName()}.system_prompt' in config.", ERROR)
            raise Exception(f"[AGENT {profile.getName()}] LLM system prompt not configured: set 'llm.{self.profile.getName()}.system_prompt_file' or 'llm.{self.profile.getName()}.system_prompt' in config.")

        #Si aucun outil n'est disponible pour ce profil, on neutralise les consignes du prompt système
        #qui imposeraient d'appeler un outil (sinon le LLM tente d'en simuler un en texte, faute de mieux).
        if not self._connector.has_tools():
            self._system += "\n\nAucun outil n'est disponible dans ce contexte : ne mentionne, ne simule et n'invoque jamais un appel d'outil, quelles que soient les autres consignes ci-dessus. Réponds uniquement à partir de la conversation, ou indique que tu n'as pas accès à cette information."

        #Configuration issue du profile
        self._MAX_TOOL_ITERATIONS          = self.profile.getConfigValue(key="mcp.max_tool_iterations", default=10)
        self._MEMORY_MESSAGES              = self.profile.getConfigValue(key="llm.memory_messages", default=5)
        self._EMPTY_LLM_RESPONSE_MAX_RETRY = self.profile.getConfigValue(key="llm.empty_llm_response_max_retry", default=2)

        self._FOLLOWUP_ENABLED             = self.profile.getConfigValue(key="llm.followup_questions.enabled", default=True)
        self._FOLLOWUP_COUNT               = self.profile.getConfigValue(key="llm.followup_questions.count", default=3)

        #Filtres
        self.filters = LLMFilterManager(profile=self.profile)

        Logger.write(f"[AGENT {profile.getName()}] MCP agent initialized", type=OK)

    """
    Tour de conversation dans une session (process racine portant un AgentContext : session HTTP ou Webex)
    exclude_restricted : exclut les outils tagués avec le décorateur @restricted_tool
    """
    async def chatStream(self, message: str, session: Process, exclude_restricted: bool = False) -> AsyncGenerator[str, None]:
        #On filtre le message entrant (application des filtres selon les filtres actifs dans la conf)
        message = self.filters.filter(text=message)

        #Contexte conversationnel de la session
        agent_ctx = session.getAgentContext()
        if agent_ctx is None:
            Logger.write(f"[AGENT {self.profile.getName()}] Session {session.getUid()} has no conversation context", type=ERROR)
            yield ErrorEvent.get(error_code="SESSION_NOT_FOUND", message="Session not found or expired")
            yield DoneEvent.get()
            return

        #Language
        language = agent_ctx.getLanguage()
        t = Traduction(language=language)

        #Accumulateur des événements RAG de tout le tour de conversation (pré-recherche pièces jointes +
        #tool calls, sur toutes les itérations) : émis groupés une fois la réponse finale prête (voir plus bas)
        rag_sources = RagAccumulator()

        #Connexions aux serveurs MCP externes en auth "session" pour ce tour (cf.
        #MCPClientManager.open_session_external_tools) — tenues dans `turn_stack` et refermées dans le
        #`finally` ci-dessous, dans la même tâche asyncio que celle qui les a ouvertes (contrainte des
        #transports MCP).
        turn_stack = AsyncExitStack()
        #Process du tour, enfant de la session : accessible via ProcessManager.getCurrent() par tout code exécuté
        #pendant ce tour (tool calls MCP internes, filtres...). Wallet, fichiers et contexte agent sont lus sur la session.
        process, process_token = ProcessManager.start(parent=session)
        try:
            session_tools, session_external_sessions = await mcp_manager.open_session_external_tools(turn_stack)

            #On récupère l'historique de conversation pour l'intégrer au prompt
            history = agent_ctx.getHistory()[-self._MEMORY_MESSAGES:]

            #Ajout de la date heure courante au prompt
            now = datetime.datetime.now()  # ou avec timezone si pertinent
            system = self._system + f"\n\nDate et heure actuelles : {now.strftime('%A %d %B %Y, %H:%M')} (heure locale)"

            #Modification de la variable de langue
            system = system.replace("%language%", language.getName())

            file_context = ""
            if self.profile.getConfigValue("attachments.enabled", default=False):
                #Si des fichiers sont joints, leur contenu est fourni d'office avec le message de l'utilisateur (fiabilité :
                #on ne compte pas sur le LLM pour décider d'appeler search_attached_files en premier) : texte complet ou
                #extraits du micro-RAG selon attachments.mode (cf. AttachmentRetriever.retrieve). Le tool reste disponible
                #pour que le modèle affine sa recherche avec une autre requête si besoin.
                #@TODO : comportement à modifier
                attachments = agent_ctx.getAttachments()
                if attachments:
                    filenames = ", ".join(a["filename"] for a in attachments)

                    current_call_uid = Uuid.get()
                    current_tool_uid = "agent_micro_rag"
                    current_tool_name = t.trad("[files.search_attached_files]")
                    yield ToolEvent.get(tool_uid=current_tool_uid, tool_name=current_tool_name, call_uid=current_call_uid, status="PENDING", long_call=True, message="")
                                        
                    try:
                        results, full = await AttachmentRetriever().retrieve(message)
                        yield ToolEvent.get(tool_uid=current_tool_uid, tool_name=current_tool_name, call_uid=current_call_uid, status="OK")
                    except Exception as e:
                        yield ToolEvent.get(tool_uid=current_tool_uid, tool_name=current_tool_name, call_uid=current_call_uid, status="ERROR", long_call=False, message=str(e))     
                        Logger.write(f"[AGENT] Attachment search failed : {str(e)}", type=ERROR)
                        results, full = [], False

                    system += AttachmentRetriever.instructions("Fichiers joints par l'utilisateur à cette conversation", filenames, full)
                    if results:
                        file_context = AttachmentRetriever.format_context(results, full)

                        for filename, pages in AttachmentRetriever.citations(results, full).items():
                            rag_sources.add(RagEvent.get(source=filename, locations=pages))

            user_content = f"{file_context}{message}" if file_context else message

            #Préparation des différents types de message pour le LLM
            messages = [
                {"role": "system", "content": system},
                *history,
                {"role": "user",   "content": user_content},
            ]

            Logger.write(f"[AGENT {self.profile.getName()}] Call LLM...", type=WARNING)
            # ----------------------------------------------------------------
            # ÉTAPE 1 — Appel non streamé pour détecter les tool calls
            # ----------------------------------------------------------------
            llm_call_uid = Uuid.get()
            llm_call_type = "INITIAL"
            yield ThinkingEvent.get(call_uid=llm_call_uid, call_type=llm_call_type, status="PENDING")

            for attempt in range(self._EMPTY_LLM_RESPONSE_MAX_RETRY):
                try:
                    response = await self._connector.callLLM(messages=messages, stream=False, exclude_restricted=exclude_restricted, extra_tools=session_tools)
                except Exception as e:
                    Logger.write(f"[AGENT {self.profile.getName()}] LLM call failure : {str(e)}", type=ERROR)
                    yield ThinkingEvent.get(call_uid=llm_call_uid, call_type=llm_call_type, status="ERROR", error_code="LLM_CALL_FAIL", message=str(e))
                    yield ErrorEvent.get(error_code="LLM_CALL_FAIL", message="LLM call failure", details=str(e))
                    yield DoneEvent.get()
                    return
                if response.choices:
                    break
                if attempt < self._EMPTY_LLM_RESPONSE_MAX_RETRY - 1:
                    Logger.write("[AGENT {self.profile.getName()}] LLM returned empty response, retrying...", type=WARNING)
            else:
                Logger.write("[AGENT] LLM returned empty response after retries", type=ERROR)
                yield ThinkingEvent.get(call_uid=llm_call_uid, call_type=llm_call_type, status="ERROR", error_code="EMPTY_RESPONSE", message="Empty LLM answer")
                yield ErrorEvent.get(error_code="EMPTY_RESPONSE", message="Empty LLM answer")
                yield DoneEvent.get()
                return
            assistant_msg = response.choices[0].message
            yield ThinkingEvent.get(call_uid=llm_call_uid, call_type=llm_call_type, status="OK")
            Logger.write("[AGENT {self.profile.getName()}] Call LLM OK !", type=OK)

            # ----------------------------------------------------------------
            # ÉTAPE 2 — Boucle de résolution des tool calls
            # ----------------------------------------------------------------
            iteration = 0
            while assistant_msg.tool_calls:
                iteration += 1
                if iteration > self._MAX_TOOL_ITERATIONS:
                    Logger.write("[AGENT {self.profile.getName()}] Too many consecutive tool calls", type=ERROR)
                    yield ErrorEvent.get(
                        error_code="MCP_TOOL_LIMIT_EXCEEDED",
                        message="Too many consecutive tool calls",
                        details=f"Limit : {self._MAX_TOOL_ITERATIONS} calls",
                    )
                    yield DoneEvent.get()
                    return

                messages.append({
                    "role": "assistant",
                    "content": assistant_msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in assistant_msg.tool_calls
                    ],
                })

                #Appels des outils MCP
                for tc in assistant_msg.tool_calls:
                    Logger.write(f"[AGENT {self.profile.getName()}] Call MCP tool {tc.function.name}...", type=WARNING)
                    meta = MCPTool.get_meta(tc.function.name)
                    description = meta.get("description", tc.function.name)
                    if description == False:
                        description = tc.function.name

                    #Traduction de la description
                    description = t.trad(description)

                    #Verifier si l'outil nécessite une confirmation préalable
                    if meta.get("confirmation", False):
                        options = meta.get("confirmation_options", [])
                        options = [t.trad(option) for option in options]
                        yield ConfirmationEvent.get(
                            question=t.trad(t.trad(meta.get("confirmation_question", ""))),
                            options=options
                        )
                        try:
                            answer = await agent_ctx.waitConfirmation()
                        except Exception:
                            answer = -1
                        if answer != meta.get("confirmation_validation_option", -1):
                            yield ConfirmationRefusedEvent.get()
                            yield DoneEvent.get()
                            return

                    #Avertit le client
                    current_call_uid = Uuid.get()
                    current_tool_uid = tc.function.name
                    current_tool_name = description
                    yield ToolEvent.get(tool_uid=current_tool_uid, tool_name=current_tool_name, call_uid=current_call_uid, status="PENDING", long_call=meta.get("slow", False), message="")
                    
                    #On essaie d'executer l'outil, si erreur on transmet l'erreur au LLM pour qu'il puisse en déduire la suite
                    try:
                        args = json.loads(tc.function.arguments)
                        result_text, tool_events = await mcp_manager.call_tool(
                            tc.function.name, args,
                            tools_enabled=self.profile.getConfigValue(key="mcp.tools_enabled", default=[]),
                            external_sessions=session_external_sessions,
                        )
                    except MCPToolError as e:
                        error_detail = str(e)
                        Logger.write(f"[AGENT {self.profile.getName()}] MCP tool {tc.function.name} error : {error_detail}", type=ERROR)
                        yield ToolEvent.get(tool_uid=current_tool_uid, tool_name=current_tool_name, call_uid=current_call_uid, status="ERROR", message=error_detail)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": f"Tool call failed: {error_detail}",
                        })
                        continue
                    except Exception as e:
                        error_detail = str(e)
                        Logger.write(f"[AGENT {self.profile.getName()}] MCP tool {tc.function.name} error : {error_detail}", type=ERROR)
                        yield ToolEvent.get(tool_uid=current_tool_uid, tool_name=current_tool_name, call_uid=current_call_uid, status="ERROR", message=error_detail)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": f"Tool call failed: {error_detail}",
                        })
                        continue

                    Logger.write(f"[AGENT {self.profile.getName()}] Call MCP tool {tc.function.name} OK !", type=OK)
                    yield ToolEvent.get(tool_uid=current_tool_uid, tool_name=current_tool_name, call_uid=current_call_uid, status="OK")

                    for event in tool_events:
                        if not rag_sources.add(event):
                            yield event

                    # Interception des actions spéciales — le LLM n'est pas rappelé
                    #TODO

                    #On ajoute aux messages le résultat de l'appel de l'outil
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_text,
                    })


                llm_call_uid = Uuid.get()
                llm_call_type = "TOOL"
                yield ThinkingEvent.get(call_uid=llm_call_uid, call_type=llm_call_type, status="PENDING")

                Logger.write("[AGENT {self.profile.getName()}] Call LLM...", type=WARNING)
                for attempt in range(self._EMPTY_LLM_RESPONSE_MAX_RETRY):
                    try:
                        response = await self._connector.callLLM(messages=messages, stream=False, exclude_restricted=exclude_restricted, extra_tools=session_tools)
                    except Exception as e:
                        Logger.write(f"[AGENT {self.profile.getName()}] LLM call failure (iteration {str(iteration)}) : {str(e)}", type=ERROR)
                        yield ThinkingEvent.get(call_uid=llm_call_uid, call_type=llm_call_type, status="ERROR", error_code="LLM_CALL_FAIL", message=str(e))
                        yield ErrorEvent.get(error_code="LLM_CALL_FAIL", message="LLM call failure", details=str(e))
                        yield DoneEvent.get()
                        return
                    if response.choices:
                        break
                    if attempt < self._EMPTY_LLM_RESPONSE_MAX_RETRY - 1:
                        Logger.write("[AGENT] LLM returned empty response, retrying...", type=WARNING)
                else:
                    Logger.write("[AGENT {self.profile.getName()}] LLM returned empty response after retries", type=ERROR)
                    yield ThinkingEvent.get(call_uid=llm_call_uid, call_type=llm_call_type, status="ERROR", error_code="EMPTY_RESPONSE", message="Empty LLM answer")
                    yield ErrorEvent.get(error_code="EMPTY_RESPONSE", message="Empty LLM answer")
                    yield DoneEvent.get()
                    return
                assistant_msg = response.choices[0].message
                yield ThinkingEvent.get(call_uid=llm_call_uid, call_type=llm_call_type, status="OK")
                Logger.write("[AGENT {self.profile.getName()}] Call LLM OK !", type=OK)

            # ----------------------------------------------------------------
            # ÉTAPE 3 — Réponse finale streamée token par token (1 retry si vide)
            # ----------------------------------------------------------------

            llm_call_uid = Uuid.get()
            llm_call_type = "FINAL"
            yield ThinkingEvent.get(call_uid=llm_call_uid, call_type=llm_call_type, status="PENDING")

            assistant_reply_tokens = []
            for attempt in range(self._EMPTY_LLM_RESPONSE_MAX_RETRY):
                Logger.write(f"[AGENT {self.profile.getName()}] Call LLM for final answer (attempt {attempt + 1}/{self._EMPTY_LLM_RESPONSE_MAX_RETRY})...", type=WARNING)
                try:
                    async for chunk in await self._connector.callLLM(messages=messages, stream=True, exclude_restricted=exclude_restricted, extra_tools=session_tools):
                        token = chunk.choices[0].delta.content
                        if token:
                            assistant_reply_tokens.append(token)
                            yield TokenEvent.get(token=token)
                except Exception as e:
                    Logger.write(f"[AGENT {self.profile.getName()}] LLM streaming error : {str(e)}", type=ERROR)
                    yield ThinkingEvent.get(call_uid=llm_call_uid, call_type=llm_call_type, status="ERROR", error_code="LLM_CALL_FAIL", message=str(e))
                    yield ErrorEvent.get(error_code="LLM_CALL_FAIL", message="LLM streaming error", details=str(e))
                    yield DoneEvent.get()
                    return

                if assistant_reply_tokens:
                    break
                if attempt < self._EMPTY_LLM_RESPONSE_MAX_RETRY - 1:
                    Logger.write("[AGENT {self.profile.getName()}] LLM returned empty response, retrying...", type=WARNING)

            if not assistant_reply_tokens:
                Logger.write("[AGENT {self.profile.getName()}] LLM returned empty response after retry", type=ERROR)
                yield ThinkingEvent.get(call_uid=llm_call_uid, call_type=llm_call_type, status="ERROR", error_code="EMPTY_RESPONSE", message="Empty response from LLM")
                yield ErrorEvent.get(error_code="EMPTY_RESPONSE", message="Empty response from LLM")
                yield DoneEvent.get()
                return


            yield ThinkingEvent.get(call_uid=llm_call_uid, call_type=llm_call_type, status="OK")
            Logger.write("[AGENT {self.profile.getName()}] Call LLM for final answer OK !", type=OK)

            #Emission groupée des citations RAG accumulées pendant tout le tour (dédoublonnées par source),
            #une fois la réponse finale prête plutôt qu'au fil des tool calls
            for rag_event in rag_sources.events():
                yield rag_event

            #On construit la chaine complète depuis les tokens
            assistant_reply = "".join(assistant_reply_tokens)
            new_history = history + [
                {"role": "user",      "content": message},
                {"role": "assistant", "content": assistant_reply},
            ]
            #On enregistre dans l'historique des messages
            agent_ctx.setHistory(new_history)

            #Log de l'appel pour comptabilisation (1 requete effectuée avec succès)
            LocalData.logLLMUsage(session_uid=session.getUid(), token_used=0)

            #Génération des questions de suivi suggérées (best-effort, ne doit jamais casser le tour de conversation)
            if self._FOLLOWUP_ENABLED:
                try:
                    followup_questions = await self._generateFollowUpQuestions(messages=messages, assistant_reply=assistant_reply, exclude_restricted=exclude_restricted)
                    if followup_questions:
                        yield FollowUpEvent.get(questions=followup_questions)
                except Exception as e:
                    Logger.write(f"[AGENT {self.profile.getName()}] Follow-up questions generation failed : {str(e)}", type=WARNING)

            yield DoneEvent.get()
        except Exception as e:
            Logger.write(f"[AGENT {self.profile.getName()}] Unexpected error : {str(e)}", type=ERROR)
            yield ErrorEvent.get(error_code="UNEXPECTED", message="Unexpected error", details=str(e))
            yield DoneEvent.get()
        finally:
            await turn_stack.aclose()
            ProcessManager.exit(process_token)
            ProcessManager.remove(process.getUid())

    """
    Appel LLM ponctuel hors session de chat (ex: bloc "Agent" d'un pipeline) : pas d'historique de
    conversation, pas de streaming. Si le contexte agent du process courant porte des pièces jointes (ex: bloc
    MicroRag de pipeline), leur contenu est placé en tête du prompt (cf. AttachmentRetriever.retrieve) : texte
    complet ou extraits selon `attachment_mode`, extraits recherchés sur `attachment_query` (à défaut le prompt).
    Les paramètres attachment_* à None prennent la valeur du profil (attachments.*). La boucle de tool calls
    est la même que dans chatStream, mais les outils nécessitant une confirmation sont refusés
    d'office (aucun client pour y répondre), sauf si auto_confirm=True : dans ce cas la confirmation
    est considérée comme accordée et l'outil est exécuté normalement. À n'activer que pour des
    pipelines de confiance : ces outils portent des effets de bord non triviaux (envoi de mail,
    suppression, écritures externes...). L'authentification utilisée pour les appels d'outils MCP
    est celle du process courant (ProcessManager.getCurrent(), via le wallet de sa racine) : c'est à l'appelant de
    l'avoir posé au préalable (ex: process enfant du run de pipeline, cf. lib/pipelines/blocks/agent.py).
    """
    async def reflect(self, prompt: str, exclude_restricted: bool = True, auto_confirm: bool = False, attachment_query: str | None = None, attachment_top_k: int | None = None,
                      attachment_mode: str | None = None, attachment_max_tokens: int | None = None) -> str:
        #Connexions aux serveurs MCP externes en auth "session" pour cet appel (cf.
        #MCPClientManager.open_session_external_tools) — tenues dans `turn_stack` et refermées dans le
        #`finally` ci-dessous, dans la même tâche asyncio que celle qui les a ouvertes (contrainte des
        #transports MCP, cf. docstring de open_session_external_tools).
        turn_stack = AsyncExitStack()
        try:
            session_tools, session_external_sessions = await mcp_manager.open_session_external_tools(turn_stack)

            now = datetime.datetime.now()
            system = self._system + f"\n\nDate et heure actuelles : {now.strftime('%A %d %B %Y, %H:%M')} (heure locale)"

            #Pièces jointes fournies par l'appelant (pas de condition sur attachments.enabled du profil : c'est le
            #pipeline qui les a explicitement jointes) : contenu fourni d'office, comme dans chatStream
            file_context = ""
            current = ProcessManager.getCurrent()
            agent_ctx = current.getAgentContext() if current else None
            attachments = agent_ctx.getAttachments() if agent_ctx else []
            if attachments:
                filenames = ", ".join(a["filename"] for a in attachments)
                results, full = await AttachmentRetriever().retrieve(attachment_query or prompt, mode=attachment_mode, top_k=attachment_top_k, max_tokens=attachment_max_tokens)
                Logger.write(f"[AGENT {self.profile.getName()}] Attachments ({filenames}) : {'full text' if full else f'{len(results)} excerpt(s)'}")
                system += AttachmentRetriever.instructions("Fichiers joints à cette demande", filenames, full)
                if results:
                    file_context = AttachmentRetriever.format_context(results, full)

            messages = [
                {"role": "system", "content": system},
                {"role": "user",   "content": f"{file_context}{prompt}"},
            ]

            Logger.write(f"[AGENT {self.profile.getName()}] Call LLM (reflect)...", type=WARNING)
            assistant_msg = await self._callReflectLLM(messages=messages, exclude_restricted=exclude_restricted, extra_tools=session_tools)

            iteration = 0
            while assistant_msg.tool_calls:
                iteration += 1
                if iteration > self._MAX_TOOL_ITERATIONS:
                    Logger.write(f"[AGENT {self.profile.getName()}] Too many consecutive tool calls (reflect)", type=ERROR)
                    raise Exception(f"Too many consecutive tool calls (limit: {self._MAX_TOOL_ITERATIONS})")

                messages.append({
                    "role": "assistant",
                    "content": assistant_msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in assistant_msg.tool_calls
                    ],
                })

                for tc in assistant_msg.tool_calls:
                    meta = MCPTool.get_meta(tc.function.name)

                    if meta.get("confirmation", False) and not auto_confirm:
                        Logger.write(f"[AGENT {self.profile.getName()}] Tool {tc.function.name} requires a confirmation, unavailable in reflect()", type=WARNING)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": "Tool call failed: this tool requires a user confirmation, unavailable in this context",
                        })
                        continue
                    if meta.get("confirmation", False) and auto_confirm:
                        Logger.write(f"[AGENT {self.profile.getName()}] Tool {tc.function.name} requires a confirmation, auto-confirmed (reflect auto_confirm=True)", type=WARNING)

                    Logger.write(f"[AGENT {self.profile.getName()}] Call MCP tool {tc.function.name}...", type=WARNING)
                    try:
                        args = json.loads(tc.function.arguments)
                        result_text, _ = await mcp_manager.call_tool(
                            tc.function.name, args,
                            tools_enabled=self.profile.getConfigValue(key="mcp.tools_enabled", default=[]),
                            external_sessions=session_external_sessions,
                        )
                    except Exception as e:
                        error_detail = str(e)
                        Logger.write(f"[AGENT {self.profile.getName()}] MCP tool {tc.function.name} error : {error_detail}", type=ERROR)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": f"Tool call failed: {error_detail}",
                        })
                        continue

                    Logger.write(f"[AGENT {self.profile.getName()}] Call MCP tool {tc.function.name} OK !", type=OK)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_text,
                    })

                assistant_msg = await self._callReflectLLM(messages=messages, exclude_restricted=exclude_restricted, extra_tools=session_tools)

            Logger.write(f"[AGENT {self.profile.getName()}] Call LLM (reflect) OK !", type=OK)
            LocalData.logLLMUsage(session_uid=ProcessManager.getCurrentRootId(), token_used=0)
            return assistant_msg.content or ""
        finally:
            await turn_stack.aclose()

    """
    Appel LLM non streamé avec retry sur réponse vide, utilisé par reflect().
    """
    async def _callReflectLLM(self, messages: list, exclude_restricted: bool, extra_tools: list | None = None):
        for attempt in range(self._EMPTY_LLM_RESPONSE_MAX_RETRY):
            response = await self._connector.callLLM(messages=messages, stream=False, exclude_restricted=exclude_restricted, extra_tools=extra_tools)
            if response.choices:
                return response.choices[0].message
            if attempt < self._EMPTY_LLM_RESPONSE_MAX_RETRY - 1:
                Logger.write(f"[AGENT {self.profile.getName()}] LLM returned empty response (reflect), retrying...", type=WARNING)
        Logger.write(f"[AGENT {self.profile.getName()}] LLM returned empty response after retries (reflect)", type=ERROR)
        raise Exception("Empty LLM answer")

    """
    Génère une liste de questions de suivi suggérées à partir de l'échange complet.
    Réutilise le prompt système et l'historique de l'appel principal (donc le périmètre/les règles de l'agent)
    et y ajoute un résumé des outils réellement disponibles, pour éviter que le modèle propose des questions
    hors périmètre ou portant sur des données/fonctionnalités auxquelles l'agent n'a pas accès.
    Appel non streamé, sans tools (use_tools=False), pour ne pas déclencher de tool call sur cet appel annexe.
    """
    async def _generateFollowUpQuestions(self, messages: list, assistant_reply: str, exclude_restricted: bool) -> list:
        capabilities = self._connector.tools_summary(exclude_restricted=exclude_restricted)
        instruction = (
            f"En te basant uniquement sur l'échange ci-dessus et sur les capacités réellement disponibles pour cet "
            f"assistant listées ci-dessous, propose {self._FOLLOWUP_COUNT} questions de suivi courtes et pertinentes "
            "que l'utilisateur pourrait poser ensuite. N'invente aucune fonctionnalité, donnée ou service qui n'apparaît "
            f"pas dans la conversation ci-dessus ou dans cette liste de capacités :\n{capabilities}\n\n"
            "Réponds UNIQUEMENT avec un tableau JSON de chaînes de caractères, sans texte additionnel, sans balises de code."
        )
        followup_messages = messages + [
            {"role": "assistant", "content": assistant_reply},
            {"role": "user", "content": instruction},
        ]
        response = await self._connector.callLLM(messages=followup_messages, stream=False, exclude_restricted=exclude_restricted, use_tools=False)
        if not response.choices:
            return []

        content = (response.choices[0].message.content or "").strip()
        if content.startswith("```"):
            content = content.strip("`")
            if content.lower().startswith("json"):
                content = content[4:]
            content = content.strip()

        questions = json.loads(content)
        if not isinstance(questions, list) or not all(isinstance(q, str) for q in questions):
            return []

        return questions[:self._FOLLOWUP_COUNT]


"""
AgentManager — Gestionnaire d'agents
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class AgentManager:
    @staticmethod
    def init():
        AgentManager.agents = {}
        for profile in ProfileManager.getProfileNames():
            AgentManager.agents[profile] = Agent(connector=ProfileManager.getProfile(name=profile).getConfigValue("llm.connector"), profile=ProfileManager.getProfile(name=profile))

    @staticmethod
    def getAgent(name:str)->Agent | None:
        return AgentManager.agents.get(name)