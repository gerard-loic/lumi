from pathlib import Path
from lib.config.config import Config
import secrets
import os
import re
import shutil
import time
import hmac
import hashlib
from lib.process.processmanager import ProcessManager

_KEY_URL_RE = re.compile(r"/files/rag/([^/]+)/([0-9a-f]{32})/([^?]+)")

"""
RagStore : gestionnaire de fichiers rémanants (utilisé pour les sources de fichiers vectorisés dans le RAG)
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class RagStore:
    @staticmethod
    def save(filename: str, content: bytes | str, collection: str)->str:
        tmpdir = Path(Config.get("directories.rag_storage_dir"))
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

    #Ajoute la base (app.url) et signe une URL RagStore (contextuel : appelé lors de la consultation/citation
    #du fichier, jamais au moment de l'indexation). La signature (?t=<expiration>.<hmac>) ne vaut que pour CE
    #fichier : une URL divulguée (logs, message Webex...) ne donne pas accès au reste du stockage RAG. Elle expire
    #avec la session courante, ou à défaut (run de pipeline sans expiration) après authentication.session_duration.
    @staticmethod
    def signUrl(url: str) -> str:
        #Compatibilité avec les URLs absolues indexées avant l'introduction des URLs relatives
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"{Config.get(key='app.url')}{url}"
        url = url.split("?", 1)[0]
        match = _KEY_URL_RE.search(url)
        if not match:
            return url
        collection, key, _ = match.groups()

        process = ProcessManager.getCurrent()
        expires_at = process.getExpiresAt() if process else None
        if expires_at is None:
            expires_at = time.time() + Config.get("authentication.session_duration")
        expires_at = int(expires_at)

        return f"{url}?t={expires_at}.{RagStore._signature(collection, key, expires_at)}"

    #Vérifie la signature ?t= d'une URL RagStore (cf. signUrl) : fichier signé et signature non expirée
    @staticmethod
    def checkSignature(collection: str, key: str, t: str) -> bool:
        try:
            expires_at, signature = t.split(".", 1)
            expires_at = int(expires_at)
        except ValueError:
            return False
        if expires_at <= time.time():
            return False
        return hmac.compare_digest(signature, RagStore._signature(collection, key, expires_at))

    #HMAC du fichier (collection + clé) et de son expiration. Le préfixe sépare cet usage du secret de celui des JWT.
    @staticmethod
    def _signature(collection: str, key: str, expires_at: int) -> str:
        message = f"lumi-ragstore-url:{collection}/{key}:{expires_at}".encode()
        return hmac.new(Config.get("authentication.jwt_secret").encode(), message, hashlib.sha256).hexdigest()

    @staticmethod
    def delete(key:str, collection:str ) -> bool:
        file_path = f"{Config.get("directories.rag_storage_dir")}/{collection}/{key}"
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
        collection_dir = Path(Config.get("directories.rag_storage_dir")) / collection
        if not collection_dir.exists():
            return 0
        count = sum(1 for f in collection_dir.iterdir() if f.is_file())
        shutil.rmtree(collection_dir)
        return count

    @staticmethod
    def _createCollectionFolder(collection: str):
        tmpdir = Path(Config.get("directories.rag_storage_dir"))
        collection_dir = tmpdir / collection
        if not collection_dir.exists():
            collection_dir.mkdir(parents=True)
