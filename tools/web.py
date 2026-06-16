import io
import httpx
from typing import Annotated, Optional
from pydantic import BaseModel, Field
from ddgs import DDGS
from markitdown import MarkItDown
from lib.mcp.tools import MCPTool, native_tool, slow_tool

_MAX_PAGE_CHARS = 12_000
_HTTPX_TIMEOUT = 15
_MARKITDOWN = MarkItDown()


class ResultatRecherche(BaseModel):
    titre: str = Field(description="Titre de la page")
    url: str = Field(description="URL de la page")
    extrait: str = Field(description="Extrait du contenu de la page")


class ResultatsRecherche(BaseModel):
    resultats: list[ResultatRecherche] = Field(description="Liste des résultats de recherche")


class ContenuPage(BaseModel):
    titre: str = Field(description="Titre de la page")
    url: str = Field(description="URL de la page")
    contenu: str = Field(description="Contenu de la page en Markdown")


class WebService(MCPTool):
    name = "web"
    description = "Recherche sur internet et lecture de pages web"

    @native_tool
    @slow_tool
    def rechercher_sur_internet(
        self,
        requete: Annotated[
            str,
            Field(description="Requête de recherche en langage naturel ou mots-clés"),
        ],
        nb_resultats: Annotated[
            Optional[int],
            Field(default=5, description="Nombre de résultats souhaités (défaut : 5, max : 10)"),
        ] = 5,
    ) -> ResultatsRecherche:
        """
        Effectue une recherche sur internet via DuckDuckGo et retourne une liste de résultats.
        À utiliser dès que l'utilisateur demande des informations récentes, une actualité, ou tout sujet
        nécessitant une recherche sur le web. Après la recherche, utiliser lire_page_web pour obtenir
        le détail d'une page si nécessaire.
        """
        nb = min(max(1, nb_resultats or 5), 10)
        with DDGS() as ddgs:
            raw = list(ddgs.text(requete, max_results=nb))

        resultats = [
            ResultatRecherche(
                titre=r.get("title", ""),
                url=r.get("href", ""),
                extrait=r.get("body", ""),
            )
            for r in raw
        ]
        return ResultatsRecherche(resultats=resultats)

    @native_tool
    @slow_tool
    def lire_page_web(
        self,
        url: Annotated[
            str,
            Field(description="URL complète de la page web à lire (ex: https://example.com/article)"),
        ],
    ) -> ContenuPage:
        """
        Récupère et retourne le contenu d'une page web au format Markdown, nettoyé des éléments
        de navigation, publicités et scripts. À utiliser après rechercher_sur_internet pour obtenir
        le détail d'une page spécifique.
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }
        response = httpx.get(url, headers=headers, timeout=_HTTPX_TIMEOUT, follow_redirects=True)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        result = _MARKITDOWN.convert_stream(
            io.BytesIO(response.content),
            mime_type=content_type.split(";")[0].strip(),
            url=url,
        )

        titre = result.title or url
        contenu = result.text_content or ""

        if len(contenu) > _MAX_PAGE_CHARS:
            contenu = contenu[:_MAX_PAGE_CHARS] + "\n\n[...contenu tronqué]"

        return ContenuPage(titre=titre, url=url, contenu=contenu)
