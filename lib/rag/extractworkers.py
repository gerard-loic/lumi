import io
import pypdfium2 as pdfium
from markitdown import MarkItDown

"""
Fonctions d'extraction de texte exécutées dans un sous-processus isolé (cf. TextExtractor, lib/utils/sandbox.py).
Module volontairement léger (pas de dépendance au reste de Lumi) : il est préchargé dans le serveur de fork.
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""

#Texte d'un PDF page par page : [(numéro de page, texte), ...], pages vides ignorées
def extract_pdf_pages(path: str) -> list[tuple[int, str]]:
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


#Conversion Markdown via MarkItDown (formats non paginés : Office, HTML, texte...)
def extract_markitdown(path: str) -> str:
    return MarkItDown().convert(path).text_content


#Conversion Markdown d'un contenu téléchargé (page web, cf. tools/web) : renvoie (titre, texte)
def convert_markitdown_stream(content: bytes, mime_type: str, url: str) -> tuple[str | None, str]:
    result = MarkItDown().convert_stream(io.BytesIO(content), mime_type=mime_type, url=url)
    return result.title, result.text_content or ""
