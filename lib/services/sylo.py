import httpx
from contextlib import AsyncExitStack
from urllib.parse import urlencode
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from lib.services._abstract import Service
from lib.log.logger import Logger, ERROR

"""
Sylo — Service représentant une instance Sylo (https://github.com/gerard-loic/sylo), qui expose à la fois :
  - une API REST CRUD (list/query/get/create/update/delete), réponses {"success": ..., "data": ..., "meta": ...}
  - un serveur MCP Streamable HTTP sur /mcp (si SYLO_MCP_ENABLED=true côté Sylo), dont les outils sont
    filtrés par les permissions de l'utilisateur porteur du token.
API et MCP partagent la même authentification (Authorization: Bearer <token>, token obtenu via POST /users/login) :
le secret conservé dans le wallet ({"token": "..."}) sert donc aux deux.

Côté MCP, le service est toujours connecté en auth "session" par MCPClientManager (lib/mcp/client.py) : sans token,
Sylo n'expose que ses outils publics (login_user), une connexion "static" au démarrage n'aurait donc pas d'intérêt.
Clé de config `mcp` (défaut true) : false pour ne pas se connecter au serveur MCP (ex: SYLO_MCP_ENABLED=false).
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class SyloHelper:
    @staticmethod
    def make_filter_description(entity:str, filterable_fields: list[str], filterable_text_fields: list[str], example:str):
        return (
        f"Expression de filtre sur la liste de {entity}. "
        f"Champs filtrables : {', '.join(filterable_fields)}. "
        "Opérateurs disponibles : == != < > <= >= (comparaisons), IN / NOT IN (dans une liste, ex: status IN ('a', 'b')), "
        "LIKE (contient, insensible à la casse, la valeur est du texte brut, sans joker), "
        "SOUNDEX (recherche phonétique), SIMILAR (recherche tolérante aux fautes de frappe). "
        "Combinaison par AND / OR (AND prioritaire), parenthèses supportées. "
        "Valeurs : nombre, 'texte' entre quotes simples, true/false, null. "
        f"IMPORTANT : pour les champs texte libres ({', '.join(filterable_text_fields)}), "
        "toujours préférer LIKE (ou SIMILAR en cas de doute sur l'orthographe) plutôt que == afin d'éviter les problèmes de casse. "
        f"Exemple — {example}"
        )


class Sylo(Service):

    def __init__(self, name:str, data:dict):
        #`timeout` (défaut 10) et `mcp` (défaut true) sont optionnels : défaultés ici, Service._checkData
        #exigeant la présence de chaque clé déclarée dans service_format (cf. MCPExternalService).
        data = dict(data)
        data.setdefault("timeout", 10)
        data.setdefault("mcp", True)
        service_format = {
            "url" : "str",
            "timeout" : "int",
            "mcp" : "bool",
        }
        super().__init__(name=name, data=data, serviceDataFormat=service_format)
        self.timeout = data["timeout"]

    def _url(self, path:str) -> str:
        return f"{self.getConfValue(key='url').rstrip('/')}/{path.lstrip('/')}"

    # ------------------------------------------------------------------
    # Authentification
    # ------------------------------------------------------------------

    #Authentification d'un utilisateur, à partir de :
    #  - {"token": "..."}                   : validation d'un token existant
    #  - {"login": "...", "password": "..."} : connexion par identifiants (email Sylo), uniquement si allow_credentials (ex: pipeline)
    #Renvoie {"token": "..."} ou False.
    def authenticate(self, authorization:dict, allow_credentials:bool = False):
        if "token" in authorization:
            return self._checkToken(token=authorization["token"])
        if allow_credentials and "login" in authorization and "password" in authorization:
            return self._login(login=authorization["login"], password=authorization["password"])
        Logger.write(f"[SYLO] authenticate : {'token or login/password' if allow_credentials else 'token'} required", type=ERROR)
        return False

    #Sylo n'expose pas de route de vérification de token : on interroge une route protégée du cœur (GET /users).
    #Sylo résout le token avant de vérifier la permission (cf. app/auth.py) : 401 = token invalide/expiré,
    #403 = token valide mais sans permission sur /users, ce qui suffit ici.
    def _checkToken(self, token:str):
        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.get(
                    self._url("users"),
                    params={"limit": 1},
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                )
                if r.status_code == 403:
                    return {"token": token}
                r.raise_for_status()
                return {"token": token}
        except httpx.HTTPStatusError as e:
            Logger.write(f"[SYLO] authenticate (token) erreur {e.response.status_code} : {e.response.text}", type=ERROR)
            return False
        except httpx.TimeoutException:
            Logger.write(f"[SYLO] authenticate (token) timeout après {self.timeout}s", type=ERROR)
            return False
        except httpx.RequestError as e:
            Logger.write(f"[SYLO] authenticate (token) erreur réseau : {e}", type=ERROR)
            return False

    def _login(self, login:str, password:str):
        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.post(
                    self._url("users/login"),
                    json={"email": login, "password": password},
                    headers={"Accept": "application/json"},
                )
                r.raise_for_status()
        except httpx.HTTPStatusError as e:
            Logger.write(f"[SYLO] authenticate erreur {e.response.status_code} pour '{login}' : {e.response.text}", type=ERROR)
            return False
        except httpx.TimeoutException:
            Logger.write(f"[SYLO] authenticate timeout après {self.timeout}s", type=ERROR)
            return False
        except httpx.RequestError as e:
            Logger.write(f"[SYLO] authenticate erreur réseau : {e}", type=ERROR)
            return False

        try:
            response_data = r.json()
        except ValueError:
            Logger.write(f"[SYLO] authenticate : réponse non-JSON (HTTP {r.status_code}) — {r.text!r}", type=ERROR)
            return False
        token = (response_data.get("data") or {}).get("token")
        if not token:
            Logger.write(f"[SYLO] authenticate : token absent dans la réponse — {response_data}", type=ERROR)
            return False
        return {"token": token}

    # ------------------------------------------------------------------
    # API REST
    # ------------------------------------------------------------------

    #Requête authentifiée (token du wallet du process courant) vers l'API. Renvoie le champ `data` de la réponse,
    #ou la réponse complète ({"data": ..., "meta": ...}) si full_response. Lève RuntimeError en cas d'erreur.
    def request(self, method:str, endpoint:str, params:dict|None = None, json:dict|None = None, full_response:bool = False):
        auth = self.getAuth()
        endpoint = endpoint.strip("/")
        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.request(
                    method,
                    self._url(endpoint),
                    params=params,
                    json=json,
                    headers={"Authorization": f"Bearer {auth.get('token', '')}", "Accept": "application/json"},
                )
                r.raise_for_status()
                data = r.json()
                return data if full_response else data.get("data")

        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Erreur API {e.response.status_code} sur {method} /{endpoint} : {self._errorMessage(e.response)}"
            ) from e
        except httpx.TimeoutException:
            raise RuntimeError(f"Timeout après {self.timeout}s sur {method} /{endpoint}") from None
        except httpx.RequestError as e:
            raise RuntimeError(f"Erreur réseau sur {method} /{endpoint} : {e}") from e

    #Message d'une réponse d'erreur Sylo ({"success": false, "error": {"code", "message", "details"}})
    def _errorMessage(self, response) -> str:
        try:
            error = response.json().get("error") or {}
        except ValueError:
            return response.text
        message = error.get("message") or response.text
        if error.get("details") is not None:
            message += f" — {error['details']}"
        return message

    #Appel libre en GET (routes spécifiques d'un projet, hors CRUD)
    def get(self, endpoint:str, arguments:dict = {}):
        return self.request("GET", endpoint, params=arguments)

    def show(self, endpoint:str, id:int|str, relations:list = []):
        params = {"with": ",".join(relations)} if relations else None
        return self.request("GET", f"{endpoint.strip('/')}/{id}", params=params)

    #Liste paginée. `filter` : expression de filtre Sylo (ex: "status == 'active' AND name LIKE 'ali'",
    #cf. SyloHelper.make_filter_description) — envoyée dans le corps via POST /<endpoint>/query.
    #`order` : "champ.ASC,autre.DESC". `page` (1-indexée) prime sur `offset`.
    #with_meta : renvoie {"data": [...], "meta": {"total", "limit", "offset", "page"}} au lieu de la seule liste.
    def list(self, endpoint:str, relations:list = [], order:str = None, limit:int = 20, offset:int = 0, page:int|None = None, filter:str|None = None, with_meta:bool = False):
        endpoint = endpoint.strip("/")
        if filter:
            payload = {"filter": filter, "limit": limit, "offset": offset}
            if page is not None:
                payload["page"] = page
            if order:
                payload["orderby"] = order
            if relations:
                payload["with"] = list(relations)
            response = self.request("POST", f"{endpoint}/query", json=payload, full_response=True)
        else:
            params = {"limit": limit, "offset": offset}
            if page is not None:
                params["page"] = page
            if order:
                params["orderby"] = order
            if relations:
                params["with"] = ",".join(relations)
            response = self.request("GET", endpoint, params=params, full_response=True)
        return response if with_meta else response.get("data")

    def create(self, endpoint:str, data:dict, relations:list = []):
        params = {"with": ",".join(relations)} if relations else None
        return self.request("POST", endpoint, params=params, json=data)

    #Mise à jour partielle (seuls les champs fournis sont modifiés)
    def update(self, endpoint:str, id:int|str, data:dict, relations:list = []):
        params = {"with": ",".join(relations)} if relations else None
        return self.request("PUT", f"{endpoint.strip('/')}/{id}", params=params, json=data)

    #Suppression logique (deleted_at)
    def delete(self, endpoint:str, id:int|str):
        return self.request("DELETE", f"{endpoint.strip('/')}/{id}")

    # ------------------------------------------------------------------
    # Pipelines (bloc ServiceMethod)
    # ------------------------------------------------------------------

    #Appel libre de l'API depuis un pipeline (signature ServiceMethod : method(self, context, params)).
    #Paramètres :
    #  - endpoint (str, obligatoire)  : route appelée (ex: "llm/createlesson").
    #  - method   (str, défaut "POST"): méthode HTTP.
    #  - input    (str, optionnel)    : chemin d'une variable du contexte (ex: "lessonjson") envoyée telle quelle
    #                                   en corps JSON. Un chemin et non "{var}" : l'interpolation produirait une chaine.
    #  - output   (str, défaut "result") : clé du contexte où stocker le champ `data` de la réponse.
    #Lève RuntimeError en cas d'erreur API (échec du bloc).
    def call(self, context, params:dict):
        endpoint = params.get("endpoint")
        if not endpoint:
            raise RuntimeError("paramètre 'endpoint' manquant")
        body = context.resolve(params["input"]) if params.get("input") else None
        result = self.request(params.get("method", "POST").upper(), endpoint, json=body)
        context.set(params.get("output", "result"), result)
        return True

    # ------------------------------------------------------------------
    # MCP
    # ------------------------------------------------------------------

    def isMcpEnabled(self) -> bool:
        return bool(self.getConfValue(key="mcp"))

    #Ouvre la connexion au serveur MCP de Sylo (Streamable HTTP, /mcp/) et l'enregistre dans `stack`
    #(AsyncExitStack possédé par l'appelant, cf. MCPClientManager.open_session_external_tools).
    #`auth_data` : secret du wallet de la session ({"token": "..."}), le même que pour l'API.
    #Même signature que MCPExternalService.connect, pour être piloté de la même façon par MCPClientManager.
    async def connect(self, stack: AsyncExitStack, auth_data: dict | None = None) -> ClientSession:
        headers = {}
        if auth_data and auth_data.get("token"):
            headers["Authorization"] = f"Bearer {auth_data['token']}"

        #Slash final : Sylo monte le serveur MCP via app.mount("/mcp"), /mcp seul déclenche une redirection
        read, write, _ = await stack.enter_async_context(streamablehttp_client(self._url("mcp/"), headers=headers))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        return session
