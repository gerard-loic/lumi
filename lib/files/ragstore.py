from pathlib import Path
from lib.config.config import Config
import secrets
import os
import re
import shutil
from lib.http.auth import Auth
from lib.session.session import AuthSessionManager

_KEY_URL_RE = re.compile(r"/files/rag/([^/]+)/([0-9a-f]{32})/([^?]+)")

"""
RagStore : gestionnaire de fichiers rémanants (utilisé pour les sources de fichiers vectorisés dans le RAG)
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class RagStore:
    @staticmethod
    def save(filename: str, content: bytes | str, collection: str)->str:
        tmpdir = Path(Config.get("rag.storage_dir"))
        RagStore._createCollectionFolder(collection=collection)

        key = secrets.token_hex(16)
        dest = tmpdir / collection / key
        if isinstance(content, str):
            dest.write_text(content, encoding="utf-8")
        else:
            dest.write_bytes(content)

        #URL relative, sans base ni jeton : le fichier est persistant et peut être consulté par des
        #sessions différentes de celle qui l'a indexé (voire aucune, ex. indexation via cron). La base
        #(app.url) peut changer entre l'indexation et la consultation (domaine, environnement...) ; elle
        #n'est ajoutée, avec le jeton de la session en cours, qu'au moment de la consultation, via signUrl().
        return f"/files/rag/{collection}/{key}/{filename}"

    #Ajoute la base (app.url) et signe une URL RagStore avec le jeton de la session courante
    #(contextuel : appelé lors de la consultation/citation du fichier, jamais au moment de l'indexation)
    @staticmethod
    def signUrl(url: str) -> str:
        #Compatibilité avec les URLs absolues indexées avant l'introduction des URLs relatives
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"{Config.get(key='app.url')}{url}"
        session = AuthSessionManager.get(Auth.getSessionId())
        if not session or not session.token_hash:
            return url
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}t={session.token_hash}"

    @staticmethod
    def delete(key:str, collection:str ) -> bool:
        file_path = f"{Config.get("rag.storage_dir")}/{collection}/{key}"
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False
    
    #Supprime le fichier référencé par une URL générée par save() (ex: ancienne version lors d'une réindexation)
    @staticmethod
    def deleteByUrl(url: str) -> bool:
        match = _KEY_URL_RE.search(url)
        if not match:
            return False
        collection, key, _ = match.groups()
        return RagStore.delete(key=key, collection=collection)

    @staticmethod
    def deleteAll(collection:str) -> int:
        collection_dir = Path(Config.get("rag.storage_dir")) / collection
        if not collection_dir.exists():
            return 0
        count = sum(1 for f in collection_dir.iterdir() if f.is_file())
        shutil.rmtree(collection_dir)
        return count

    @staticmethod
    def _createCollectionFolder(collection: str):
        tmpdir = Path(Config.get("rag.storage_dir"))
        collection_dir = tmpdir / collection
        if not collection_dir.exists():
            collection_dir.mkdir(parents=True)
