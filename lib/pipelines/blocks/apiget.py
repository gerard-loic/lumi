from lib.pipelines.utils.apirequest import ApiRequest

#Bloc ApiGet : appelle une API REST en HTTP GET. Les paramètres d'appel proviennent de la config du bloc.
#
#Paramètres de configuration (clé "config" du bloc) :
#  - url            (str,   obligatoire) : URL complète de l'endpoint ; variables de contexte interpolées.
#  - headers        (dict,  défaut {})   : en-têtes HTTP ; valeurs chaine interpolées.
#  - params         (dict,  défaut {})   : paramètres de query string ; valeurs chaine interpolées.
#  - send_json      (bool,  défaut True) : True -> en-tête Accept application/json et réponse parsée en JSON ;
#                                          False -> réponse renvoyée en texte brut.
#  - auth           (dict,  défaut {})   : {"type":"basic","username":...,"password":...} ou {"type":"bearer","token":...}.
#  - timeout        (int,   défaut 30)   : délai d'attente en secondes.
#  - verify_ssl     (bool,  défaut True) : vérification du certificat TLS.
#  - allow_redirects(bool,  défaut True) : suivi des redirections HTTP.
#  - fail_on_error  (bool,  défaut True) : un statut HTTP >= 400 fait échouer le bloc.
#  - output         (str,   défaut "result") : clé du contexte où stocker {"status","ok","headers","body"}.
#
#Le corps de requête (body) n'est pas utilisé en GET ; voir ApiPost / ApiPut pour l'envoi de données.
class ApiGet(ApiRequest):
    _METHOD = "GET"
