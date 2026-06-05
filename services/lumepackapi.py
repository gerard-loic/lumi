import httpx
from urllib.parse import urlencode
from lib.mcp.services import Service
import sys

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



class LumePackAPI(Service):

    def __init__(self, data:dict):
        service_format = {
            "url" : "str",
            "timeout" : "int"
        }
        super().__init__(data=data, serviceDataFormat=service_format)
        self.timeout = data.get("timeout", 10)

    def checkAuthentication(self, authorization:dict):
        if "token" not in authorization:
            raise Exception("token must be submitted in auth request")
        
        #On vérifie que le token est valide
        #Préparation des paramètres
        url = f"{self.getConfValue(key="url")}/api/auth"
        token = authorization["token"]

        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.get(
                    url,
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                )
                r.raise_for_status()

                if r.status_code == 200:
                    self.authenticated = True
                    self.authData = authorization
                    return True
        except httpx.HTTPStatusError as e:
            print(f"ERREUR auth {e.response.status_code} : {e.response.text}")
            return False
        except httpx.TimeoutException:
            print(f"ERREUR auth : timeout après {self.timeout}s")
            return False
        except httpx.RequestError as e:
            print(f"ERREUR auth réseau : {e}")
            return False

        return False

    
    def get(self, endpoint:str, arguments:dict = {}):
        url = f"{self.getConfValue(key='url')}/api/{endpoint}?{urlencode(arguments)}"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.get(
                    url,
                    headers={"Authorization": f"Bearer {self.authData["token"]}", "Accept": "application/json"},
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
        #Préparation des paramètres
        relations = ':'.join(relations)
        url = f"{self.getConfValue(key='url')}/api/{endpoint}/{id}"
        if relations != "":
            url += f"?with={relations}"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.get(
                    url,
                    headers={"Authorization": f"Bearer {self.authData["token"]}", "Accept": "application/json"},
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
        #Préparation des paramètres
        url = f"{self.getConfValue(key='url')}/api/{endpoint}"

        parameters = {}
        relations = ':'.join(relations)
        if relations != "":
            parameters["with"] = relations
        if order != None:
            parameters["order"] = order
        parameters["limit"] = limit
        if filters:
            parameters["filters"] = FilterBuilder.build(filters)

        url += "?"+urlencode(parameters)

        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.get(
                    url,
                    headers={"Authorization": f"Bearer {self.authData["token"]}", "Accept": "application/json"},
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

