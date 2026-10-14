import os
import re
import asyncio
import threading
import weakref
import httpx
from typing import Annotated, Literal, Optional
from pydantic import BaseModel, Field
from lib.config.config import Config
from lib.mcp.toolloader import MCPTool, slow_tool, tool_description
from lib.process.processmanager import ProcessManager
from lib.log.logger import Logger, ERROR, WARNING, INFO

_API_URL = "https://api.tavily.com"
_MAX_PAGE_CHARS = 12_000
_MAX_URLS = 5
_MAX_ATTEMPTS = 3
_RETRY_STATUS = {429, 500, 502, 503, 504}
_MAX_SEARCHES_PER_TURN = 3
_MAX_EXTRACTS_PER_TURN = 2
#Contenu renvoyé pour chaque résultat de recherche (config `tavily.search_mode`) :
#  - "snippets"  : extrait court fourni par Tavily ;
#  - "full"      : contenu complet de la page, tronqué à `full_max_chars` ;
#  - "retrieval" : contenu complet découpé et vectorisé, seuls les `retrieval_top_k` passages les plus proches
#                  de la requête (tous résultats confondus) sont renvoyés.
_FULL_MAX_CHARS = 4_000
_RETRIEVAL_TOP_K = 8
_RETRIEVAL_MAX_CHARS_PER_PAGE = 20_000
_RETRIEVAL_MIN_CHUNK_CHARS = 80
_RETRIEVAL_CHUNK_SIZE = 1_500
_RETRIEVAL_SCORE_MARGIN = 0.15
_MIN_RELATIVE_SCORE = 0.5


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


#Nombre d'appels par tour d'agent et par outil. Le tour est représenté par le process courant (enfant de la session
#créé à chaque message, ou process d'un bloc Agent de pipeline) : indexé faiblement par ce process, le compteur
#disparaît avec lui en fin de tour.
_appels_par_tour: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_appels_lock = threading.Lock()


#Comptabilise un appel à l'outil dans le budget du tour courant (config `tavily.<cle_limite>`, 0 = illimité).
#Renvoie (autorisé, appels restants après celui-ci) ; restants vaut None si aucune limite ne s'applique
#(limite désactivée, ou appel hors tour d'agent).
def _consommer_budget(outil: str, cle_limite: str, defaut: int) -> tuple[bool, Optional[int]]:
    limite = _config(cle_limite, defaut)
    process = ProcessManager.getCurrent()
    if not limite or process is None:
        return True, None
    with _appels_lock:
        compteurs = _appels_par_tour.setdefault(process, {})
        if compteurs.get(outil, 0) >= limite:
            return False, 0
        compteurs[outil] = compteurs.get(outil, 0) + 1
        return True, limite - compteurs[outil]


#Liens et images Markdown, y compris quand l'URL contient elle-même des parenthèses (ex. javascript:void(0))
#ou est suivie d'un titre (infobulle) : [texte](url "titre")
_RE_IMAGE = re.compile(r"!\[[^\]]*\]\((?:[^()]|\([^()]*\))*\)")
_RE_LIEN = re.compile(r"\[([^\]]*)\]\((?:[^()]|\([^()]*\))*\)")
_RE_HTML = re.compile(r"</?[a-zA-Z][^<>]{0,200}>")
#Expressions de gabarit JavaScript non évaluées (pages rendues côté navigateur), ex. ${notification.message}
_RE_GABARIT = re.compile(r"\$\{[^}\n]*\}")
_RE_ESPACES = re.compile(r"(?<=\S)[ \t]{2,}")
_RE_PUCE_VIDE = re.compile(r"^[ \t]*[*-][ \t]*$", re.MULTILINE)
_RE_LIGNES_VIDES = re.compile(r"\n{3,}")
_RE_SEPARATEUR_TABLEAU = re.compile(r"^\|?\s*:?-{3,}")


