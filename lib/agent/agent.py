"""
Orchestration LiteLLM + MCP avec streaming SSE.

Stratégie en deux temps :
  1. Appel LiteLLM NON streamé  → détecter les tool calls
  2. Exécution des tools via MCP si nécessaire
  3. Appel LiteLLM STREAMÉ      → réponse finale token par token
"""

import json
from typing import AsyncGenerator
import litellm

from lib.mcp.client import mcp_manager

from lib.config.config import Config
from lib.agent.llmconnector.litellm import LiteLLM


class Agent:

    def __init__(self):
        self._model    = Config.get(key="LLM_MODEL", type="env")
        self._api_base = Config.get(key="LLM_API_BASE", type="env")
        self._api_key  = Config.get(key="LLM_API_KEY", type="env")
        self._tools    = mcp_manager.tools_as_openai_format()
        self._system   = Config.get(key="SYSTEM_PROMPT", type="env")
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
        response = await litellm.acompletion(
            model=self._model,
            messages=messages,
            tools=self._tools,
            stream=False,
            api_base=self._api_base,
            api_key=self._api_key,
        )
        assistant_msg = response.choices[0].message

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
                        yield "data: [DONE]\n\n"
                        return
                except (json.JSONDecodeError, AttributeError, TypeError):
                    pass

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_text,
                })

            response = await litellm.acompletion(
                model=self._model,
                messages=messages,
                tools=self._tools,
                stream=False,
                api_base=self._api_base,
                api_key=self._api_key,
            )
            assistant_msg = response.choices[0].message

        # ----------------------------------------------------------------
        # ÉTAPE 3 — Réponse finale streamée token par token
        # ----------------------------------------------------------------
        async for chunk in await litellm.acompletion(
            model=self._model,
            messages=messages,
            stream=True,
            api_base=self._api_base,
            api_key=self._api_key,
        ):
            token = chunk.choices[0].delta.content
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
