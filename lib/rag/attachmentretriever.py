from lib.rag.indexer import Indexer
from lib.session.session import AuthSessionManager

"""
AttachmentRetriever — Recherche dans les fichiers joints à la conversation (micro-RAG éphémère, en mémoire)
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>

Contrairement à Retriever (RAG persistant, pgvector), les fichiers proviennent de session.attachments
(uploadés via POST /files/upload) et ne sont jamais écrits en base : chunking + embeddings calculés
à la volée et mis en cache dans la session (attachment["chunks"]) pour la durée de vie de la session.
"""
class AttachmentRetriever:
    def __init__(self):
        self._indexer = Indexer()  # réutilisé uniquement pour _chunk() et son _embedder, jamais pour VectorStore

    #Retourne les extraits les plus pertinents pour `query` parmi les fichiers joints à la session.
    #Toujours en passant par le micro-RAG (chunking + similarité) : le texte complet d'un fichier n'est
    #jamais envoyé au LLM, seuls les chunks les plus pertinents pour la question posée le sont.
    async def search(self, session_id: str, query: str) -> list[dict]:
        attachments = AuthSessionManager.get_all_attachments(session_id)
        if not attachments:
            return []

        #Le top_k dépend du profil de configuration associé à la session
        profile = AuthSessionManager.get_profile(session_id)
        top_k = profile.getConfigValue("attachments.file_context_top_k", default=8) if profile else 8

        return await self._searchChunks(session_id, attachments, query, top_k)

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
    async def _buildChunks(self, attachment: dict) -> list[dict]:
        if attachment.get("pages"):
            raw_chunks = [
                {"text": c["text"], "page": page_num}
                for page_num, page_text in attachment["pages"]
                for c in self._indexer._chunk(page_text)
            ]
        else:
            raw_chunks = [{"text": c["text"], "page": None} for c in self._indexer._chunk(attachment["text"])]

        texts = [c["text"] for c in raw_chunks]
        embeddings = await self._indexer._embedder.embed(texts) if texts else []
        return [{"text": c["text"], "page": c["page"], "embedding": e} for c, e in zip(raw_chunks, embeddings)]

    async def _searchChunks(self, session_id: str, attachments: list, query: str, top_k: int) -> list[dict]:
        import numpy as np

        chunk_texts, chunk_filenames, chunk_pages, chunk_embeddings = [], [], [], []
        for attachment in attachments:
            cached = attachment.get("chunks")
            if cached is None:
                cached = await self._buildChunks(attachment)
                AuthSessionManager.cache_attachment_chunks(session_id, attachment["key"], cached)

            for chunk in cached:
                chunk_texts.append(chunk["text"])
                chunk_filenames.append(attachment["filename"])
                chunk_pages.append(chunk["page"])
                chunk_embeddings.append(chunk["embedding"])

        if not chunk_texts:
            return []

        query_embedding = (await self._indexer._embedder.embed([query]))[0]

        chunk_matrix = np.array(chunk_embeddings)
        query_vector = np.array(query_embedding)
        scores = chunk_matrix @ query_vector / (np.linalg.norm(chunk_matrix, axis=1) * np.linalg.norm(query_vector) + 1e-8)

        top_k = min(top_k, len(chunk_texts))
        top_indices = np.argsort(scores)[::-1][:top_k]

        return [{"filename": chunk_filenames[i], "text": chunk_texts[i], "page": chunk_pages[i]} for i in top_indices]
