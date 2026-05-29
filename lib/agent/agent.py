import json
from typing import AsyncGenerator, Optional
from lib.mcp.client import mcp_manager
from lib.config.config import Config
from lib.agent.llmconnector.litellm import LiteLLM
from lib.agent.events import TokenEvent, DoneEvent, ToolEvent, ErrorEvent

"""
Agent d'orchestration / communication LLM
Stratégie :
1. Appel LiteLLM NON streamé pour détecter les tool calls
2. Exécution des tools via MCP si nécessaire
 3. Appel LiteLLM STREAMÉ réponse finale token par token
"""
class Agent:
    def __init__(self, connector:str):
        if connector=="LiteLLM":
            self._connector = LiteLLM()
        else:
            raise Exception(f"LLM connector {connector} not supported.")
        self._system   = Config.get(key="SYSTEM_PROMPT", type="env")
        # Historique des conversations : session_id -> liste de messages {role, content}
        self._sessions: dict[str, list[dict]] = {}

    def _get_history(self, session_id: Optional[str]) -> list[dict]:
        if not session_id:
            return []
        return self._sessions.get(session_id, [])

    def _save_history(self, session_id: Optional[str], history: list[dict]) -> None:
        if session_id:
            self._sessions[session_id] = history

    """
    Gestion d'une connexion SSE (correspondant à une requête client)
    Format des messages (chunks) transmis dans le flux : "data: <token>"
    Signal de fin de communication : "data: [DONE]"
    """
    async def chatStream(self, message: str, bearer: str, session_id: Optional[str] = None) -> AsyncGenerator[str, None]:
        try:
            history = self._get_history(session_id)

            #Prompts (system + historique + message courant)
            messages = [
                {"role": "system", "content": self._system},
                *history,
                {"role": "user",   "content": message},
            ]

            # ----------------------------------------------------------------
            # ÉTAPE 1 — Appel non streamé pour détecter les tool calls
            # ----------------------------------------------------------------
            response = await self._connector.callLLM(messages=messages, stream=False)
            assistant_msg = response.choices[0].message


            # ----------------------------------------------------------------
            # ÉTAPE 2 — Boucle de résolution des tool calls
            # ----------------------------------------------------------------
            while assistant_msg.tool_calls:

                tool_names = [tc.function.name for tc in assistant_msg.tool_calls]  
                yield ToolEvent.get(tool_names=tool_names)#Retourne qu'on utilise un outil

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
                    args = json.loads(tc.function.arguments)
                    result_text = await mcp_manager.call_tool(tc.function.name, args, bearer=bearer)

                    # Interception des actions spéciales — le LLM n'est pas rappelé
                    try:
                        result_data = json.loads(result_text)
                        action = result_data.get("action")
                        if action == "redirect":
                            yield self._sse_event("redirect", {
                                "url": result_data["url"],
                                "message": result_data.get("message", ""),
                            })
                            yield DoneEvent.get()
                            return
                    except (json.JSONDecodeError, AttributeError, TypeError):
                        pass

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_text,
                    })

                response = await self._connector.callLLM(messages=messages, stream=False)
                assistant_msg = response.choices[0].message

            # ----------------------------------------------------------------
            # ÉTAPE 3 — Réponse finale streamée token par token
            # ----------------------------------------------------------------
            assistant_reply_tokens = []
            async for chunk in await self._connector.callLLM(messages=messages, stream=True):
                token = chunk.choices[0].delta.content
                if token:
                    assistant_reply_tokens.append(token)
                    yield TokenEvent.get(token=token)

            # Sauvegarde du tour dans l'historique de session
            assistant_reply = "".join(assistant_reply_tokens)
            new_history = history + [
                {"role": "user",      "content": message},
                {"role": "assistant", "content": assistant_reply},
            ]
            self._save_history(session_id, new_history)

            #Message de fin
            yield DoneEvent.get()
        except Exception as e:
            yield ErrorEvent.get(error_code="0", message="Une erreur a été rncontrée")
            yield DoneEvent.get()

