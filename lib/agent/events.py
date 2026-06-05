import json

"""
Event — Classe parente de tous les évenements retournés par l'agent vers le client
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Event:
    @staticmethod
    def get(eventType:str, payload: dict=None):
        if payload == None:
            return f"data: {json.dumps({'type': eventType})}\n\n"
        else:
            return f"data: {json.dumps({'type': eventType, **payload})}\n\n"

"""
ErrorEvent — Evenement lorsqu'une erreur est relevée
Codes d'erreur supportés :
LLM_CALL_FAIL : erreur d'appel au LLM
MCP_TOOL_LIMIT_EXCEEDED : Trop d'appels d'outils consécutifs
UNEXPECTED : erreur inattendue
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class ErrorEvent:
    @staticmethod
    def get(error_code:str, message:str, details:str = ""):
        return Event.get(eventType="error", payload={"error_code":error_code, "message":message, "details":details})
        

"""
TokenEvent : Retourne un token de texte
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class TokenEvent:
    @staticmethod
    def get(token:str):
        return Event.get(eventType="token", payload={"content":token})

"""
DoneEvent : Envoyé lorsque la conversation est terminée
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class DoneEvent:
    @staticmethod
    def get():
        return Event.get(eventType="end")

"""
ToolEvent : envoyé avant, après ou à l'erreur de l'appel d'un outil MCP
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class ToolEvent:
    @staticmethod
    def get(tool_name:str, status:str = "PENDING", long_call:bool = False, message:str = ""):
        return Event.get(eventType="tool_call", payload={"tools" : tool_name, "status" : status, "long_call" : long_call, "message": message})

"""
FileEvent : envoyé lorsqu'un fichier est généré et mis à disposition
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class FileEvent:
    @staticmethod
    def get(name:str, url:str):
        return Event.get(eventType="file", payload={"name": name, "url": url})

"""
UrlEvent : envoyé lorsqu'une url est mise à disposition
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class UrlEvent:
    @staticmethod
    def get(name:str, url:str):
        return Event.get(eventType="url", payload={"name": name, "url": url})
