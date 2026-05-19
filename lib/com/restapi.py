import httpx
from lib.config.config import Config
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
