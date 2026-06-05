import secrets
from pathlib import Path
from lib.config.config import Config

"""
FileStore — Gestion des fichiers temporaires
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class FileStore:
    @staticmethod
    def save(filename: str, content: bytes | str) -> str:
        tmpdir = Path(Config.get("TEMP_DIR"))

        tmpdir.mkdir(exist_ok=True)
        key = secrets.token_hex(16)
        dest = tmpdir / key
        if isinstance(content, str):
            dest.write_text(content, encoding="utf-8")
        else:
            dest.write_bytes(content)
        base_url = Config.get(key="SERVICE_URL")
        return f"{base_url}/files/{key}/{filename}"
