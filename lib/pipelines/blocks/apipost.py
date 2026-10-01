from lib.pipelines.utils.apirequest import ApiRequest

#Bloc ApiPost : appelle une API REST en HTTP POST. Les paramètres d'appel proviennent de la config du bloc.
#
#Paramètres de configuration (clé "config" du bloc) :
#  - url            (str,            obligatoire) : URL complète de l'endpoint ; variables de contexte interpolées.
#  - headers        (dict,           défaut {})   : en-têtes HTTP ; valeurs chaine interpolées.
#  - params         (dict,           défaut {})   : paramètres de query string ; valeurs chaine interpolées.
#  - body           (dict|list|str,  défaut None) : corps de la requête ; chaines interpolées récursivement.
#  - send_json      (bool,           défaut True) : True -> body sérialisé en JSON (Content-Type application/json)
#                                                   et réponse parsée en JSON ; False -> body envoyé en form/raw
#                                                   et réponse renvoyée en texte brut.
#  - multipart      (bool,           défaut False): True -> body envoyé en multipart/form-data (un champ par clé).
#                                                   Implicite dès que "files" est renseigné.
#  - files          (dict,           défaut {})   : fichiers joints en multipart. {"champ": "/chemin"} ou
#                                                   {"champ": {"path": "...", "filename": "...", "content_type": "..."}}.
#  - auth           (dict,           défaut {})   : {"type":"basic","username":...,"password":...} ou {"type":"bearer","token":...}.
#  - timeout        (int,            défaut 30)   : délai d'attente en secondes.
#  - verify_ssl     (bool,           défaut True) : vérification du certificat TLS.
#  - allow_redirects(bool,           défaut True) : suivi des redirections HTTP.
#  - fail_on_error  (bool,           défaut True) : un statut HTTP >= 400 fait échouer le bloc.
#  - output         (str,            défaut "result") : clé du contexte où stocker {"status","ok","headers","body"}.
class ApiPost(ApiRequest):
    _METHOD = "POST"
