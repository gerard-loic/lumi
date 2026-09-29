from lib.rag.indexer import Indexer
from lib.rag.embedder import Embedder
from lib.rag.collection import RagCollection
from lib.process.processmanager import ProcessManager

"""
AttachmentRetriever — Recherche dans les fichiers joints à la conversation (micro-RAG éphémère, en mémoire)
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>

Contrairement à Retriever (RAG persistant, pgvector), les fichiers proviennent des pièces jointes de l'AgentContext
(uploadés via POST /files/upload) et ne sont jamais écrits en base : chunking + embeddings calculés
à la volée et mis en cache dans la session (attachment["chunks"]) pour la durée de vie de la session.
Le découpage et les embeddings utilisent la configuration de la collection RAG du profil de l'agent
(profiles.<profil>.rag.collection, celle du profil "default" à défaut) : rien n'est stocké, chunks et requête sont
encodés avec le même modèle. Le cache est marqué du modèle qui l'a produit (attachment["embedding_model"]) et
recalculé si un agent d'un autre profil/modèle interroge les mêmes fichiers.

retrieve() choisit ce qui est fourni au LLM selon le mode (profil "attachments.mode", surchargeable par l'appelant) :
  - "rag"  : les extraits les plus pertinents pour la requête (search) ;
  - "full" : le texte complet de tous les fichiers (page par page pour un PDF), sans embeddings ;
  - "auto" : le texte complet si le total tient dans "attachments.full_text_max_tokens", les extraits sinon.
Le mode "rag" ne convient pas aux demandes qui portent sur tout le document (lister, résumer, comparer...).
"""
class AttachmentRetriever:
    MODES = ("rag", "full", "auto")
    DEFAULT_MODE = "auto"
    DEFAULT_FULL_TEXT_MAX_TOKENS = 20000

    #Contexte fichiers à fournir au LLM pour `query`. Paramètres à None : valeurs du profil de la session.
    #Retourne (résultats, full) : résultats au format de search() ([{"filename","text","page"}]), full=True si
    #ce sont les textes complets (une entrée par page pour un PDF, par fichier sinon) plutôt que des extraits.
    async def retrieve(self, query: str, mode: str | None = None, top_k: int | None = None, max_tokens: int | None = None) -> tuple[list[dict], bool]:
        agent_ctx, attachments = self._current()
        if not attachments:
            return [], False

        profile = agent_ctx.getProfileConfig()
        if mode is None:
            mode = profile.getConfigValue("attachments.mode", default=self.DEFAULT_MODE) if profile else self.DEFAULT_MODE
        mode = str(mode).lower()
        if mode not in self.MODES:
            raise ValueError(f"Unknown attachment mode '{mode}' (expected one of {', '.join(self.MODES)})")

        if mode == "auto":
            if max_tokens is None:
                max_tokens = profile.getConfigValue("attachments.full_text_max_tokens", default=self.DEFAULT_FULL_TEXT_MAX_TOKENS) if profile else self.DEFAULT_FULL_TEXT_MAX_TOKENS
            mode = "full" if sum(a["tokens"] for a in attachments) <= int(max_tokens) else "rag"

        if mode == "full":
            return self._fullText(attachments), True
        return await self.search(query, top_k=top_k), False

    #Retourne les extraits les plus pertinents pour `query` parmi les fichiers joints à la session courante.
    #Toujours en passant par le micro-RAG (chunking + similarité) : le texte complet d'un fichier n'est
    #jamais envoyé au LLM, seuls les chunks les plus pertinents pour la question posée le sont.
    #`top_k` : surcharge du nombre d'extraits retournés (ex: bloc Agent de pipeline), sinon valeur du profil.
    async def search(self, query: str, top_k: int | None = None) -> list[dict]:
        agent_ctx, attachments = self._current()
        if not attachments:
            return []

        #Le top_k dépend du profil de configuration associé à la session
        if top_k is None:
            profile = agent_ctx.getProfileConfig()
            top_k = profile.getConfigValue("attachments.file_context_top_k", default=8) if profile else 8

        return await self._searchChunks(agent_ctx, attachments, query, top_k)

    #Contexte agent et pièces jointes du process courant
    @staticmethod
    def _current():
        process = ProcessManager.getCurrent()
        agent_ctx = process.getAgentContext() if process else None
        return agent_ctx, (agent_ctx.getAttachments() if agent_ctx else [])

    #Textes complets des fichiers, dans l'ordre d'ajout : une entrée par page pour un fichier paginé (PDF)
    @staticmethod
    def _fullText(attachments: list) -> list[dict]:
        results = []
        for attachment in attachments:
            if attachment.get("pages"):
                results.extend({"filename": attachment["filename"], "text": text, "page": page} for page, text in attachment["pages"] if text.strip())
            else:
                results.append({"filename": attachment["filename"], "text": attachment["text"], "page": None})
        return results

    #Regroupe les résultats de search() par fichier, pour construire les événements de citation (RagEvent) :
    #{"fichier.pdf": [3, 7], "notes.txt": []}
    #`results` est déjà trié par similarité décroissante (cf. _searchChunks) : on préserve cet ordre plutôt
    #que de trier les pages par numéro, pour que la page la plus pertinente apparaisse en premier.
    @staticmethod
    def group_pages_by_file(results: list[dict]) -> dict[str, list[int]]:
        pages_by_file: dict[str, list[int]] = {}
        for r in results:
            pages = pages_by_file.setdefault(r["filename"], [])
            page = r.get("page")
            if page is not None and page not in pages:
                pages.append(page)
        return pages_by_file

    #Chunke un fichier en conservant la page d'origine de chaque chunk quand le fichier est paginé (PDF) :
    #un chunking par page (comme PdfIndexer.index côté RAG persistant) plutôt qu'un chunking global.
    async def _buildChunks(self, attachment: dict, indexer: Indexer, embedder: Embedder) -> list[dict]:
        if attachment.get("pages"):
            raw_chunks = [
                {"text": c["text"], "page": page_num}
                for page_num, page_text in attachment["pages"]
                for c in indexer._chunk(page_text)
            ]
        else:
            raw_chunks = [{"text": c["text"], "page": None} for c in indexer._chunk(attachment["text"])]

        texts = [c["text"] for c in raw_chunks]
        embeddings = await embedder.embed(texts) if texts else []
        return [{"text": c["text"], "page": c["page"], "embedding": e} for c, e in zip(raw_chunks, embeddings)]

    async def _searchChunks(self, agent_ctx, attachments: list, query: str, top_k: int) -> list[dict]:
        import numpy as np

        #Collection RAG du profil de l'agent : seule sa configuration (découpage, embedder) est utilisée, jamais son
        #stockage (cf. docstring du module). Indexer réutilisé uniquement pour _chunk(), jamais pour VectorStore
        collection = RagCollection.ofProfile(agent_ctx.getProfileConfig())
        indexer = Indexer(collection=collection)
        embedder = Embedder(collection)

        chunk_texts, chunk_filenames, chunk_pages, chunk_embeddings = [], [], [], []
        for attachment in attachments:
            cached = attachment.get("chunks")
            if cached is None or attachment.get("embedding_model") != embedder.model_id:
                cached = await self._buildChunks(attachment, indexer, embedder)
                agent_ctx.cacheAttachmentChunks(attachment["key"], cached, embedder.model_id)

            for chunk in cached:
                chunk_texts.append(chunk["text"])
                chunk_filenames.append(attachment["filename"])
                chunk_pages.append(chunk["page"])
                chunk_embeddings.append(chunk["embedding"])

        if not chunk_texts:
            return []

        query_embedding = (await embedder.embed([query]))[0]

        chunk_matrix = np.array(chunk_embeddings)
        query_vector = np.array(query_embedding)
        scores = chunk_matrix @ query_vector / (np.linalg.norm(chunk_matrix, axis=1) * np.linalg.norm(query_vector) + 1e-8)

        top_k = min(top_k, len(chunk_texts))
        top_indices = np.argsort(scores)[::-1][:top_k]

        return [{"filename": chunk_filenames[i], "text": chunk_texts[i], "page": chunk_pages[i]} for i in top_indices]
