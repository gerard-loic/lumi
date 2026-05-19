"""
Orchestration Ollama + MCP avec streaming SSE.

Stratégie en deux temps :
  1. Appel Ollama NON streamé  → détecter les tool calls
  2. Exécution des tools via MCP si nécessaire
  3. Appel Ollama STREAMÉ      → réponse finale token par token
"""

import json
from typing import AsyncGenerator
import ollama

from lib.mcp.client import mcp_manager

import sys
from lib.config.config import Config


class Agent:

    def __init__(self):
        self._client = ollama.AsyncClient(host=Config.get(key="OLLAMA_HOST", type="env"))
        self._model  = Config.get(key="OLLAMA_MODEL", type="env")
        self._tools  = mcp_manager.tools_as_ollama_format()
        self._system = Config.get(key="SYSTEM_PROMPT", type="env")
        print(f"[Agent] {len(self._tools)} outil(s) chargé(s) : {[t['function']['name'] for t in self._tools]}")

    async def chat_stream(self, message: str, bearer: str) -> AsyncGenerator[str, None]:
        """
        Générateur async qui yield des chunks SSE.
        Format : "data: <token>\n\n"
        Signal de fin : "data: [DONE]\n\n"
        """
        messages = [
            {"role": "system", "content": self._system},
            {"role": "user",   "content": message},
        ]

        # ----------------------------------------------------------------
        # ÉTAPE 1 — Appel non streamé pour détecter les tool calls
        # ----------------------------------------------------------------
        response = await self._client.chat(
            model=self._model,
            messages=messages,
            tools=self._tools,
            stream=False,
        )
        assistant_msg = response.message

        # ----------------------------------------------------------------
        # ÉTAPE 2 — Boucle de résolution des tool calls
        # ----------------------------------------------------------------
        while assistant_msg.tool_calls:

            tool_names = [tc.function.name for tc in assistant_msg.tool_calls]
            yield self._sse_event("tool_call", {"tools": tool_names})

            messages.append({
                "role": "assistant",
                "content": assistant_msg.content or "",
                "tool_calls": [
                    {
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    }
                    for tc in assistant_msg.tool_calls
                ],
            })

            for tc in assistant_msg.tool_calls:
                args = dict(tc.function.arguments)
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
                        yield "data: [DONE]\n\n"
                        return
                except (json.JSONDecodeError, AttributeError, TypeError):
                    pass

                messages.append({
                    "role": "tool",
                    "content": result_text,
                })

            response = await self._client.chat(
                model=self._model,
                messages=messages,
                tools=self._tools,
                stream=False,
            )
            assistant_msg = response.message

        # ----------------------------------------------------------------
        # ÉTAPE 3 — Réponse finale streamée token par token
        # ----------------------------------------------------------------
        async for chunk in await self._client.chat(
            model=self._model,
            messages=messages,
            stream=True,
        ):
            token = chunk.message.content
            if token:
                yield self._sse_token(token)

        yield "data: [DONE]\n\n"

    # ----------------------------------------------------------------
    # Helpers SSE
    # ----------------------------------------------------------------

    @staticmethod
    def _sse_token(token: str) -> str:
        """Chunk de texte normal."""
        return f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

    @staticmethod
    def _sse_event(event_type: str, payload: dict) -> str:
        """Événement structuré (tool_call, erreur...)."""
        return f"data: {json.dumps({'type': event_type, **payload})}\n\n"
