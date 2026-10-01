import asyncio
from lib.localization.language import Language

"""
AgentContext — État conversationnel d'un agent, rattaché à un Process (cf. Process.setAgentContext)
Même durée de vie que le process qui le porte (session HTTP/Webex, ou exécution d'un bloc Agent de pipeline) :
les tours de conversation (process enfants) le retrouvent via Process.getAgentContext().
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class AgentContext:
    def __init__(self, profile: str = "default", language: Language = None):
        self._profile = profile                           # Profil de configuration LLM
        self._language = language                         # Langue appliquée
        self._history: list[dict] = []                    # Historique de la conversation
        self._attachments: dict[str, dict] = {}           # Pièces jointes conversationnelles (texte extrait, tokens, chunks RAG), indexées par clé
        self._flood_timestamps: list[float] = []          # Horodatages des derniers appels LLM, utilisés pour le rate-limiting (voir llmlimiter.py)
        self._confirmation_queue: asyncio.Queue | None = None   # File d'attente de la confirmation en cours (cf. waitConfirmation)

    def getProfile(self) -> str:
        return self._profile

    #Obtenir l'objet Profile associé
    def getProfileConfig(self):
        from lib.agent.profile import ProfileManager
        return ProfileManager.getProfile(self._profile)

    def getLanguage(self) -> Language:
        return self._language

    def getHistory(self) -> list[dict]:
        return self._history

    def setHistory(self, history: list[dict]) -> None:
        self._history = history

    def getFloodTimestamps(self) -> list[float]:
        return self._flood_timestamps

    #Ajouter une pièce jointe conversationnelle (texte déjà extrait)
    #`pages` : list[tuple[int,str]] pour un PDF (texte par page), None si le format n'a pas de pagination.
    #`chunks` est rempli paresseusement au premier passage en micro-RAG (cache des embeddings pour la session),
    #`embedding_model` identifie le modèle qui a produit ces embeddings (cf. Embedder.model_id)
    def addAttachment(self, key: str, filename: str, text: str, tokens: int, pages: list | None = None):
        self._attachments[key] = {"key": key, "filename": filename, "text": text, "tokens": tokens, "chunks": None, "embedding_model": None, "pages": pages}

    def getAttachments(self) -> list[dict]:
        return list(self._attachments.values())

    #Met en cache les chunks/embeddings calculés pour une pièce jointe (évite de les recalculer aux tours suivants)
    def cacheAttachmentChunks(self, key: str, chunks: list[dict], embedding_model: str) -> None:
        if key in self._attachments:
            self._attachments[key]["chunks"] = chunks
            self._attachments[key]["embedding_model"] = embedding_model

    #Attend la réponse du client à une demande de confirmation
    async def waitConfirmation(self, timeout: int = 120) -> int:
        self._confirmation_queue = asyncio.Queue(maxsize=1)
        try:
            return await asyncio.wait_for(self._confirmation_queue.get(), timeout=timeout)
        finally:
            self._confirmation_queue = None

    def hasPendingConfirmation(self) -> bool:
        return self._confirmation_queue is not None

    #Résolution d'une confirmation en attente
    def resolveConfirmation(self, option: int) -> bool:
        if self._confirmation_queue is None:
            return False
        self._confirmation_queue.put_nowait(option)
        return True
