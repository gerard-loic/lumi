import base64
import httpx
from urllib.parse import urlencode
from lib.services._abstract import Service
from lib.log.logger import Logger, ERROR
from pydantic import Field, BaseModel
from typing import Annotated, Literal, Optional, Any


OrderByField = Annotated[Literal["ASC", "DESC"], Field(description="...")]
LimiteField = Annotated[int, Field(description="Nombre maximal de résultats à retourner")]
class FilterField(BaseModel):
    field: str
    op: str
    value: Any
    logic: Literal["and", "or"] = "and"


class FilterBuilder:
    """Converts a list of filter dicts to the API filter string syntax.

    Each condition dict:
        field   (str)              : attribute name
        op      (str)              : operator — eq, neq, gt, lt, gte, lte,
                                     lk, nlk, ilk, nilk, in, nin,
                                     btw, nbtw, ist, isf
        value   (str|int|float|list): operand(s); omit for ist/isf;
                                     list for in/nin/btw/nbtw
        logic   ("and"|"or")       : how this item joins the PREVIOUS one
                                     (ignored on the first item, default "and")

    To AND/OR a parenthesised group, use a group item instead of field/op:
        {"logic": "and", "group": [...conditions]}

    Example:
        [
            {"field": "status", "op": "eq",  "value": "active"},
            {"field": "amount", "op": "gte", "value": 100, "logic": "and"},
            {"logic": "or", "group": [
                {"field": "type", "op": "in", "value": ["invoice", "credit"]},
            ]},
        ]
        → "status:eq(active)|n|amount:gte(100)|u|[type:in(invoice,credit)]"
    """

    _LOGIC = {"and": "|n|", "or": "|u|"}

    @classmethod
    def build(cls, filters: list[dict]) -> str:
        if not filters:
            return ""
        parts: list[str] = []
        for i, item in enumerate(filters):
            item = item.model_dump() if hasattr(item, "model_dump") else item
            logic = item.get("logic", "and")
            sep = cls._LOGIC.get(logic, "|n|")
            segment = (
                f"[{cls.build(item['group'])}]"
                if "group" in item
                else cls._condition(item)
            )
            parts.append(segment if i == 0 else sep + segment)
        return "".join(parts)

    @classmethod
    def _condition(cls, item: dict) -> str:
        field = item["field"]
        op = item["op"]
        value = item.get("value")

        if op in ("ist", "isf"):
            return f"{field}:{op}()"
        if op in ("in", "nin"):
            v = ",".join(str(x) for x in value) if isinstance(value, list) else str(value)
            return f"{field}:{op}({v})"
        if op in ("btw", "nbtw"):
            if isinstance(value, list) and len(value) == 2:
                return f"{field}:{op}({value[0]},{value[1]})"
            return f"{field}:{op}({value})"
        if op in ("ilk", "nilk"):
            v = str(value).strip("%")
            return f"{field}:{op}(%{v}%)"
        return f"{field}:{op}({value})"


class LumePackAPIHelper:
    @staticmethod
    def make_filters_description(entity:str, filterable_fields: list[str], filterable_text_fields: list[str], example:str):
        return (
        f"Filtres à appliquer sur la liste de {entity}. "
        f"Champs filtrables : {', '.join(filterable_fields)}. "
        "Opérateurs disponibles : eq (égal), neq (différent), gt/lt/gte/lte (comparaisons numériques), "
        "ilk/nilk (correspondance partielle insensible à la casse, fonctionne comme SQL LIKE : % est un joker qui remplace zéro ou plusieurs caractères. Exemples : '%paris%' contient 'paris', 'paris%' commence par 'paris', '%paris' finit par 'paris'. nilk est la négation de ilk), "
        "in/nin (dans une liste — value doit être une liste), "
        "btw/nbtw (entre deux valeurs — value doit être [min, max]), ist/isf (vrai/faux). "
        "Le champ 'logic' relie la condition à la précédente (défaut: 'and'). "
        f"IMPORTANT : pour les champs texte libres ({', '.join(filterable_text_fields)}), "
        "toujours préférer l'opérateur ilk plutôt que eq afin d'éviter les problèmes de casse "
        f"Exemple — {example}"
        )
    

        

