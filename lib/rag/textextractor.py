import asyncio

"""
TextExtractor — Extraction de texte brut depuis un fichier selon son type
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>

Logique de dispatch partagée entre l'indexation RAG persistante (Indexer)
et l'extraction pour les pièces jointes conversationnelles (éphémère).
"""
class TextExtractor:
    #Extrait le texte brut d'un fichier. PDF : concaténation page par page (pypdfium2).
    #Autres formats : conversion Markdown via MarkItDown.
    @staticmethod
    async def extract(path: str, ext: str) -> str:
        pages = await TextExtractor.extractPages(path, ext)
        if pages is not None:
            return "\n\n".join(text for _, text in pages)
        from markitdown import MarkItDown
        result = await asyncio.to_thread(MarkItDown().convert, path)
        return result.text_content

    #Extrait le texte page par page (uniquement pour les formats paginés, PDF pour l'instant).
    #Retourne None pour les formats sans notion de page, à charge de l'appelant de fallback sur extract().
    @staticmethod
    async def extractPages(path: str, ext: str) -> list[tuple[int, str]] | None:
        if ext != ".pdf":
            return None
        from lib.rag.contenttype.pdf import PdfIndexer
        return await asyncio.to_thread(PdfIndexer._extract_pages, path)
