import json
from lib.agent.events import RagEvent

"""
RagAccumulator : accumule les événements RAG d'un tour de conversation (source dédoublonnée, pages fusionnées)
plutôt que de les émettre immédiatement : le LLM peut appeler l'outil de recherche RAG plusieurs fois (ou combiner
pré-recherche sur pièces jointes et outil RAG) pour une même réponse, ce qui produirait sinon des citations
dupliquées/entrelacées avec les tokens de la réponse. Les événements groupés sont émis une fois la réponse prête.
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class RagAccumulator:
    def __init__(self):
        self._sources: dict = {}

    #Absorbe un événement sérialisé. Retourne True si l'événement a été absorbé (événement de type "rag"), False sinon
    def add(self, raw_event: str) -> bool:
        try:
            data = json.loads(raw_event)
        except (TypeError, ValueError):
            return False
        if data.get("type") != "rag":
            return False
        entry = self._sources.setdefault(data["source"], {"locations": [], "url": None})
        for loc in data.get("locations") or []:
            if loc not in entry["locations"]:
                entry["locations"].append(loc)
        if data.get("url") and not entry["url"]:
            entry["url"] = data["url"]
        return True

    #Evénements RAG groupés (un par source), à émettre une fois la réponse prête
    def events(self) -> list:
        return [RagEvent.get(source=source, locations=data["locations"], url=data["url"]) for source, data in self._sources.items()]