class LumePackAPI(Service):

    def __init__(self, name:str, data:dict):
        service_format = {
            "url" : "str",
            "timeout" : "int"
        }
        super().__init__(name=name, data=data, serviceDataFormat=service_format)
        self.timeout = data.get("timeout", 10)
        

    #Authentification d'un utilisateur, à partir de :
    #  - {"token": "..."}                   : validation d'un token existant (ex: client déjà connecté à LumePack)
    #  - {"login": "...", "password": "..."} : connexion par identifiants, uniquement si allow_credentials (ex: pipeline)
    #Renvoie {"token": "..."} ou False.
    def authenticate(self, authorization:dict, allow_credentials:bool = False):
        if "token" in authorization:
            return self._checkToken(token=authorization["token"])
        if allow_credentials and "login" in authorization and "password" in authorization:
            return self._login(login=authorization["login"], password=authorization["password"])
        Logger.write(f"[LUMEPACKAPI] authenticate : {'token or login/password' if allow_credentials else 'token'} required", type=ERROR)
        return False

    def _checkToken(self, token:str):
        url = f"{self.getConfValue(key='url')}/api/auth"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.get(
                    url,
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                )
                r.raise_for_status()
                return {"token": token}
        except httpx.HTTPStatusError as e:
            Logger.write(f"[LUMEPACKAPI] authenticate (token) erreur {e.response.status_code} : {e.response.text}", type=ERROR)
            return False
        except httpx.TimeoutException:
            Logger.write(f"[LUMEPACKAPI] authenticate (token) timeout après {self.timeout}s", type=ERROR)
            return False
        except httpx.RequestError as e:
            Logger.write(f"[LUMEPACKAPI] authenticate (token) erreur réseau : {e}", type=ERROR)
            return False

    def _login(self, login:str, password:str):
        url = f"{self.getConfValue(key='url')}/api/auth/login"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.post(
                    url,
                    files={
                        "login": (None, login),
                        "password": (None, password),
                    },
                    headers={
                        "Accept": "application/json"
                    },
                )
                r.raise_for_status()
                return self._tokenFromResponse(r, context="authenticate")
        except httpx.HTTPStatusError as e:
            Logger.write(f"[LUMEPACKAPI] authenticate erreur {e.response.status_code} pour '{login}' : {e.response.text}", type=ERROR)
            return False
        except httpx.TimeoutException:
            Logger.write(f"[LUMEPACKAPI] authenticate timeout après {self.timeout}s", type=ERROR)
            return False
        except httpx.RequestError as e:
            Logger.write(f"[LUMEPACKAPI] authenticate erreur réseau : {e}", type=ERROR)
            return False

    #api_key : clé d'API propre au connecteur/profil Webex à l'origine de l'appel
    #(cf profiles.<profil>.connectors.webex.api_key), fournie par l'appelant plutôt que
    #lue depuis une config globale.
    #Renvoie {"token": "..."} ou False.
    def webexAuthenticate(self, username: str, api_key: str):
        url = f"{self.getConfValue(key='url')}/api/webex/auth"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                encoded_key = base64.b64encode(api_key.encode()).decode()
                r = client.post(
                    url,
                    files={"login": (None, username)},
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Basic {encoded_key}",
                    },
                )
                r.raise_for_status()
                return self._tokenFromResponse(r, context="webexAuthenticate")
        except httpx.HTTPStatusError as e:
            Logger.write(f"[LUMEPACKAPI] webexAuthenticate erreur {e.response.status_code} pour '{username}' : {e.response.text}", type=ERROR)
            return False
        except httpx.TimeoutException:
            Logger.write(f"[LUMEPACKAPI] webexAuthenticate timeout après {self.timeout}s", type=ERROR)
            return False
        except httpx.RequestError as e:
            Logger.write(f"[LUMEPACKAPI] webexAuthenticate erreur réseau : {e}", type=ERROR)
            return False

    #Extrait le token d'une réponse d'authentification LumePack ({"data": {"token": ...}})
    def _tokenFromResponse(self, r, context:str):
        try:
            response_data = r.json()
        except ValueError:
            Logger.write(f"[LUMEPACKAPI] {context} : réponse non-JSON (HTTP {r.status_code}) — {r.text!r}", type=ERROR)
            return False
        token = response_data.get("data", {}).get("token")
        if not token:
            Logger.write(f"[LUMEPACKAPI] {context} : token absent dans la réponse — {response_data}", type=ERROR)
            return False
        return {"token": token}
    
    def get(self, endpoint:str, arguments:dict = {}):
        auth = self.getAuth()

        url = f"{self.getConfValue(key='url')}/api/{endpoint}?{urlencode(arguments)}"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.get(
                    url,
                    headers={"Authorization": f"Bearer {auth.get("token", "")}", "Accept": "application/json"},
                )
                r.raise_for_status()
                data = r.json()
                return data['data']

        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Erreur API {e.response.status_code} sur /{endpoint} : {e.response.text}"
            ) from e
        except httpx.TimeoutException:
            raise RuntimeError(f"Timeout après {self.timeout}s sur /{endpoint}") from None
        except httpx.RequestError as e:
            raise RuntimeError(f"Erreur réseau sur /{endpoint} : {e}") from e

    def show(self, endpoint:str, id:int|str, relations:list=[]):
        auth = self.getAuth()
        
        #Préparation des paramètres
        relations = ':'.join(relations)
        url = f"{self.getConfValue(key='url')}/api/{endpoint}/{id}"
        if relations != "":
            url += f"?with={relations}"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.get(
                    url,
                    headers={"Authorization": f"Bearer {auth.get("token", "")}", "Accept": "application/json"},
                )
                r.raise_for_status()
                data = r.json()
                return data['data']

        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Erreur API {e.response.status_code} sur /{endpoint}/{id} : {e.response.text}"
            ) from e
        except httpx.TimeoutException:
            raise RuntimeError(f"Timeout après {self.timeout}s sur /{endpoint}/{id}") from None
        except httpx.RequestError as e:
            raise RuntimeError(f"Erreur réseau sur /{endpoint}/{id} : {e}") from e


    def list(self, endpoint:str, relations:list=[], order:str=None, limit:int=20, filters:list[dict]|None=None):
        auth = self.getAuth()
        
        #Préparation des paramètres
        url = f"{self.getConfValue(key='url')}/api/{endpoint}"

        parameters = {}
        relations = ':'.join(relations)
        if relations != "":
            parameters["with"] = relations
        if order != None:
            parameters["sort"] = order
        parameters["limit"] = limit
        if filters:
            parameters["filters"] = FilterBuilder.build(filters)

        url += "?"+urlencode(parameters)

        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.get(
                    url,
                    headers={"Authorization": f"Bearer {auth.get("token", "")}", "Accept": "application/json"},
                )
                r.raise_for_status()
                data = r.json()
                return data['data']

        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Erreur API {e.response.status_code} sur /{endpoint} : {e.response.text}"
            ) from e
        except httpx.TimeoutException:
            raise RuntimeError(f"Timeout après {self.timeout}s sur /{endpoint}") from None
        except httpx.RequestError as e:
            raise RuntimeError(f"Erreur réseau sur /{endpoint} : {e}") from e


