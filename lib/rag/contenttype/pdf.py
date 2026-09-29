from lib.rag.indexer import Indexer
from lib.rag.vectorstore import VectorStore


"""
PdfIndexer — Gestion indexation de fichiers PDF
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class PdfIndexer:
    
    @staticmethod
    async def index(indexer: Indexer, path: str, base_meta: dict):
        from lib.rag.textextractor import TextExtractor
        pages = await TextExtractor.extractPages(path, ".pdf")
        total = 0
        for page_num, page_text in pages:
            meta = {**base_meta, "page": page_num}
            chunks = indexer._chunk(page_text)
            embeddings = await indexer._embedder.embed([c["text"] for c in chunks])
            for chunk, emb in zip(chunks, embeddings):
                m = {**meta, **chunk}
                text_content = m.pop("text")
                await VectorStore.insert(indexer._collection, text_content, m, emb)
            total += len(chunks)
        return total
