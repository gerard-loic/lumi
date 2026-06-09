import pypdfium2 as pdfium
import asyncio
from lib.rag.indexer import Indexer
from lib.rag.vectorstore import VectorStore

class PdfIndexer:
    
    @staticmethod
    async def index(indexer: Indexer, path: str, base_meta: dict):
        pages = await asyncio.to_thread(PdfIndexer._extract_pages, path)
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

    @staticmethod
    def _extract_pages(path:str) -> list[tuple[int, str]]:
        pages = []
        with pdfium.PdfDocument(path) as doc:
            for page_num, page in enumerate(doc, start=1):
                textpage = page.get_textpage()
                text = textpage.get_text_bounded()
                textpage.close()
                page.close()
                if text.strip():
                    pages.append((page_num, text))
        return pages

        