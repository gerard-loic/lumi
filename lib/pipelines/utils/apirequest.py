import json
import os

import requests

from lib.pipelines.block import Block
from lib.pipelines.pipelinecontext import PipelineContext
from lib.log.logger import Logger, ERROR, OK

#ApiRequest : classe de base mutualisée des blocs d'appel HTTP (ApiGet / ApiPost / ApiPut / ApiDelete).
#Elle ne réside pas dans lib/pipelines/blocks pour que chaque module de ce paquet reste un bloc
#autonome et directement instanciable ; les blocs concrets se contentent d'en hériter et de fixer _METHOD.
#Effectue une requête REST vers une URL et écrit la réponse (statut, en-têtes, corps) dans le contexte.
#La méthode HTTP est portée par la sous-classe (attribut _METHOD) ; elle peut aussi être forcée
#via la clé de configuration "method" quand cette classe est utilisée directement comme bloc.
#
#Paramètres de configuration (clé "config" du bloc) :
#  - url            (str,            obligatoire)   : URL complète de l'endpoint ; les variables de contexte y sont interpolées.
#  - method         (str,            défaut _METHOD): méthode HTTP ("GET", "POST", ...) ; ignorée si la sous-classe impose _METHOD.
#  - headers        (dict,           défaut {})     : en-têtes HTTP ; les valeurs chaine sont interpolées via le contexte.
#  - params         (dict,           défaut {})     : paramètres de query string ; valeurs chaine interpolées.
#  - body           (dict|list|str,  défaut None)   : corps de la requête (surtout POST/PUT) ; chaines interpolées récursivement.
#  - send_json      (bool,           défaut True)   : True -> body sérialisé en JSON + en-têtes Accept/Content-Type JSON et
#                                                     réponse parsée en JSON ; False -> body envoyé tel quel (form/raw) et
#                                                     réponse renvoyée en texte brut. Ignoré pour la construction du corps
#                                                     quand multipart est actif (voir ci-dessous), mais gouverne toujours
#                                                     le parsing de la réponse.
#  - multipart      (bool,           défaut False)  : True -> le corps est envoyé en multipart/form-data. Chaque paire
#                                                     clé/valeur de "body" devient un champ de formulaire (valeurs non
#                                                     chaine sérialisées en JSON). Forcé implicitement dès que "files"
#                                                     est non vide.
#  - files          (dict,           défaut {})     : fichiers à joindre en multipart/form-data ; active multipart.
#                                                     {"champ": "/chemin/fichier"} ou
#                                                     {"champ": {"path": "...", "filename": "...", "content_type": "..."}}.
#                                                     Les chaines (chemins, noms) sont interpolées via le contexte.
#  - auth           (dict,           défaut {})     : authentification. {"type":"basic","username":...,"password":...}
#                                                     ou {"type":"bearer","token":...}.
#  - timeout        (int|float,      défaut 30)     : délai d'attente en secondes.
#  - verify_ssl     (bool,           défaut True)   : vérification du certificat TLS du serveur.
#  - allow_redirects(bool,           défaut True)   : suivi automatique des redirections HTTP.
#  - fail_on_error  (bool,           défaut True)   : True -> un statut HTTP >= 400 fait échouer le bloc (execute renvoie False),
#                                                     la réponse restant tout de même écrite dans le contexte.
#  - output         (str,            défaut "result"): clé du contexte où stocker le résultat.
#
#Résultat écrit dans le contexte (clé "output") :
#  {
#    "status":  int   -> code de statut HTTP,
#    "ok":      bool  -> True si statut < 400,
#    "headers": dict  -> en-têtes de la réponse,
#    "body":    dict|list|str -> corps parsé en JSON si send_json et parsable, sinon texte brut
#  }
class ApiRequest(Block):
    #Méthode HTTP imposée par la sous-classe ; None -> lue depuis la config ("method"), défaut "GET".
    _METHOD = None

    def __init__(self, block_uid:str, config:dict, on_success_block:str=None, on_error_block:str=None):
        super().__init__(self.__class__.__name__, block_uid, config, on_success_block=on_success_block, on_error_block=on_error_block)

    def execute(self, context:PipelineContext):
        #Récupération de la configuration
        url = context.getConfig(key="url", default="")
        method = (self._METHOD or context.getConfig(key="method", default="GET") or "GET").upper()
        headers = self._interpolate(context, context.getConfig(key="headers", default={}) or {})
        params = self._interpolate(context, context.getConfig(key="params", default={}) or {})
        body = self._interpolate(context, context.getConfig(key="body", default=None))
        send_json = context.getConfig(key="send_json", default=True)
        multipart = context.getConfig(key="multipart", default=False)
        files_conf = self._interpolate(context, context.getConfig(key="files", default={}) or {})
        auth_conf = self._interpolate(context, context.getConfig(key="auth", default={}) or {})
        timeout = context.getConfig(key="timeout", default=30)
        verify_ssl = context.getConfig(key="verify_ssl", default=True)
        allow_redirects = context.getConfig(key="allow_redirects", default=True)
        fail_on_error = context.getConfig(key="fail_on_error", default=True)
        output = context.getConfig(key="output", default="result")

        if not url:
            Logger.write(f"[Block {self._class_name}] Missing 'url' in config", type=ERROR)
            return False

        #Authentification : basic (login/mot de passe) ou bearer (jeton porté par un en-tête Authorization)
        request_auth = None
        auth_type = str(auth_conf.get("type", "")).lower()
        if auth_type == "basic":
            request_auth = (auth_conf.get("username", ""), auth_conf.get("password", ""))
        elif auth_type == "bearer":
            headers = {**headers, "Authorization": f"Bearer {auth_conf.get('token', '')}"}

        #Construction du corps selon le mode demandé :
        #  - multipart (multipart=True ou files non vide) : champs de "body" + fichiers de "files" transmis
        #    via files= pour que requests génère un Content-Type multipart/form-data avec frontière.
        #  - send_json : corps transmis via json= (sérialisation + Content-Type application/json automatiques),
        #    et on annonce Accept: application/json.
        #  - sinon : corps passé tel quel via data= (form urlencodée pour un dict, contenu brut pour une chaine).
        use_multipart = bool(multipart or files_conf)
        json_body = None
        data_body = None
        files_arg = None
        opened_files = []
        if use_multipart:
            files_arg = []
            if isinstance(body, dict):
                for name, value in body.items():
                    if not isinstance(value, (str, bytes)):
                        value = json.dumps(value)
                    files_arg.append((name, (None, value)))
            elif body is not None:
                Logger.write(f"[Block {self._class_name}] multipart : 'body' ignoré (doit être un objet clé/valeur)", type=ERROR)
            for field, spec in files_conf.items():
                if isinstance(spec, dict):
                    path = spec.get("path", "")
                    filename = spec.get("filename") or os.path.basename(path)
                    content_type = spec.get("content_type")
                else:
                    path = spec
                    filename = os.path.basename(path)
                    content_type = None
                try:
                    handle = open(path, "rb")
                except OSError as e:
                    for fh in opened_files:
                        fh.close()
                    Logger.write(f"[Block {self._class_name}] multipart : fichier '{path}' illisible : {e}", type=ERROR)
                    return False
                opened_files.append(handle)
                part = (filename, handle, content_type) if content_type else (filename, handle)
                files_arg.append((field, part))
            if send_json:
                headers = {"Accept": "application/json", **headers}
        elif body is not None:
            if send_json:
                json_body = body
                headers = {"Accept": "application/json", **headers}
            else:
                data_body = body

        try:
            Logger.write(method)
            Logger.write(url)
            Logger.write(params)
            response = requests.request(
                method,
                url,
                headers=headers or None,
                params=params or None,
                json=json_body,
                data=data_body,
                files=files_arg or None,
                auth=request_auth,
                timeout=timeout,
                verify=verify_ssl,
                allow_redirects=allow_redirects,
            )
            Logger.write("////////////////////////////////////")
            Logger.write(response)
        except requests.RequestException as e:
            Logger.write(f"[Block {self._class_name}] {method} {url} failed : {e}", type=ERROR)
            return False
        finally:
            for fh in opened_files:
                fh.close()

        #Corps de réponse : parsé en JSON quand send_json est actif et que le contenu est parsable,
        #sinon renvoyé en texte brut pour rester exploitable par les blocs suivants.
        if send_json:
            try:
                response_body = response.json()
            except ValueError:
                response_body = response.text
        else:
            response_body = response.text

        result = {
            "status":  response.status_code,
            "ok":      response.ok,
            "headers": dict(response.headers),
            "body":    response_body,
        }
        context.set(output, result)

        if fail_on_error and not response.ok:
            Logger.write(f"[Block {self._class_name}] {method} {url} -> HTTP {response.status_code}", type=ERROR)
            return False

        Logger.write(f"[Block {self._class_name}] {method} {url} -> HTTP {response.status_code}", type=OK)
        return True

    #Interpole récursivement les chaines contenues dans value (chaine, dict ou list) avec les
    #variables du contexte. getConfig n'applique cette transformation qu'aux valeurs chaine de
    #premier niveau : on la propage ici aux dicts/lists (headers, params, body, auth).
    def _interpolate(self, context:PipelineContext, value):
        if isinstance(value, str):
            return context.transform(text=value)
        if isinstance(value, dict):
            return {k: self._interpolate(context, v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._interpolate(context, v) for v in value]
        return value
