import re
import secrets
import contextvars
from pathlib import Path
from urllib.parse import unquote
from lib.config.config import Config
import os
from lib.session.session import AuthSessionManager

_KEY_URL_RE = re.compile(r"/files/([0-9a-f]{32})/([^?]+)")

#Scope courant d'attribution des fichiers temporaires. Format : "session:<id>" ou "pipeline:<process_id>".
#Il est posé par l'appelant le plus externe (handler HTTP conversationnel, ou PipelineRunner) et se
#propage via contextvars — y compris jusqu'aux outils MCP appelés pendant un bloc Agent, cf.
#lib/mcp/client.py (injection de lumi_file_scope) et lib/mcp/toolloader.py (enter_scope/exit_scope).
#Ce scope prime sur la session d'auth courante : pendant un pipeline, la sous-session éphémère de
#l'agent ne "capture" donc pas les fichiers, qui restent rattachés au run.
_scope_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("filestore_scope", default=None)

"""
FileStore — Gestion des fichiers temporaires
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class FileStore:
    #Fichiers rattachés à un run de pipeline :
    #  process_id -> {"token": <str>, "files": [{"key": <str>, "filename": <str>}, ...]}
    #Le token signe les URLs /files pour la durée du run (analogue à AuthSession.token_hash).
    _pipelines: dict[str, dict] = {}
    #Index inverse token -> process_id, pour l'autorisation côté route GET /files.
    _token_index: dict[str, str] = {}

    # ----------------------------------------------------------------- scope courant
    #Pose le scope pour le contexte d'exécution en cours ; renvoie un token à passer à exit_scope
    #(None si scope vide -> aucune modification).
    @staticmethod
    def enter_scope(scope: str | None) -> "contextvars.Token | None":
        if not scope:
            return None
        return _scope_var.set(scope)

    @staticmethod
    def exit_scope(token: "contextvars.Token | None") -> None:
        if token is not None:
            _scope_var.reset(token)

    @staticmethod
    def current_scope() -> str | None:
        return _scope_var.get()

    # --------------------------------------------------------------- scope pipeline
    #Ouvre un scope de fichiers pour un run de pipeline et renvoie le token de signature d'URL.
    @staticmethod
    def register_pipeline(process_id: str) -> str:
        token = secrets.token_hex(32)
        FileStore._pipelines[process_id] = {"token": token, "files": []}
        FileStore._token_index[token] = process_id
        return token

    #Supprime tous les fichiers d'un run de pipeline et invalide son token. Idempotent.
    @staticmethod
    def release_pipeline(process_id: str) -> int:
        entry = FileStore._pipelines.pop(process_id, None)
        if not entry:
            return 0
        FileStore._token_index.pop(entry["token"], None)
        return sum(1 for f in entry["files"] if FileStore.delete(f["key"]))

    @staticmethod
    def pipeline_from_token(token: str) -> str | None:
        return FileStore._token_index.get(token)

    @staticmethod
    def pipeline_has_file(process_id: str, key: str) -> bool:
        entry = FileStore._pipelines.get(process_id)
        return bool(entry) and any(f["key"] == key for f in entry["files"])

    #Entrées [{"key","filename"}] rattachées à un scope pipeline (liste vide pour un scope session
    #ou un scope inconnu). Sert au bloc Agent pour publier les fichiers produits par les outils MCP.
    @staticmethod
    def scope_entries(scope: str | None) -> list[dict]:
        if not scope or not scope.startswith("pipeline:"):
            return []
        entry = FileStore._pipelines.get(scope.split(":", 1)[1])
        return [dict(f) for f in entry["files"]] if entry else []

    @staticmethod
    def scope_keys(scope: str | None) -> set[str]:
        return {f["key"] for f in FileStore.scope_entries(scope)}

    @staticmethod
    def path(key: str) -> str:
        return str(Path(Config.get("directories.temp_dir")) / key)

    # ------------------------------------------------------------------------ save
    #Écrit un fichier temporaire et renvoie son URL de téléchargement.
    #Attribution (signature de l'URL + responsabilité du nettoyage) :
    #  - scope explicite, sinon scope courant (_scope_var), sinon session d'auth courante.
    #  - "pipeline:<id>" -> lié au run : URL signée par le token du run, purge en fin de run.
    #  - "session:<id>"  -> lié à la session : URL signée par token_hash, purge en fin de session.
    #  - aucun scope     -> fichier orphelin : écrit, URL non signée, non purgé automatiquement.
    @staticmethod
    def save(filename: str, content: bytes | str, scope: str | None = None) -> str:
        tmpdir = Path(Config.get("directories.temp_dir"))

        tmpdir.mkdir(exist_ok=True)
        key = secrets.token_hex(16)
        dest = tmpdir / key
        if isinstance(content, str):
            dest.write_text(content, encoding="utf-8")
        else:
            dest.write_bytes(content)
        base_url = Config.get(key="app.url")

        #Résolution du scope : argument explicite > scope courant > session d'auth courante.
        scope = scope or _scope_var.get()
        session = AuthSessionManager.get_current() if scope is None else None
        if session is not None:
            scope = f"session:{session.session_id}"

        url = f"{base_url}/files/{key}/{filename}"

        if scope and scope.startswith("session:"):
            session = session or AuthSessionManager.get_by_session_id(scope.split(":", 1)[1])
            if session:
                session.addFile(key)
                if session.token_hash:
                    url += f"?t={session.token_hash}"
        elif scope and scope.startswith("pipeline:"):
            entry = FileStore._pipelines.get(scope.split(":", 1)[1])
            if entry is not None:
                entry["files"].append({"key": key, "filename": filename})
                url += f"?t={entry['token']}"

        return url

    #Enregistrement d'un fichier entrant (upload utilisateur), sans URL de téléchargement publique
    @staticmethod
    def saveUpload(filename: str, content: bytes) -> str:
        tmpdir = Path(Config.get("directories.temp_dir"))
        tmpdir.mkdir(exist_ok=True)
        key = secrets.token_hex(16)
        (tmpdir / key).write_bytes(content)

        session = AuthSessionManager.get_current()
        if session:
            session.addFile(key)

        return key

    @staticmethod
    def key_from_url(url: str) -> str:
        match = _KEY_URL_RE.search(url)
        if not match:
            raise ValueError("URL de fichier invalide.")
        return match.group(1)

    @staticmethod
    def filename_from_url(url: str) -> str | None:
        match = _KEY_URL_RE.search(url)
        return unquote(match.group(2)) if match else None

    @staticmethod
    def load(source: str, scope: str | None = None) -> bytes:
        key = FileStore.key_from_url(source) if "/files/" in source else source
        tmpdir = Path(Config.get("directories.temp_dir")).resolve()

        #Fichier rattaché à un run de pipeline : accessible tant que le run n'est pas terminé.
        scope = scope or _scope_var.get()
        if scope and scope.startswith("pipeline:") and key in FileStore.scope_keys(scope):
            file_path = (tmpdir / key).resolve()
            if file_path.is_relative_to(tmpdir) and file_path.exists():
                return file_path.read_bytes()

        session = AuthSessionManager.get_current()
        if not session or key not in session.files:
            raise ValueError("Fichier introuvable ou inaccessible pour cette session.")

        file_path = (tmpdir / key).resolve()
        if not file_path.is_relative_to(tmpdir) or not file_path.exists():
            raise ValueError("Fichier introuvable.")
        return file_path.read_bytes()

    @staticmethod
    def delete(key:str) -> bool:
        file_path = f"{Config.get("directories.temp_dir")}/{key}"
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False

    @staticmethod
    def deleteAll() -> int:
        tmpdir = Path(Config.get("directories.temp_dir"))
        count = 0
        for f in tmpdir.iterdir():
            if f.is_file() and f.name != ".gitkeep":
                f.unlink()
                count += 1
        return count
