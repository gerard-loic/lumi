import json
import time
import asyncio
import hashlib
import functools
from concurrent.futures import ThreadPoolExecutor
from lib.services.servicemanager import ServiceManager
from lib.config.config import Config
import secrets
from lib.log.logger import Logger, ERROR, WARNING
from lib.localization.language import Language
from lib.process.processmanager import ProcessManager
from lib.process.process import Process, KIND_HTTP
from lib.process.agentcontext import AgentContext
from lib.utils.jwt import Jwt

#Pool dédié aux appels d'authentification auprès des services (synchrones, bloquants) : ils ne bloquent pas la
#boucle événementielle, et un afflux de requêtes /auth ne peut occuper que ces threads, sans saturer le pool
#par défaut d'asyncio (utilisé ailleurs, ex. requêtes pgvector)
_AUTH_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="lumi-auth")

"""
Auth — Gestion de l'authentification sur l'agent via Websockets
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Auth:
    #Vérifie la configuration de l'authentification au démarrage : un secret vide ou court permettrait de forger des tokens
    @staticmethod
    def init():
        #Taille minimale du secret de signature des tokens (HS256 : 256 bits)
        min_length = Config.get(key="security.min_secret_length", default=32)
        secret = Config.get(key="authentication.jwt_secret", default="")
        if not isinstance(secret, str) or len(secret) < min_length:
            raise Exception(f"[AUTH] authentication.jwt_secret must be at least {min_length} characters long")

    #S'authentifier : `authorization` est de la forme {"<service>": {...}, ...}. L'authentification auprès du
    #service principal (authentication.service) est obligatoire ; celle des autres services présents est
    #facultative. Seuls des tokens existants sont acceptés, jamais d'identifiants (cf. Service.authenticate,
    #allow_credentials). Une session (process racine) est ouverte, son wallet porte les secrets obtenus.
    #Le token renvoyé ne contient que l'identifiant de session : les secrets restent côté serveur.
    #Renvoie None si une session WebSocket est déjà ouverte pour cette source d'authentification, False en cas d'échec.
    #Les appels aux services (réseau, synchrones) sont faits en premier, hors de la boucle événementielle ; la
    #session n'est ensuite créée qu'en fin de méthode, sans point d'attente, pour que deux authentifications
    #concurrentes ne s'entremêlent pas dans ProcessManager.
    @staticmethod
    async def authenticate(authorization: dict, profile: str, language: Language):
        #Authentification auprès du service principal
        auth_name = Config.get(key="authentication.service")
        auth_secret = await Auth._serviceAuthenticate(name=auth_name, authorization=authorization.get(auth_name) or {})
        if not isinstance(auth_secret, dict):
            return False

        #Authentification aux autres services fournis dans la requête (en parallèle)
        others = [
            name for name, service_authorization in authorization.items()
            if name != auth_name and name in ServiceManager.services and isinstance(service_authorization, dict)
        ]
        other_secrets = await asyncio.gather(*(Auth._serviceAuthenticate(name=name, authorization=authorization[name]) for name in others))

        fingerprint = hashlib.sha256(
            json.dumps(authorization, sort_keys=True).encode()
        ).hexdigest()

        #Une seule session par source d'authentification : la précédente est remplacée (ce qui borne la mémoire
        #consommée par utilisateur), sauf si elle est en cours d'utilisation par un client WebSocket.
        previous = ProcessManager.getRootsByFingerprint(fingerprint, kind=KIND_HTTP)
        if any(process.isConnected() for process in previous):
            Logger.write("[AUTH] Authentification refusée : une session WebSocket est déjà ouverte pour cet utilisateur", type=WARNING)
            return None
        for process in previous:
            ProcessManager.remove(process.getUid())

        #Ouverture de la session
        process = ProcessManager.create(expires_in=Config.get("authentication.session_duration"), fingerprint=fingerprint, kind=KIND_HTTP)
        process.setAgentContext(AgentContext(profile=profile, language=language))

        #Secrets obtenus auprès des services
        wallet = process.getWallet()
        wallet.store(key=auth_name, secret=auth_secret)
        for name, secret in zip(others, other_secrets):
            if isinstance(secret, dict):
                wallet.store(key=name, secret=secret)
            else:
                Logger.write(f"[AUTH] Authentification au service {name} échouée, ignoré pour cette session", type=WARNING)

        return Jwt.createToken(
            payload={"session_id": process.getUid()},
            secret=Config.get(key="authentication.jwt_secret"),
            algorithm=Config.get(key="authentication.jwt_algorithm"),
            expires_in=Config.get("authentication.session_duration"),
        )

    #Appelle Service.authenticate (synchrone, bloquant : requête réseau vers le service) dans le pool dédié
    @staticmethod
    async def _serviceAuthenticate(name: str, authorization: dict):
        service = ServiceManager.get(name=name)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_AUTH_EXECUTOR, functools.partial(service.authenticate, authorization=authorization))

    #Vérifie un token d'authentification et renvoie la session associée (None si invalide ou expirée).
    #Pose la session comme process courant du contexte d'exécution (ex: préfixe des logs de la requête).
    #Seules les sessions racines ouvertes par authenticate() sont acceptées (cf. KIND_HTTP).
    @staticmethod
    def checkAuthentification(token:str) -> Process | None:
        try:
            decoded = Jwt.verifyToken(
                token=token,
                secret=Config.get(key="authentication.jwt_secret"),
                algorithm=Config.get(key="authentication.jwt_algorithm"),
            )
            process = ProcessManager.get(decoded.get("session_id"))
            if process is None or process.getParent() is not None or process.getKind() != KIND_HTTP:
                return None
            ProcessManager.setCurrent(process.getUid())
            return process
        except Exception:
            return None


"""
AuthRateLimiter — Limitation du nombre de requêtes d'authentification par IP cliente (fenêtre glissante)
Limite : authentication.max_auth_requests_minute (défaut 10, -1 : désactivé) par fenêtre de security.auth_rate_window secondes (défaut 60).
Derrière un reverse proxy, l'IP cliente n'est la bonne que si uvicorn est lancé avec --proxy-headers
(et --forwarded-allow-ips) : sinon toutes les requêtes semblent venir du proxy et partagent la même limite.
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class AuthRateLimiter:
    _requests: dict[str, list[float]] = {}

    #Enregistre une tentative pour `ip`. Renvoie False si la limite est atteinte (tentative non comptée).
    @staticmethod
    def allow(ip: str) -> bool:
        limit = Config.get("authentication.max_auth_requests_minute", 10)
        if limit is None or limit == -1:
            return True

        window = Config.get("security.auth_rate_window", 60)
        max_tracked_ips = Config.get("security.auth_rate_max_tracked_ips", 10_000)   # Au-delà, purge des IP inactives (borne la mémoire)

        now = time.time()
        if len(AuthRateLimiter._requests) > max_tracked_ips:
            AuthRateLimiter._requests = {
                k: v for k, v in AuthRateLimiter._requests.items() if v and now - v[-1] < window
            }

        timestamps = [t for t in AuthRateLimiter._requests.get(ip, []) if now - t < window]
        if len(timestamps) >= limit:
            AuthRateLimiter._requests[ip] = timestamps
            return False
        timestamps.append(now)
        AuthRateLimiter._requests[ip] = timestamps
        return True


"""
Auth — Gestion de l'authentification sur les routes d'administration
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class AdminAuth:
    @staticmethod
    def checkAdminCredentials(username: str, password: str) -> bool:
        users = Config.get("app.admin_users")
        for user in users:
            u_ok = secrets.compare_digest(username.encode(), user["username"].encode())
            p_ok = secrets.compare_digest(password.encode(), user["password"].encode())
            if u_ok and p_ok:
                return True
        Logger.write(f"[HTTP] [401] rag — Unauthorized access attempt for user '{username}'", type=ERROR)
        return False


