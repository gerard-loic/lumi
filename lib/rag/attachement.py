from fastapi import UploadFile, File
from lib.session.session import AuthSession, AuthSessionManager
from pathlib import Path
import tempfile
from lib.rag.textextractor import TextExtractor
from lib.log.logger import Logger, ERROR
import os
from lib.files.filestore import FileStore

"""
Attachment — Ajoute un fichier à une conversation, qui sera stocké dans la base vectorielle temporaire
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>

add() : point d'entrée pour un upload HTTP (UploadFile).
addContent() : point d'entrée générique (nom + bytes) pour toute autre provenance (tool, fichier disque, etc.)
"""
class Attachement:
    #Point d'entrée HTTP : lit le contenu d'un UploadFile puis délègue à add()
    @staticmethod
    async def add(session: AuthSession, file: UploadFile = File(...)):
        content = await file.read()
        return await Attachement.addContent(session, file.filename, content)

    #Point d'entrée générique : ajoute une pièce jointe à partir d'un nom de fichier et de son contenu brut,
    #quelle que soit sa provenance (upload HTTP, fichier généré par un tool, fichier lu sur disque, etc.)
    @staticmethod
    async def addContent(session: AuthSession, filename: str, content: bytes) -> dict:
        #Récupère la configuration des pièces jointes issue du profil de la session
        profile = AuthSessionManager.get_profile(session.session_id)

        #Vérifie que l'option est activée
        if not profile.getConfigValue("attachments.enabled", default=False):
            raise Exception("File attachements are disabled")

        #Vérifie que la limite n'est pas atteinte
        max_files = profile.getConfigValue("attachments.max_files", default=5)
        if len(session.attachments) >= max_files:
            raise Exception(f"Maximum number of attached files reached ({max_files})")

        #Vérifie l'extension du fichier
        ext = Path(filename).suffix.lower() if filename else ""
        allowed_extensions = profile.getConfigValue("attachments.allowed_extensions", default=[".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".md", ".html", ".htm", ".py", ".js", ".ts", ".txt", ".csv"])
        if ext not in allowed_extensions:
            raise Exception(f"File extension '{ext}' not allowed")

        if not content:
            raise Exception("Empty file")

        #vérifie la taille du fichier
        max_size = profile.getConfigValue("attachments.max_file_size_mb", default=20) * 1024 * 1024
        if len(content) > max_size:
            raise Exception("File too large")

        #Extraction des données
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            pages = await TextExtractor.extractPages(tmp_path, ext)
            text = "\n\n".join(t for _, t in pages) if pages is not None else await TextExtractor.extract(tmp_path, ext)
        except Exception as e:
            Logger.write(f"[HTTP] [500] add_attachment — extraction error: {e}", type=ERROR)
            raise Exception("Unable to extract file content")
        finally:
            os.unlink(tmp_path)

        key = FileStore.saveUpload(filename, content)
        tokens = max(1, len(text) // 4)
        session.addAttachment(key, filename, text, tokens, pages=pages)

        return {"key": key, "filename": filename, "tokens": tokens}