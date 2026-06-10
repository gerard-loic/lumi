import secrets
from pathlib import Path
from lib.config.config import Config
import os
from lib.http.auth import Auth
from lib.session.session import AuthSessionManager

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

        return f"{base_url}/files/{key}/{filename}"

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