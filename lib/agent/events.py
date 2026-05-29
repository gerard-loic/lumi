import json

class Event:
    @staticmethod
    def get(eventType:str, payload: dict=None):
        if payload == None:
            return f"data: {json.dumps({'type': eventType})}\n\n"
        else:
            return f"data: {json.dumps({'type': eventType, **payload})}\n\n"
        
class ErrorEvent:
    @staticmethod
    def get(error_code:str, message:str):
        return Event.get(eventType="error", payload={"error_code":error_code, "message":message})
        
"""Chunk de texte normal."""
class TokenEvent:
    @staticmethod
    def get(token:str):
        return Event.get(eventType="token", payload={"content":token})
    

class DoneEvent:
    @staticmethod
    def get():
        return Event.get(eventType="end")
    
class ToolEvent:
    @staticmethod
    def get(tool_names:str):
        return Event.get(eventType="tool_call", payload={"tools" : tool_names})

class ConfirmationEvent:
    pass

class FileEvent:
    pass

class UrlEvent:
    pass
