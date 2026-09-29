import time
import contextvars
from lib.process.process import Process, KIND_INTERNAL
from lib.utils.uuid import Uuid

#ID du process courant, isolé par contexte d'exécution (tâche asyncio pour un tour d'agent, thread
#dédié pour un run de pipeline — cf. lib/pipelines/pipelinerunner.py) : posé par l'appelant le plus externe
#et lu n'importe où plus bas dans l'appel via getCurrent() (ex: FileStore, pour rattacher les fichiers produits). Se propage aussi à un reflect() de pipeline lancé via
#run_coroutine_threadsafe (qui recopie le contexte du thread appelant, cf. lib/pipelines/blocks/agent.py) —
#mais PAS à l'intérieur d'un outil MCP (la session MCP dispatche sur une autre tâche) : le process_id y est
#injecté explicitement via lumi_session_id (cf. lib/mcp/client.py et lib/mcp/toolloader.py).
_current_process_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar('current_process_id', default=None)

"""
ProcessManager — Registre des process (sessions, runs de pipeline et leurs exécutions enfants)
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class ProcessManager:
    #Registre à plat : racines ET enfants, pour qu'un outil MCP retrouve le process à partir de lumi_session_id
    _processes: dict[str, Process] = {}

    #Crée et enregistre un process, sans le poser comme process courant.
    #expires_in (secondes) et kind (cf. KIND_* dans lib/process/process.py) n'ont de sens que pour une racine.
    @staticmethod
    def create(process_id: str | None = None, parent: Process | None = None, expires_in: int | None = None, fingerprint: str = "", kind: str = KIND_INTERNAL) -> Process:
        process_id = process_id or Uuid.getUuid()
        #Un process du même id (ex: session Webex expirée) est fermé avant d'être remplacé
        if process_id in ProcessManager._processes:
            ProcessManager.remove(process_id)
        expires_at = time.time() + expires_in if expires_in is not None else None
        process = Process(process_id=process_id, parent=parent, expires_at=expires_at, fingerprint=fingerprint, kind=kind)
        ProcessManager._processes[process_id] = process
        return process

    #Crée un process et le pose comme process courant du contexte d'exécution en cours.
    #Renvoie (process, token) ; token à repasser à exit() pour restaurer le contexte précédent.
    @staticmethod
    def start(process_id: str | None = None, parent: Process | None = None, kind: str = KIND_INTERNAL) -> tuple[Process, contextvars.Token]:
        process = ProcessManager.create(process_id=process_id, parent=parent, kind=kind)
        return process, _current_process_id_var.set(process.getUid())

    #Pose un process existant comme process courant. Renvoie le token à repasser à exit().
    @staticmethod
    def setCurrent(process_id: str | None) -> contextvars.Token:
        return _current_process_id_var.set(process_id)

    #Restaure le contexte précédent. N'efface pas le process du registre, cf. remove().
    #Tolère un token issu d'un autre contexte (ex: générateur async finalisé hors de sa tâche).
    @staticmethod
    def exit(token: contextvars.Token | None) -> None:
        if token is None:
            return
        try:
            _current_process_id_var.reset(token)
        except ValueError:
            pass

    #Ferme le process et ses enfants, et les retire du registre.
    @staticmethod
    def remove(process_id: str) -> bool:
        process = ProcessManager._processes.pop(process_id, None)
        if process is None:
            return False
        for child in process.getChildren():
            ProcessManager.remove(child.getUid())
        process.close()
        return True

    #Supprime les racines expirées (ou toutes si all=True), avec leurs enfants
    @staticmethod
    def clear(all: bool = False) -> None:
        for process in list(ProcessManager._processes.values()):
            if process.getParent() is None and (all or process.isExpired()):
                ProcessManager.remove(process.getUid())

    #Récupère l'ID du process courant du contexte d'exécution en cours
    @staticmethod
    def getCurrentId() -> str | None:
        return _current_process_id_var.get()

    #Récupère le process courant du contexte d'exécution en cours
    @staticmethod
    def getCurrent() -> Process | None:
        return ProcessManager.get(ProcessManager.getCurrentId())

    #Récupère l'ID de la racine du process courant (session ou run de pipeline)
    @staticmethod
    def getCurrentRootId() -> str | None:
        process = ProcessManager.getCurrent()
        return process.getRoot().getUid() if process else None

    #Récupération d'un process par son ID (None si inconnu ou expiré)
    @staticmethod
    def get(process_id: str | None) -> Process | None:
        process = ProcessManager._processes.get(process_id) if process_id else None
        if process is None or process.isExpired():
            return None
        return process

    #Récupération d'une racine à partir de son token de signature d'URL
    @staticmethod
    def getByToken(token: str) -> Process | None:
        for process in list(ProcessManager._processes.values()):
            if process.getParent() is None and process.getToken() == token and not process.isExpired():
                return process
        return None

    #Racines actives ouvertes pour une source d'authentification donnée
    @staticmethod
    def getRootsByFingerprint(fingerprint: str, kind: str) -> list[Process]:
        return [
            process for process in list(ProcessManager._processes.values())
            if process.getParent() is None and process.getKind() == kind and process.getFingerprint() == fingerprint and not process.isExpired()
        ]

    @staticmethod
    def count() -> int:
        return len(ProcessManager._processes)
