import asyncio
import socket
import ipaddress
import httpx
from typing import Annotated, Optional
from pydantic import BaseModel, Field
from ddgs import DDGS
from lib.mcp.toolloader import MCPTool, slow_tool, tool_description
from lib.rag.textextractor import TextExtractor

_MAX_PAGE_CHARS = 12_000
_HTTPX_TIMEOUT = 15
_MAX_REDIRECTS = 5
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024


class UrlNonAutoriseeError(ValueError):
    pass


#Une IP n'est acceptée que si elle est publique (routable sur internet) : refuse loopback, réseaux privés,
#link-local (dont 169.254.169.254, métadonnées cloud), multicast, réservés... y compris lorsqu'elle est
#encapsulée dans une adresse IPv6 (IPv4-mapped, 6to4, Teredo)
def _ip_autorisee(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address):
        embedded = ip.ipv4_mapped or ip.sixtofour or (ip.teredo[1] if ip.teredo else None)
        if embedded is not None and not _ip_autorisee(embedded):
            return False
    return ip.is_global and not ip.is_multicast


#Vérifie l'URL et résout son hôte. Renvoie l'IP à contacter : toutes les IP résolues doivent être autorisées
#(sinon un enregistrement DNS mixte public/privé pourrait être exploité).
def _resoudre_url(url: httpx.URL) -> str:
    if url.scheme not in ("http", "https"):
        raise UrlNonAutoriseeError(f"Schéma non autorisé : {url.scheme or '(aucun)'}")
    if not url.host:
        raise UrlNonAutoriseeError("URL sans hôte")

    port = url.port or (443 if url.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(url.host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise UrlNonAutoriseeError(f"Hôte introuvable : {url.host}")

    ips = {ipaddress.ip_address(info[4][0].split("%")[0]) for info in infos}
    if not ips or not all(_ip_autorisee(ip) for ip in ips):
        raise UrlNonAutoriseeError(f"Accès refusé à une adresse non publique : {url.host}")
    return str(sorted(ips, key=lambda ip: ip.version)[0])


#Requête GET protégée contre la SSRF : la connexion se fait directement sur l'IP vérifiée (pas de seconde
#résolution DNS exploitable par DNS rebinding), avec l'en-tête Host et le SNI TLS du nom d'origine pour que le
#certificat reste validé sur ce nom. Les redirections sont suivies manuellement et revérifiées à chaque saut.
#Renvoie (url finale, content-type, contenu), contenu tronqué à _MAX_RESPONSE_BYTES.
def _get_securise(url: str, headers: dict) -> tuple[str, str, bytes]:
    current = httpx.URL(url)
    #trust_env=False : un proxy défini par variable d'environnement résoudrait lui-même le nom, contournant la vérification
    with httpx.Client(timeout=_HTTPX_TIMEOUT, follow_redirects=False, trust_env=False) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            ip = _resoudre_url(current)
            request = client.build_request(
                "GET",
                current.copy_with(host=ip),
                headers={**headers, "Host": current.netloc.decode("ascii")},
                extensions={"sni_hostname": current.host},
            )
            response = client.send(request, stream=True)
            try:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise UrlNonAutoriseeError("Redirection sans destination")
                    current = current.join(location)
                    continue

                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) >= _MAX_RESPONSE_BYTES:
                        del content[_MAX_RESPONSE_BYTES:]
                        break
                return str(current), response.headers.get("content-type", ""), bytes(content)
            finally:
                response.close()

    raise UrlNonAutoriseeError(f"Trop de redirections (> {_MAX_REDIRECTS})")


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

    @slow_tool
    @tool_description(name="[web.rechercher_sur_internet]")
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

    @slow_tool
    @tool_description(name="[web.lire_page_web]")
    async def lire_page_web(
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
        #Téléchargement (bloquant) hors de la boucle événementielle
        final_url, content_type, content = await asyncio.to_thread(_get_securise, url, headers)

        #Contenu d'un serveur quelconque, potentiellement piégé (bombe de décompression, PDF pathologique...) :
        #conversion dans un sous-processus isolé, comme les pièces jointes (cf. TextExtractor, lib/utils/sandbox.py)
        titre, contenu = await TextExtractor.convertContent(
            content,
            mime_type=content_type.split(";")[0].strip(),
            url=final_url,
        )
        titre = titre or url

        if len(contenu) > _MAX_PAGE_CHARS:
            contenu = contenu[:_MAX_PAGE_CHARS] + "\n\n[...contenu tronqué]"

        return ContenuPage(titre=titre, url=url, contenu=contenu)
