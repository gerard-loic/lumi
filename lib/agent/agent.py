import json
from typing import AsyncGenerator, Optional
from lib.mcp.client import mcp_manager, MCPToolError
from lib.mcp.tools import MCPTool
from lib.config.config import Config
from lib.agent.llmconnector.litellm import LiteLLM
from lib.agent.events import TokenEvent, DoneEvent, ToolEvent, ErrorEvent, ConfirmationEvent, ConfirmationRefusedEvent
from lib.session.session import AuthSessionManager as _SessionManager
from lib.log.logger import Logger, ERROR, OK, WARNING
from lib.session.session import AuthSessionManager

"""
Agent — Agent d'orchestration / communication LLM
Stratégie :
1. Appel LiteLLM NON streamé pour détecter les tool calls
2. Exécution des tools via MCP si nécessaire
3. Appel LiteLLM STREAMÉ réponse finale token par token
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Agent:
    def __init__(self, connector:str):
        #Initialisation du connecteur LLM
        if connector=="LiteLLM":
            self._connector = LiteLLM()
        else:
            Logger.write(f"[AGENT] LLM connector {connector} not supported.", type=ERROR)
            raise Exception(f"LLM connector {connector} not supported.")
        
        #Prompt systeme
        self._system   = Config.get(key="llm.system_prompt")

        self._MAX_TOOL_ITERATIONS = Config.get(key="mcp.max_tool_iterations")

        Logger.write("[AGENT] MCP agent initialized", type=OK)

    """
    Gestion d'une connexion SSE (correspondant à une requête client)
    """
    async def chatStream(self, message: str, authorization: dict, session_id: Optional[str] = None) -> AsyncGenerator[str, None]:
        try:
            history = AuthSessionManager.get_history(session_id)

            messages = [
                {"role": "system", "content": self._system},
                *history,
                {"role": "user",   "content": message},
            ]

            Logger.write("[AGENT] Call LLM...", type=WARNING)
            # ----------------------------------------------------------------
            # ÉTAPE 1 — Appel non streamé pour détecter les tool calls
            # ----------------------------------------------------------------
            try:
                response = await self._connector.callLLM(messages=messages, stream=False)
                if not response.choices:
                    raise ValueError("Empty LLM answer")
                assistant_msg = response.choices[0].message
            except Exception as e:
                Logger.write(f"[AGENT] LLM call failure : {str(e)}", type=ERROR)
                yield ErrorEvent.get(error_code="LLM_CALL_FAIL", message="LLM call failure", details=str(e))
                yield DoneEvent.get()
                return

            Logger.write("[AGENT] Call LLM OK !", type=OK)

            # ----------------------------------------------------------------
            # ÉTAPE 2 — Boucle de résolution des tool calls
            # ----------------------------------------------------------------
            iteration = 0
            while assistant_msg.tool_calls:
                iteration += 1
                if iteration > self._MAX_TOOL_ITERATIONS:
                    Logger.write("[AGENT] Too many consecutive tool calls", type=ERROR)
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

                for tc in assistant_msg.tool_calls:
                    Logger.write(f"[AGENT] Call MCP tool {tc.function.name}...", type=WARNING)
                    meta = MCPTool.get_meta(tc.function.name)
                    description = meta.get("description", tc.function.name)
                    if description == False:
                        description = tc.function.name

                    #Verifier si l'outil nécessite une confirmation préalable
                    if meta.get("confirmation", False) and session_id:
                        yield ConfirmationEvent.get(
                            question=meta.get("confirmation_question", False),
                            options=meta.get("confirmation_options", False)
                        )
                        try:
                            answer = await _SessionManager.wait_confirmation(session_id)
                        except Exception:
                            answer = -1
                        if answer != meta.get("confirmation_validation_option", -1):
                            yield ConfirmationRefusedEvent.get()
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": "Action cancelled by user.",
                            })
                            continue

                    yield ToolEvent.get(tool_name=tc.function.name, status="PENDING", long_call=meta.get("slow", False), message=description)
                    try:
                        args = json.loads(tc.function.arguments)
                        result_text, tool_events = await mcp_manager.call_tool(tc.function.name, args)
                    except MCPToolError as e:
                        error_detail = str(e)
                        Logger.write(f"[AGENT] MCP tool {tc.function.name} error : {error_detail}", type=ERROR)
                        yield ToolEvent.get(tool_name=tc.function.name, status="ERROR", message=error_detail)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": f"Tool call failed: {error_detail}",
                        })
                        continue
                    except Exception as e:
                        error_detail = str(e)
                        Logger.write(f"[AGENT] MCP tool {tc.function.name} error : {error_detail}", type=ERROR)
                        yield ToolEvent.get(tool_name=tc.function.name, status="ERROR", message=error_detail)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": f"Tool call failed: {error_detail}",
                        })
                        continue

                    Logger.write(f"[AGENT] Call MCP tool {tc.function.name} OK !", type=OK)
                    yield ToolEvent.get(tool_name=tc.function.name, status="OK")

                    for event in tool_events:
                        yield event

                    # Interception des actions spéciales — le LLM n'est pas rappelé
                    #TODO
  
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_text,
                    })


                Logger.write("[AGENT] Call LLM...", type=WARNING)
                try:
                    response = await self._connector.callLLM(messages=messages, stream=False)
                    if not response.choices:
                        raise ValueError("Empty LLM answer")
                    assistant_msg = response.choices[0].message
                except Exception as e:
                    Logger.write(f"[AGENT] LLM call failure (iteration {str(iteration)}) : {str(e)}", type=ERROR)
                    yield ErrorEvent.get(error_code="LLM_CALL_FAIL", message="LLM call failure", details=str(e))
                    yield DoneEvent.get()
                    return
                Logger.write("[AGENT] Call LLM OK !", type=OK)

            # ----------------------------------------------------------------
            # ÉTAPE 3 — Réponse finale streamée token par token
            # ----------------------------------------------------------------
            Logger.write("[AGENT] Call LLM for final answer...", type=WARNING)
            assistant_reply_tokens = []
            try:
                async for chunk in await self._connector.callLLM(messages=messages, stream=True):
                    token = chunk.choices[0].delta.content
                    if token:
                        assistant_reply_tokens.append(token)
                        yield TokenEvent.get(token=token)
            except Exception as e:
                Logger.write(f"[AGENT] LLM streaming error : {str(e)}", type=ERROR)
                yield ErrorEvent.get(error_code="LLM_CALL_FAIL", message="LLM streaming error", details=str(e))
                yield DoneEvent.get()
                return

            Logger.write("[AGENT] Call LLM for final answer OK !", type=OK)

            assistant_reply = "".join(assistant_reply_tokens)
            new_history = history + [
                {"role": "user",      "content": message},
                {"role": "assistant", "content": assistant_reply},
            ]
            AuthSessionManager.save_history(session_id, new_history)

            yield DoneEvent.get()
        except Exception as e:
            Logger.write(f"[AGENT] Unexpected error : {str(e)}", type=ERROR)
            yield ErrorEvent.get(error_code="UNEXPECTED", message="Unexpected error", details=str(e))
            yield DoneEvent.get()

