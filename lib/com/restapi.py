import httpx
from lib.config.config import Config
from lib.com.filter_builder import FilterBuilder
from urllib.parse import urlencode
import sys

class RestApi:
    @staticmethod
    def setBasicAuthentification(basicToken:str):
        RestApi.basicToken = basicToken

    @staticmethod
    def show(endpoint:str, id:int|str, relations:list=[]):
        #Préparation des paramètres
        relations = ':'.join(relations)
        url = f"{Config.get(key='APP_URL', type='env')}/api/{endpoint}/{id}"
        if relations != "":
            url += f"?with={relations}"

        try:
            with httpx.Client() as client:
                r = client.get(
                    url,
                    headers={"Authorization": f"Bearer {RestApi.basicToken}", "Accept": "application/json"},
                )
                r.raise_for_status()
                data = r.json()
                data = data['data']

                return data

        except Exception as e:
            print(f"ERREUR : {str(e)}", file=sys.stderr, flush=True)

    @staticmethod
    def list(endpoint:str, relations:list=[], order:str=None, limit:int=20, filters:list[dict]|None=None):
        print("LIST")
        #Préparation des paramètres
        url = f"{Config.get(key='APP_URL', type='env')}/api/{endpoint}"

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

        print(url, file=sys.stderr, flush=True)

        try:
            with httpx.Client() as client:
                r = client.get(
                    url,
                    headers={"Authorization": f"Bearer {RestApi.basicToken}", "Accept": "application/json"},
                )
                r.raise_for_status()
                data = r.json()
                print(data, file=sys.stderr, flush=True)
                data = data['data']
                print(len(data), file=sys.stderr, flush=True)
                return data

        except Exception as e:
            print(f"ERREUR : {str(e)}", file=sys.stderr, flush=True)