#Allège le Markdown renvoyé par Tavily avant troncature ou découpage : les pages comportent souvent des milliers de
#caractères de menus et de liens (URL, infobulles) qui repoussent le contenu utile au-delà des limites.
#Les liens sont remplacés par leur texte, les images et balises HTML supprimées, les blancs réduits.
def _nettoyer(contenu: str) -> str:
    contenu = contenu.replace("\xa0", " ")
    contenu = _RE_IMAGE.sub("", contenu)
    contenu = _RE_LIEN.sub(r"\1", contenu)
    contenu = _RE_HTML.sub("", contenu)
    contenu = _RE_GABARIT.sub("", contenu)
    contenu = _RE_ESPACES.sub(" ", contenu)
    contenu = _RE_PUCE_VIDE.sub("", "\n".join(ligne.rstrip() for ligne in contenu.split("\n")))
    return _RE_LIGNES_VIDES.sub("\n\n", contenu).strip()


#URL utilisable par Tavily, ou None. Les URL sans schéma (ex. "meteofrance.com/...", fréquentes de la part du LLM)
#sont complétées en https plutôt que rejetées.
def _normaliser_url(url: str) -> Optional[str]:
    if "://" not in url:
        url = "https://" + url.lstrip("/")
    try:
        parsed = httpx.URL(url)
    except Exception:
        return None
    return url if parsed.scheme in ("http", "https") and parsed.host else None


def _tronquer(contenu: str) -> str:
    if len(contenu) > _MAX_PAGE_CHARS:
        return contenu[:_MAX_PAGE_CHARS] + "\n\n[...contenu tronqué]"
    return contenu


#Découpe un texte en passages d'au plus `taille` caractères, en coupant entre les lignes (une ligne trop longue est
#coupée en morceaux). Un passage qui commence au milieu d'un tableau Markdown reprend l'en-tête du tableau, pour que
#les valeurs restent associées à leurs colonnes (ex. les mois d'un relevé climatologique).
def _decouper(texte: str, taille: int) -> list[str]:
    lignes = texte.split("\n")
    passages, courant, longueur = [], [], 0
    entete = None
    for i, ligne in enumerate(lignes):
        if not ligne.lstrip().startswith("|"):
            entete = None
        elif i + 1 < len(lignes) and _RE_SEPARATEUR_TABLEAU.match(lignes[i + 1].strip()):
            entete = [ligne, lignes[i + 1]]
            #En-tête trop volumineux pour être répété dans chaque passage
            if sum(len(l) + 1 for l in entete) > taille // 2:
                entete = None

        for morceau in [ligne[j:j + taille] for j in range(0, len(ligne), taille)] or [""]:
            if courant and longueur + len(morceau) + 1 > taille:
                passages.append("\n".join(courant))
                courant, longueur = [], 0
                if entete and ligne not in entete:
                    courant = list(entete)
                    longueur = sum(len(l) + 1 for l in entete)
            courant.append(morceau)
            longueur += len(morceau) + 1
    if courant:
        passages.append("\n".join(courant))
    return [p for p in passages if p.strip()]


