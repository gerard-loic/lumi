
import os
import asyncio
from lib.rag.embedder import Embedder
from lib.rag.vectorstore import VectorStore
from lib.config.config import Config

#Correspondance des types de fichiers et extensions
_FILE_TYPE_MAP = {
    ".pdf":  "pdf",
    ".docx": "word",
    ".doc":  "word",
    ".pptx": "powerpoint",
    ".ppt":  "powerpoint",
    ".xlsx": "excel",
    ".xls":  "excel",
    ".md":   "markdown",
    ".html": "html",
    ".htm":  "html",
    ".py":   "code",
    ".js":   "code",
    ".ts":   "code",
    ".txt":  "text",
    ".csv":  "csv",
}

"""
Indexer — Découpage et indexation de documents dans le vectorstore
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>

Prend en charge l'indexation de texte brut et de fichiers (PDF, Word,
PowerPoint, Excel, Markdown, HTML, code, CSV) dans une collection pgvector.

Flux principal :
  1. Extraction du contenu textuel selon le type de fichier
  2. Découpage en chunks avec overlap et calcul des offsets (char + ligne)
  3. Génération des embeddings via Embedder
  4. Persistance dans VectorStore avec les métadonnées associées

"""
class Indexer:
    def __init__(self, collection: str = None):
        #Collection utilisée. Par défaut celle dans la conf
        self._collection    = collection or Config.get("rag.collection")
        self._chunk_size    = Config.get("rag.chunk_size") # taille maximale (en tokens ou caractères) de chaque morceau de texte
        self._chunk_overlap = Config.get("rag.chunk_overlap") #nombre de tokens/caractères qui se chevauchent entre deux chunks consécutifs
        self._embedder      = Embedder()

    # Indexation depuis texte brut
    async def indexText(self, text: str, metadata: dict = None) -> int:
        await VectorStore.ensureTable()
        base_meta = dict(metadata or {})
        if "file_type" not in base_meta and "source" in base_meta:
            ext = os.path.splitext(base_meta["source"])[-1].lower()
            if ext in _FILE_TYPE_MAP:
                base_meta["file_type"] = _FILE_TYPE_MAP[ext]
        chunks = self._chunk(text)
        embeddings = await self._embedder.embed([c["text"] for c in chunks])
        for chunk, emb in zip(chunks, embeddings):
            m = {**base_meta, **chunk}
            text_content = m.pop("text")
            await VectorStore.insert(self._collection, text_content, m, emb)
        return len(chunks)

    #Reindexation d'un texte
    async def reindexText(self, source: str, text: str, metadata: dict = None) -> dict:
        await VectorStore.ensureTable()
        deleted = await VectorStore.deleteBySource(self._collection, source)
        m = {**(metadata or {}), "source": source}
        indexed = await self.indexText(text, metadata=m)
        return {"deleted_chunks": deleted, "chunks_indexed": indexed}

    # Indexation depuis fichier (avec extraction par type)
    async def indexFile(self, path: str, source: str = None, metadata: dict = None) -> int:
        """Indexe un fichier en extrayant son contenu selon son type.
        PDF : extraction page par page via pypdfium2 (métadonnée `page`).
        Autres formats : conversion Markdown via MarkItDown puis chunking texte.
        """
        await VectorStore.ensureTable()
        src = source or os.path.basename(path)
        ext = os.path.splitext(src)[-1].lower()
        base_meta = {**(metadata or {}), "source": src}

        if ext == ".pdf":
            from lib.rag.contenttype.pdf import PdfIndexer
            return await PdfIndexer.index(self, path, base_meta)
        else:
            from markitdown import MarkItDown
            result = await asyncio.to_thread(MarkItDown().convert, path)
            return await self.indexText(result.text_content, metadata=base_meta)

    #Réindexation d'un fichier
    async def reindexFile(self, path: str, source: str = None, metadata: dict = None) -> dict:
        await VectorStore.ensureTable()
        src = source or os.path.basename(path)
        deleted = await VectorStore.deleteBySource(self._collection, src)
        indexed = await self.indexFile(path, source=src, metadata=metadata)
        return {"deleted_chunks": deleted, "chunks_indexed": indexed}

    
    # Suppression d'une collection complete
    async def deleteCollection(self, collection: str = None) -> int:
        return await VectorStore.deleteCollection(collection or self._collection)


    # Chunking avec offsets
    def _chunk(self, text: str) -> list[dict]:
        size, overlap = self._chunk_size, self._chunk_overlap

        # Précalcule les positions de début de chaque ligne pour le mapping char→ligne
        line_starts = [0]
        for i, ch in enumerate(text):
            if ch == '\n':
                line_starts.append(i + 1)

        def char_to_line(pos: int) -> int:
            lo, hi = 0, len(line_starts) - 1
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if line_starts[mid] <= pos:
                    lo = mid
                else:
                    hi = mid - 1
            return lo + 1  # 1-indexé

        chunks = []
        idx = 0
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            chunk_text = text[start:end]
            if chunk_text.strip():
                chunks.append({
                    "text":        chunk_text,
                    "chunk_index": idx,
                    "start_char":  start,
                    "end_char":    end,
                    "start_line":  char_to_line(start),
                    "end_line":    char_to_line(end - 1),
                })
                idx += 1
            start += size - overlap

        for chunk in chunks:
            chunk["total_chunks"] = idx
        return chunks
