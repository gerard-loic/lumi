import os
import asyncio
import httpx
from typing import Annotated, Literal, Optional
from pydantic import BaseModel, Field
from lib.config.config import Config
from lib.mcp.toolloader import MCPTool, slow_tool, tool_description

_API_URL = "https://api.tavily.com"
_MAX_PAGE_CHARS = 12_000
_MAX_URLS = 5
_MAX_ATTEMPTS = 3
_RETRY_STATUS = {429, 500, 502, 503, 504}


class TavilyError(RuntimeError):
    pass


def _config(key: str, default):
    return Config.get(f"tavily.{key}", default=default)


#Clé d'API : config `tavily.api_key`, à défaut variable d'environnement TAVILY_API_KEY
def _api_key() -> str:
    key = _config("api_key", None) or os.environ.get("TAVILY_API_KEY")
    if not key:
        raise TavilyError("Aucune clé d'API Tavily n'est configurée (tavily.api_key ou TAVILY_API_KEY).")
    return key


def _message_erreur(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail", "")
        if isinstance(detail, dict):
            detail = detail.get("error", "")
    except ValueError:
        detail = ""
    return f"Erreur Tavily HTTP {response.status_code}" + (f" : {detail}" if detail else "")


#Appel POST à l'API Tavily, avec nouvelles tentatives (backoff exponentiel) sur les erreurs transitoires :
#limitation de débit, erreurs serveur, erreurs réseau et délais dépassés
async def _post(endpoint: str, payload: dict) -> dict:
    headers = {"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"}
    timeout = _config("timeout", 30)
    last_error = None
    async with httpx.AsyncClient(base_url=_API_URL, timeout=timeout) as client:
        for attempt in range(_MAX_ATTEMPTS):
            if attempt:
                await asyncio.sleep(2 ** (attempt - 1))
            try:
                response = await client.post(endpoint, json=payload, headers=headers)
            except httpx.TransportError as e:
                last_error = TavilyError(f"Erreur réseau lors de l'appel à Tavily : {type(e).__name__}")
                continue
            if response.status_code in _RETRY_STATUS:
                last_error = TavilyError(_message_erreur(response))
                continue
            if response.is_error:
                raise TavilyError(_message_erreur(response))
            return response.json()
    raise last_error


def _tronquer(contenu: str) -> str:
    if len(contenu) > _MAX_PAGE_CHARS:
        return contenu[:_MAX_PAGE_CHARS] + "\n\n[...contenu tronqué]"
    return contenu


class ResultatRechercheTavily(BaseModel):
    titre: str = Field(description="Titre de la page")
    url: str = Field(description="URL de la page")
    extrait: str = Field(description="Extrait pertinent du contenu de la page")
    date_publication: Optional[str] = Field(default=None, description="Date de publication (actualités)")


class ResultatsRechercheTavily(BaseModel):
    reponse: Optional[str] = Field(default=None, description="Réponse synthétique générée à partir des résultats")
    resultats: list[ResultatRechercheTavily] = Field(description="Liste des résultats de recherche")


class PageTavily(BaseModel):
    url: str = Field(description="URL de la page")
    contenu: str = Field(description="Contenu de la page en Markdown")


class EchecPageTavily(BaseModel):
    url: str = Field(description="URL de la page")
    erreur: str = Field(description="Raison de l'échec")


class ContenuPagesTavily(BaseModel):
    pages: list[PageTavily] = Field(description="Pages lues avec succès")
    echecs: list[EchecPageTavily] = Field(description="Pages n'ayant pas pu être lues")


"""
TavilyService — Recherche web et lecture de pages via l'API Tavily
Le téléchargement et la conversion des pages (HTML, PDF...) sont réalisés par Tavily : aucun contenu distant
n'est récupéré ni converti localement.
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class TavilyService(MCPTool):
    name = "tavily"
    description = "Recherche sur internet et lecture de pages web via Tavily"

    @slow_tool
    @tool_description(name="[tavily.rechercher_web]")
    async def rechercher_web(
        self,
        requete: Annotated[
            str,
            Field(description="Requête de recherche en langage naturel ou mots-clés"),
        ],
        nb_resultats: Annotated[
            Optional[int],
            Field(default=5, description="Nombre de résultats souhaités (défaut : 5, max : 10)"),
        ] = 5,
        sujet: Annotated[
            Optional[Literal["general", "news", "finance"]],
            Field(default="general", description="Type de recherche : general (défaut), news (actualités), finance"),
        ] = "general",
        periode: Annotated[
            Optional[Literal["day", "week", "month", "year"]],
            Field(default=None, description="Restreint aux résultats publiés depuis : day, week, month ou year"),
        ] = None,
        domaines_inclus: Annotated[
            Optional[list[str]],
            Field(default=None, description="Limite la recherche à ces domaines (ex: [\"legifrance.gouv.fr\"])"),
        ] = None,
        domaines_exclus: Annotated[
            Optional[list[str]],
            Field(default=None, description="Exclut ces domaines de la recherche"),
        ] = None,
    ) -> ResultatsRechercheTavily:
        """
        Effectue une recherche sur internet et retourne une réponse synthétique ainsi qu'une liste de résultats
        avec leurs extraits les plus pertinents. À utiliser dès que l'utilisateur demande des informations
        récentes, une actualité, ou tout sujet nécessitant une recherche sur le web. Après la recherche, utiliser
        lire_pages_web pour obtenir le contenu complet de pages si les extraits ne suffisent pas.
        """
        payload = {
            "query": requete,
            "max_results": min(max(1, nb_resultats or 5), 10),
            "topic": sujet or "general",
            "search_depth": _config("search_depth", "basic"),
            "include_answer": True,
        }
        if periode:
            payload["time_range"] = periode
        if domaines_inclus:
            payload["include_domains"] = domaines_inclus
        if domaines_exclus:
            payload["exclude_domains"] = domaines_exclus

        data = await _post("/search", payload)
        resultats = [
            ResultatRechercheTavily(
                titre=r.get("title") or "",
                url=r.get("url") or "",
                extrait=r.get("content") or "",
                date_publication=r.get("published_date"),
            )
            for r in data.get("results", [])
        ]
        return ResultatsRechercheTavily(reponse=data.get("answer"), resultats=resultats)

    @slow_tool
    @tool_description(name="[tavily.lire_pages_web]")
    async def lire_pages_web(
        self,
        urls: Annotated[
            list[str],
            Field(description=f"URLs complètes des pages à lire (pages web ou PDF), {_MAX_URLS} maximum"),
        ],
    ) -> ContenuPagesTavily:
        """
        Récupère le contenu d'une ou plusieurs pages web (ou documents PDF en ligne) au format Markdown.
        À utiliser après rechercher_web pour obtenir le détail de pages spécifiques. Les pages n'ayant pas pu
        être lues sont listées dans `echecs` sans empêcher la lecture des autres.
        """
        urls = list(dict.fromkeys(u.strip() for u in urls if u and u.strip()))[:_MAX_URLS]
        echecs = {}
        for u in urls:
            if httpx.URL(u).scheme not in ("http", "https"):
                echecs[u] = "URL invalide (schéma http ou https attendu)"
        a_lire = [u for u in urls if u not in echecs]

        pages = {}
        #Extraction "basic" d'abord, puis nouvelle tentative en "advanced" (rendu plus complet, plus coûteux)
        #pour les seules pages en échec
        profondeurs = list(dict.fromkeys([_config("extract_depth", "basic"), "advanced"]))
        for profondeur in profondeurs:
            if not a_lire:
                break
            data = await _post("/extract", {"urls": a_lire, "extract_depth": profondeur, "format": "markdown"})
            en_echec = set()
            for r in data.get("results", []):
                if r.get("raw_content"):
                    pages[r["url"]] = _tronquer(r["raw_content"])
                else:
                    en_echec.add(r.get("url", ""))
                    echecs[r.get("url", "")] = "Aucun contenu extrait"
            for r in data.get("failed_results", []):
                en_echec.add(r.get("url", ""))
                echecs[r.get("url", "")] = r.get("error") or "Échec de l'extraction"
            #Seules les pages explicitement en échec sont retentées : Tavily peut renvoyer une URL normalisée
            #différente de celle demandée pour une page lue avec succès
            a_lire = [u for u in a_lire if u in en_echec]

        return ContenuPagesTavily(
            pages=[PageTavily(url=u, contenu=c) for u, c in pages.items()],
            echecs=[EchecPageTavily(url=u, erreur=e) for u, e in echecs.items() if u not in pages],
        )