#Passage de navigation (menu, plan du site) : une majorité de lignes sont des entrées de liste courtes. Ces passages
#reprennent les mots-clés du site et devancent souvent le contenu utile en similarité.
def _cle_url(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", (url or "").strip().lower()).rstrip("/")


#Écarte les résultats que Tavily juge nettement moins pertinents que le meilleur (score < `min_relative_score` x
#meilleur score) et les doublons (même page en http/https, avec ou sans www) : d'un doublon, on garde la copie
#dont le contenu est le plus riche (l'une peut n'avoir aucun contenu complet), au rang de la mieux classée.
def _filtrer_resultats(resultats: list[dict]) -> list[dict]:
    seuil = _config("min_relative_score", _MIN_RELATIVE_SCORE) * max((r.get("score") or 0 for r in resultats), default=0)
    gardes: dict[str, dict] = {}
    for r in resultats:
        if (r.get("score") or 0) < seuil:
            continue
        cle = _cle_url(r.get("url"))
        taille = len(r.get("raw_content") or r.get("content") or "")
        if cle not in gardes or taille > len(gardes[cle].get("raw_content") or gardes[cle].get("content") or ""):
            gardes[cle] = r
    return list(gardes.values())


def _est_navigation(passage: str) -> bool:
    lignes = [l.strip() for l in passage.split("\n") if l.strip()]
    entrees = [l for l in lignes if l[:2] in ("* ", "- ") and len(l) <= 40]
    return len(entrees) >= 5 and len(entrees) >= 0.7 * len(lignes)


#Mode "full" : contenu complet du résultat, tronqué ; extrait Tavily si la page n'a pas pu être récupérée
def _contenu_complet(resultat: dict) -> str:
    contenu = _nettoyer(resultat.get("raw_content") or "")
    if not contenu:
        return _nettoyer(resultat.get("content") or "")
    max_chars = _config("full_max_chars", _FULL_MAX_CHARS)
    if len(contenu) > max_chars:
        return contenu[:max_chars] + "\n\n[...contenu tronqué]"
    return contenu


#Mode "retrieval" : découpe le contenu des résultats et ne garde que les passages les plus proches de la requête,
#comme le micro-RAG des pièces jointes (cf. AttachmentRetriever) avec l'embedder de la collection RAG
#`tavily.retrieval_collection`, ou à défaut de celle du profil de l'agent ; rien n'est stocké. Le découpage est
#propre aux pages web (`retrieval_chunk_size`, cf. _decouper) : celui des collections, prévu pour des documents
#rédigés, morcelle les tableaux.
#Renvoie {url: passages retenus}, les URL étant ordonnées par pertinence de leur meilleur passage.
async def _passages_pertinents(requete: str, resultats: list[dict]) -> dict[str, str]:
    import numpy as np
    from lib.rag.collection import RagCollection
    from lib.rag.embedder import Embedder

    collection = _config("retrieval_collection", None)
    if not collection:
        process = ProcessManager.getCurrent()
        agent_ctx = process.getAgentContext() if process else None
        collection = RagCollection.ofProfile(agent_ctx.getProfileConfig() if agent_ctx else None)
    embedder = Embedder(collection)
    taille = _config("retrieval_chunk_size", _RETRIEVAL_CHUNK_SIZE)

    chunks = []
    for r in resultats:
        texte = _nettoyer(r.get("raw_content") or r.get("content") or "")[:_RETRIEVAL_MAX_CHARS_PER_PAGE]
        #Les fragments de fin de découpage trop courts (sauf s'ils sont tout le contenu) et les menus n'apportent rien
        chunks.extend(
            (r.get("url") or "", passage) for passage in _decouper(texte, taille)
            if (len(passage.strip()) >= _RETRIEVAL_MIN_CHUNK_CHARS or len(texte) < _RETRIEVAL_MIN_CHUNK_CHARS)
            and not _est_navigation(passage)
        )
    if not chunks:
        return {}

    #Requête et passages encodés en un seul appel
    vecteurs = await embedder.embed([requete] + [texte for _, texte in chunks])
    query_vector = np.array(vecteurs[0])
    chunk_matrix = np.array(vecteurs[1:])
    scores = chunk_matrix @ query_vector / (np.linalg.norm(chunk_matrix, axis=1) * np.linalg.norm(query_vector) + 1e-8)

    #Les passages nettement moins proches de la requête que le meilleur ne sont pas renvoyés, même si le top_k
    #n'est pas atteint : ils alourdissent le contexte sans apporter d'information utile
    plancher = scores.max() - _config("retrieval_score_margin", _RETRIEVAL_SCORE_MARGIN)
    passages: dict[str, list[str]] = {}
    for i in np.argsort(scores)[::-1][:_config("retrieval_top_k", _RETRIEVAL_TOP_K)]:
        if scores[i] < plancher:
            break
        url, texte = chunks[i]
        passages.setdefault(url, []).append(texte.strip())
    return {url: "\n[...]\n".join(textes) for url, textes in passages.items()}


class ResultatRechercheTavily(BaseModel):
    titre: str = Field(description="Titre de la page")
    url: str = Field(description="URL de la page")
    extrait: str = Field(description="Contenu de la page : extrait, contenu complet ou passages les plus pertinents")
    date_publication: Optional[str] = Field(default=None, description="Date de publication (actualités)")


class ResultatsRechercheTavily(BaseModel):
    synthese_non_verifiee: Optional[str] = Field(default=None, description=(
        "Résumé généré automatiquement par le moteur de recherche (option tavily.include_answer), qui peut être faux "
        "ou porter sur une autre date ou un autre lieu : ne jamais en reprendre une valeur absente des extraits"
    ))
    resultats: list[ResultatRechercheTavily] = Field(description="Liste des résultats de recherche")
    avertissement: Optional[str] = Field(default=None, description="Consigne à respecter (budget de recherche)")


class PageTavily(BaseModel):
    url: str = Field(description="URL de la page")
    contenu: str = Field(description="Contenu de la page en Markdown")


class EchecPageTavily(BaseModel):
    url: str = Field(description="URL de la page")
    erreur: str = Field(description="Raison de l'échec")


class ContenuPagesTavily(BaseModel):
    pages: list[PageTavily] = Field(description="Pages lues avec succès")
    echecs: list[EchecPageTavily] = Field(description="Pages n'ayant pas pu être lues")
    avertissement: Optional[str] = Field(default=None, description="Consigne à respecter (budget de lecture)")


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
            Field(default=None, description=(
                "Filtre sur la DATE DE PUBLICATION des pages : day, week, month ou year = publiées depuis moins d'un "
                "jour, d'une semaine, d'un mois ou d'un an. À réserver à l'actualité. Ne pas l'utiliser pour désigner la "
                "période couverte par les données (ex. « relevés de 2025 » : mettre l'année dans la requête, pas ici)"
            )),
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
        Effectue une recherche sur internet et retourne une liste de résultats avec, pour chacun, l'extrait le plus
        pertinent de la page et son URL. À utiliser dès que l'utilisateur demande des informations récentes, une
        actualité, ou tout sujet nécessitant une recherche sur le web. Formuler une requête précise et utiliser les
        filtres (sujet, periode, domaines) dès le premier appel plutôt que multiplier les recherches. Les `extraits`
        suffisent le plus souvent : n'utiliser lire_pages_web que s'ils ne suffisent pas. Toute valeur chiffrée reprise
        dans la réponse doit figurer dans un extrait ; `synthese_non_verifiee`, si présente, n'est qu'un résumé
        automatique qui peut être faux.
        """
        autorise, restants = _consommer_budget("rechercher_web", "max_searches_per_turn", _MAX_SEARCHES_PER_TURN)
        if not autorise:
            Logger.write(f"[Tavily] rechercher_web refusé : budget du tour atteint (requete={requete!r})", type=WARNING)
            return ResultatsRechercheTavily(resultats=[], avertissement=(
                "Budget de recherche atteint pour cette question : aucune nouvelle recherche n'a été effectuée. "
                "Rédige ta réponse avec les informations déjà obtenues, en précisant ce qui n'a pas pu être vérifié."
            ))

        payload = {
            "query": requete,
            "max_results": min(max(1, nb_resultats or 5), 10),
            "topic": sujet or "general",
            "search_depth": _config("search_depth", "basic"),
            #Résumé généré par Tavily : désactivé par défaut, il peut être faux (valeurs d'une autre date ou d'un autre
            #lieu) et le LLM tend à le reprendre tel quel plutôt que de s'appuyer sur les extraits
            "include_answer": bool(_config("include_answer", False)),
        }
        if periode:
            payload["time_range"] = periode
        if domaines_inclus:
            payload["include_domains"] = domaines_inclus
        if domaines_exclus:
            payload["exclude_domains"] = domaines_exclus
        mode = _config("search_mode", "snippets")
        Logger.write(
            f"[Tavily] rechercher_web requete={requete!r} sujet={sujet} periode={periode} "
            f"domaines_inclus={domaines_inclus} domaines_exclus={domaines_exclus} mode={mode}",
            type=INFO,
        )
        if mode in ("full", "retrieval"):
            payload["include_raw_content"] = "markdown"

        data = await _post("/search", payload)
        bruts = _filtrer_resultats(data.get("results", []))
        if len(bruts) < len(data.get("results", [])):
            Logger.write(f"[Tavily] rechercher_web : {len(data.get('results', [])) - len(bruts)} résultat(s) écarté(s) (doublons ou peu pertinents)", type=INFO)
        contenus = {}
        if mode == "full":
            contenus = {r.get("url"): _contenu_complet(r) for r in bruts}
        elif mode == "retrieval":
            try:
                contenus = await _passages_pertinents(requete, bruts)
                #Seuls les résultats dont au moins un passage a été retenu sont renvoyés, par pertinence
                ordre = list(contenus)
                bruts = sorted((r for r in bruts if r.get("url") in contenus), key=lambda r: ordre.index(r.get("url")))
            except Exception as e:
                #Embedder indisponible : repli sur les extraits Tavily plutôt qu'un échec de la recherche
                Logger.write(f"[Tavily] Sélection des passages impossible, repli sur les extraits : {type(e).__name__}: {e}", type=ERROR)
                contenus = {}

        resultats = [
            ResultatRechercheTavily(
                titre=r.get("title") or "",
                url=r.get("url") or "",
                extrait=contenus.get(r.get("url")) or _nettoyer(r.get("content") or ""),
                date_publication=r.get("published_date"),
            )
            for r in bruts
        ]
        avertissement = None
        if restants == 0:
            avertissement = "Dernière recherche autorisée pour cette question : aucune autre recherche ne sera possible."
        Logger.write(
            f"[Tavily] rechercher_web -> {len(resultats)} résultat(s), {sum(len(r.extrait) for r in resultats)} car. : "
            f"{[(r.url, len(r.extrait)) for r in resultats]}" + (f" | synthèse Tavily : {data['answer'][:400]!r}" if data.get("answer") else ""),
            type=INFO,
        )
        return ResultatsRechercheTavily(synthese_non_verifiee=data.get("answer") or None, resultats=resultats, avertissement=avertissement)

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
        À utiliser après rechercher_web, uniquement si les extraits ne suffisent pas. Passer toutes les URL utiles
        en un seul appel plutôt que de lire les pages une par une. Les pages n'ayant pas pu être lues sont listées
        dans `echecs` sans empêcher la lecture des autres : ne pas les redemander.
        """
        Logger.write(f"[Tavily] lire_pages_web urls={urls!r}", type=INFO)
        urls = list(dict.fromkeys(u.strip() for u in urls if u and u.strip()))[:_MAX_URLS]
        echecs = {}
        a_lire = []
        for u in urls:
            normalisee = _normaliser_url(u)
            if normalisee is None:
                echecs[u] = "URL invalide"
            elif normalisee not in a_lire:
                a_lire.append(normalisee)

        #Un appel sans aucune URL valide ne consomme pas de budget
        avertissement = None
        if a_lire:
            autorise, restants = _consommer_budget("lire_pages_web", "max_extracts_per_turn", _MAX_EXTRACTS_PER_TURN)
            if not autorise:
                Logger.write("[Tavily] lire_pages_web refusé : budget du tour atteint", type=WARNING)
                return ContenuPagesTavily(pages=[], echecs=[], avertissement=(
                    "Budget de lecture de pages atteint pour cette question : aucune page n'a été lue. "
                    "Rédige ta réponse avec les informations déjà obtenues, en précisant ce qui n'a pas pu être vérifié."
                ))
            if restants == 0:
                avertissement = "Dernière lecture de pages autorisée pour cette question : aucune autre lecture ne sera possible."

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
                    pages[r["url"]] = _tronquer(_nettoyer(r["raw_content"]))
                else:
                    en_echec.add(r.get("url", ""))
                    echecs[r.get("url", "")] = "Aucun contenu extrait"
            for r in data.get("failed_results", []):
                en_echec.add(r.get("url", ""))
                echecs[r.get("url", "")] = r.get("error") or "Échec de l'extraction"
            #Seules les pages explicitement en échec sont retentées : Tavily peut renvoyer une URL normalisée
            #différente de celle demandée pour une page lue avec succès
            a_lire = [u for u in a_lire if u in en_echec]

        resultat = ContenuPagesTavily(
            pages=[PageTavily(url=u, contenu=c) for u, c in pages.items()],
            echecs=[EchecPageTavily(url=u, erreur=e) for u, e in echecs.items() if u not in pages],
            avertissement=avertissement,
        )
        Logger.write(
            f"[Tavily] lire_pages_web -> pages={[(p.url, len(p.contenu)) for p in resultat.pages]} "
            f"echecs={[(e.url, e.erreur) for e in resultat.echecs]}",
            type=INFO,
        )
        return resultat
