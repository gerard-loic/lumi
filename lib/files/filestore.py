import re
import secrets
from pathlib import Path
from urllib.parse import unquote
from lib.config.config import Config
import os
from lib.process.processmanager import ProcessManager

_KEY_URL_RE = re.compile(r"/files/([0-9a-f]{32})/([^?]+)")

"""
FileStore — Gestion des fichiers temporaires
Chaque fichier est rattaché à la racine du process courant (session ou run de pipeline, cf. Process.addFile) :
les URLs sont signées par le token de cette racine, et les fichiers sont supprimés à sa fermeture.
Les outils MCP retrouvent le process courant via lumi_session_id (cf. lib/mcp/toolloader.py).
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class FileStore:
    @staticmethod
    def path(key: str) -> str:
        return str(Path(Config.get("directories.temp_dir")) / key)

    # ------------------------------------------------------------------------ save
    #Écrit un fichier temporaire et renvoie son URL de téléchargement.
    #Rattaché au process courant : URL signée par son token, purge à sa fermeture.
    #Sans process courant : fichier orphelin, URL non signée, non purgé automatiquement.
    @staticmethod
    def save(filename: str, content: bytes | str) -> str:
        tmpdir = Path(Config.get("directories.temp_dir"))

        tmpdir.mkdir(exist_ok=True)
        key = secrets.token_hex(16)
        dest = tmpdir / key
        if isinstance(content, str):
            dest.write_text(content, encoding="utf-8")
        else:
            dest.write_bytes(content)

        url = f"{Config.get(key='app.url')}/files/{key}/{filename}"

        process = ProcessManager.getCurrent()
        if process:
            process.addFile(key, filename)
            url += f"?t={process.getToken()}"

        return url

    #Enregistrement d'un fichier entrant (upload utilisateur), sans URL de téléchargement publique.
    #Rattaché à `process` s'il est fourni, sinon au process courant.
    @staticmethod
    def saveUpload(filename: str, content: bytes, process=None) -> str:
        tmpdir = Path(Config.get("directories.temp_dir"))
        tmpdir.mkdir(exist_ok=True)
        key = secrets.token_hex(16)
        (tmpdir / key).write_bytes(content)

        process = process or ProcessManager.getCurrent()
        if process:
            process.addFile(key, filename)

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

    #Lecture d'un fichier (clé ou URL) rattaché au process courant
    @staticmethod
    def load(source: str) -> bytes:
        key = FileStore.key_from_url(source) if "/files/" in source else source
        tmpdir = Path(Config.get("directories.temp_dir")).resolve()

        process = ProcessManager.getCurrent()
        if not process or not process.hasFile(key):
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
