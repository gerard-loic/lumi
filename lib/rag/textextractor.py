import io
import zipfile
from lib.config.config import Config
from lib.utils.sandbox import Sandbox, SandboxError

"""
TextExtractor — Extraction de texte brut depuis un fichier selon son type
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>

Logique de dispatch partagée entre l'indexation RAG persistante (Indexer)
et l'extraction pour les pièces jointes conversationnelles (éphémère).

Les fichiers traités peuvent être piégés (pièces jointes d'utilisateurs) : les archives (docx, xlsx, pptx...)
sont d'abord contrôlées (taille décompressée, nombre d'entrées), puis l'extraction elle-même est faite dans un
sous-processus isolé aux ressources limitées (cf. lib/utils/sandbox.py). Limites : clé de configuration `extraction`.
"""

class ExtractionError(Exception):
    pass


class TextExtractor:
    #Extrait le texte brut d'un fichier. PDF : concaténation page par page (pypdfium2).
    #Autres formats : conversion Markdown via MarkItDown.
    @staticmethod
    async def extract(path: str, ext: str) -> str:
        pages = await TextExtractor.extractPages(path, ext)
        if pages is not None:
            return "\n\n".join(text for _, text in pages)
        from lib.rag.extractworkers import extract_markitdown
        return await TextExtractor._run(extract_markitdown, path)

    #Extrait le texte page par page (uniquement pour les formats paginés, PDF pour l'instant).
    #Retourne None pour les formats sans notion de page, à charge de l'appelant de fallback sur extract().
    @staticmethod
    async def extractPages(path: str, ext: str) -> list[tuple[int, str]] | None:
        if ext != ".pdf":
            return None
        from lib.rag.extractworkers import extract_pdf_pages
        return await TextExtractor._run(extract_pdf_pages, path)

    #Conversion Markdown d'un contenu en mémoire (ex: page web téléchargée, cf. tools/web), isolée comme un fichier :
    #le contenu vient d'un serveur quelconque et peut être piégé au même titre qu'une pièce jointe. Renvoie (titre, texte).
    @staticmethod
    async def convertContent(content: bytes, mime_type: str, url: str) -> tuple[str | None, str]:
        from lib.rag.extractworkers import convert_markitdown_stream
        TextExtractor._checkArchive(io.BytesIO(content))
        return await TextExtractor._sandbox(convert_markitdown_stream, content, mime_type, url)

    #Contrôle du fichier puis extraction isolée
    @staticmethod
    async def _run(func, path: str):
        TextExtractor._checkArchive(path)
        return await TextExtractor._sandbox(func, path)

    @staticmethod
    async def _sandbox(func, *args):
        try:
            return await Sandbox.run(
                func, *args,
                timeout=Config.get("extraction.timeout", 120),
                max_memory_mb=Config.get("extraction.max_memory_mb", 2048),
            )
        except SandboxError as e:
            raise ExtractionError(str(e))

    #Bombe de décompression : une archive est refusée si ses entrées décompressées dépassent la limite. Contrôle
    #fait sur le contenu réel et non sur l'extension (MarkItDown détecte le format d'après le contenu). Les tailles
    #lues dans le répertoire central peuvent mentir, mais zipfile ne décompresse jamais au-delà de la taille déclarée.
    @staticmethod
    #`source` : chemin du fichier ou contenu en mémoire (objet fichier binaire)
    def _checkArchive(source: str | io.BytesIO) -> None:
        if not zipfile.is_zipfile(source):
            return
        max_size = Config.get("extraction.max_uncompressed_mb", 500) * 1024 * 1024
        max_entries = Config.get("extraction.max_archive_entries", 10_000)
        try:
            with zipfile.ZipFile(source) as archive:
                entries = archive.infolist()
        except (zipfile.BadZipFile, ValueError) as e:
            raise ExtractionError(f"Archive invalide : {e}")
        if len(entries) > max_entries:
            raise ExtractionError(f"Archive refusée : trop d'entrées ({len(entries)} > {max_entries})")
        if sum(entry.file_size for entry in entries) > max_size:
            raise ExtractionError("Archive refusée : taille décompressée trop importante")
