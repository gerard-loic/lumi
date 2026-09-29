import asyncio
import multiprocessing
import resource
import signal
import threading

"""
Sandbox — Exécution d'une fonction dans un sous-processus isolé, avec limites de mémoire, de CPU et de durée
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>

Utilisé pour les traitements de fichiers non fiables (extraction de texte des pièces jointes : PDF, Office...) :
un fichier piégé (bombe de décompression, PDF pathologique) ne peut épuiser que les ressources du sous-processus,
qui est tué au besoin, sans affecter le serveur. Un thread, lui, ne peut être ni limité ni interrompu.

Contexte "forkserver" : les sous-processus sont forkés depuis un serveur qui ne porte ni threads ni état du
serveur principal (pas de fork d'un processus multi-thread), avec les modules d'extraction préchargés
(cf. init) pour ne pas payer leur import à chaque appel. Linux uniquement.
"""

_CONTEXT = multiprocessing.get_context("forkserver")


class SandboxError(Exception):
    pass


class Sandbox:
    #Nombre maximal de sous-processus simultanés (les appels suivants attendent leur tour) : borne la mémoire totale
    _slots = threading.BoundedSemaphore(4)

    #À appeler au démarrage, avant la première exécution :
    #  - modules      : modules préchargés dans le serveur de fork
    #  - max_concurrent : nombre maximal de sous-processus simultanés
    @staticmethod
    def init(modules: list[str], max_concurrent: int = 4) -> None:
        _CONTEXT.set_forkserver_preload(modules)
        Sandbox._slots = threading.BoundedSemaphore(max_concurrent)

    #Exécute func(*args) dans un sous-processus et renvoie son résultat (doit être sérialisable, de même que func,
    #fonction de niveau module). Lève SandboxError si une limite est dépassée ou si func lève une exception.
    #  - timeout       : durée maximale (secondes, temps réel)
    #  - max_memory_mb : mémoire maximale du sous-processus (espace d'adressage)
    #  - max_cpu       : temps CPU maximal (secondes), par défaut égal au timeout
    @staticmethod
    async def run(func, *args, timeout: float, max_memory_mb: int, max_cpu: int | None = None):
        return await asyncio.to_thread(Sandbox._runBlocking, func, args, timeout, max_memory_mb, max_cpu or int(timeout))

    @staticmethod
    def _runBlocking(func, args: tuple, timeout: float, max_memory_mb: int, max_cpu: int):
        with Sandbox._slots:
            return Sandbox._runProcess(func, args, timeout, max_memory_mb, max_cpu)

    @staticmethod
    def _runProcess(func, args: tuple, timeout: float, max_memory_mb: int, max_cpu: int):
        receiver, sender = _CONTEXT.Pipe(duplex=False)
        process = _CONTEXT.Process(target=_worker, args=(sender, func, args, max_memory_mb, max_cpu), daemon=True)
        process.start()
        sender.close()
        try:
            #Lecture du résultat avant join() : un résultat volumineux remplirait le tube et bloquerait l'enfant
            if not receiver.poll(timeout):
                raise SandboxError(f"Traitement interrompu : durée maximale dépassée ({timeout}s)")
            try:
                status, payload = receiver.recv()
            except EOFError:
                #Sous-processus mort sans réponse : tué par une limite (CPU : SIGXCPU/SIGKILL) ou planté
                process.join(5)
                raise SandboxError(f"Traitement interrompu : ressources maximales dépassées (code {process.exitcode})")
        finally:
            receiver.close()
            if process.is_alive():
                process.kill()
            process.join(5)

        if status == "error":
            raise SandboxError(payload)
        return payload


#Point d'entrée du sous-processus : pose les limites puis exécute la fonction
def _worker(sender, func, args: tuple, max_memory_mb: int, max_cpu: int):
    try:
        memory = max_memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_CPU, (max_cpu, max_cpu + 1))
        signal.signal(signal.SIGXCPU, signal.SIG_DFL)
        #Pas de fichier core : un core dump de max_memory_mb par fichier piégé remplirait le disque
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        result = func(*args)
        sender.send(("ok", result))
    except MemoryError:
        sender.send(("error", "Traitement interrompu : mémoire maximale dépassée"))
    except BaseException as e:
        sender.send(("error", f"{type(e).__name__}: {e}"))
    finally:
        sender.close()
