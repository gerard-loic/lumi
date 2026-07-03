import re
import secrets
from pathlib import Path
from urllib.parse import unquote
from lib.config.config import Config
import os
from lib.http.auth import Auth
from lib.session.session import AuthSessionManager

_KEY_URL_RE = re.compile(r"/files/([0-9a-f]{32})/([^?]+)")

"""
FileStore — Gestion des fichiers temporaires
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class FileStore:
    @staticmethod
    def save(filename: str, content: bytes | str)->str:
        tmpdir = Path(Config.get("files.temp_dir"))

        tmpdir.mkdir(exist_ok=True)
        key = secrets.token_hex(16)
        dest = tmpdir / key
        if isinstance(content, str):
            dest.write_text(content, encoding="utf-8")
        else:
            dest.write_bytes(content)
        base_url = Config.get(key="app.url")

        #Enregistrement dans la session
        session = AuthSessionManager.get(Auth.getSessionId())
        if session:
            session.addFile(key)

        url = f"{base_url}/files/{key}/{filename}"
        if session and session.token_hash:
            url += f"?t={session.token_hash}"
        return url

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
    def load(source: str) -> bytes:
        key = FileStore.key_from_url(source) if "/files/" in source else source

        session = AuthSessionManager.get(Auth.getSessionId())
        if not session or key not in session.files:
            raise ValueError("Fichier introuvable ou inaccessible pour cette session.")

        tmpdir = Path(Config.get("files.temp_dir")).resolve()
        file_path = (tmpdir / key).resolve()
        if not file_path.is_relative_to(tmpdir) or not file_path.exists():
            raise ValueError("Fichier introuvable.")
        return file_path.read_bytes()

    @staticmethod
    def delete(key:str) -> bool:
        file_path = f"{Config.get("files.temp_dir")}/{key}"
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False

    @staticmethod
    def deleteAll() -> int:
        tmpdir = Path(Config.get("files.temp_dir"))
        count = 0
        for f in tmpdir.iterdir():
            if f.is_file() and f.name != ".gitkeep":
                f.unlink()
                count += 1
        return count