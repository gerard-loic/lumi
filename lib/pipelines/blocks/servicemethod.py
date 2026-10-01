from lib.pipelines._abstract import Block
from lib.pipelines.pipelinecontext import PipelineContext
from lib.services.servicemanager import ServiceManager
from lib.log.logger import Logger, ERROR, OK

#Bloc ServiceMethod : appelle une méthode d'un service déclaré dans la config (clé "services"), ex. LumePackAPI.test.
#La méthode doit avoir la signature method(self, context, params), même convention que le bloc PythonScript :
#elle reçoit le PipelineContext du run et peut donc le lire (context.get / context.resolve) et le modifier
#(context.set / context.merge).
#  - la méthode renvoie False ou lève une exception -> échec du bloc (branche on_error) ;
#  - toute autre valeur de retour (y compris None)    -> succès du bloc (branche on_success).
#Le service est une instance partagée : l'authentification utilisateur passe par le wallet du process
#(Service.getAuth()), jamais par un état porté par le service.
#
#Paramètres de configuration (clé "config" du bloc) :
#  - service (str,  obligatoire) : nom du service (clé dans "services" de la config). Non interpolé.
#  - method  (str,  obligatoire) : nom de la méthode publique à appeler (pas de "_" initial). Non interpolé.
#  - params  (dict, défaut {})   : paramètres transmis à la méthode (2e argument), interpolés avec le contexte.
class ServiceMethod(Block):
    def __init__(self, block_uid:str, config:dict, on_success_block:str=None, on_error_block:str=None):
        super().__init__("ServiceMethod", block_uid, config, on_success_block=on_success_block, on_error_block=on_error_block)

    def execute(self, context:PipelineContext):
        #Service et méthode volontairement non interpolés : une donnée du contexte (ex : payload du
        #trigger) ne doit pas pouvoir choisir le code exécuté
        service_name = self._config.get("service")
        method_name = self._config.get("method")
        params = context.getConfig(key="params", default={})

        if not isinstance(service_name, str) or service_name == "":
            Logger.write(f"[Block ServiceMethod] Missing 'service' parameter", type=ERROR)
            return False
        if not isinstance(method_name, str) or method_name == "":
            Logger.write(f"[Block ServiceMethod] Missing 'method' parameter", type=ERROR)
            return False
        if method_name.startswith("_"):
            Logger.write(f"[Block ServiceMethod] Method '{method_name}' is private and cannot be called", type=ERROR)
            return False

        try:
            service = ServiceManager.get(service_name)
        except Exception as e:
            Logger.write(f"[Block ServiceMethod] Service '{service_name}' not found", type=ERROR)
            return False

        method = getattr(service, method_name, None)
        if not callable(method):
            Logger.write(f"[Block ServiceMethod] Method '{method_name}' not found in service '{service_name}'", type=ERROR)
            return False

        try:
            result = method(context, params)
        except Exception as e:
            Logger.write(f"[Block ServiceMethod] {service_name}.{method_name} raised {type(e).__name__} : {e}", type=ERROR)
            return False

        if result is False:
            Logger.write(f"[Block ServiceMethod] {service_name}.{method_name} returned False", type=ERROR)
            return False

        Logger.write(f"[Block ServiceMethod] {service_name}.{method_name} executed", type=OK)
        return True
