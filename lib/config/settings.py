import os

OLLAMA_HOST  = os.environ.get("OLLAMA_HOST",  "http://187.77.64.25:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b-instruct")
MCP_SERVER   = os.environ.get("MCP_SERVER",   "lib/mcp/server.py")

SYSTEM_PROMPT = (
    "Tu es un assistant pour un extranet client. "
    "Tu réponds en français, de façon concise et professionnelle. "
    "Utilise les outils disponibles pour récupérer les données en temps réel. "
    "Ne réponds jamais avec des données inventées si un outil est disponible pour les obtenir."
)
