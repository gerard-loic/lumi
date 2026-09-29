from fastapi import UploadFile, File
from lib.process.process import Process
from pathlib import Path
import tempfile
from lib.rag.textextractor import TextExtractor, ExtractionError
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
    async def add(session: Process, file: UploadFile = File(...)):
        #Lecture bornée à la taille maximale du profil (+1 octet pour détecter le dépassement) : un fichier trop
        #gros n'est pas chargé en mémoire (la taille de la requête est déjà plafonnée par BodySizeLimitMiddleware)
        agent_ctx = session.getAgentContext()
        max_size = Attachement._maxSize(agent_ctx.getProfileConfig()) if agent_ctx else 0
        content = await file.read(max_size + 1)
        if len(content) > max_size:
            raise Exception("File too large")
        return await Attachement.addContent(session, file.filename, content)

    #Taille maximale d'une pièce jointe pour un profil (octets)
    @staticmethod
    def _maxSize(profile) -> int:
        return int(profile.getConfigValue("attachments.max_file_size_mb", default=20) * 1024 * 1024)

    #Point d'entrée générique : ajoute une pièce jointe à partir d'un nom de fichier et de son contenu brut,
    #quelle que soit sa provenance (upload HTTP, fichier généré par un tool, fichier lu sur disque, etc.)
    @staticmethod
    async def addContent(session: Process, filename: str, content: bytes) -> dict:
        #Récupère la configuration des pièces jointes issue du profil de la session
        agent_ctx = session.getAgentContext()
        if agent_ctx is None:
            raise Exception("No conversation attached to this session")
        profile = agent_ctx.getProfileConfig()

        #Vérifie que l'option est activée
        if not profile.getConfigValue("attachments.enabled", default=False):
            raise Exception("File attachements are disabled")

        #Vérifie que la limite n'est pas atteinte
        max_files = profile.getConfigValue("attachments.max_files", default=5)
        if len(agent_ctx.getAttachments()) >= max_files:
            raise Exception(f"Maximum number of attached files reached ({max_files})")

        #Vérifie l'extension du fichier
        ext = Path(filename).suffix.lower() if filename else ""
        allowed_extensions = profile.getConfigValue("attachments.allowed_extensions", default=[".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".md", ".html", ".htm", ".py", ".js", ".ts", ".txt", ".csv"])
        if ext not in allowed_extensions:
            raise Exception(f"File extension '{ext}' not allowed")

        if not content:
            raise Exception("Empty file")

        #vérifie la taille du fichier
        if len(content) > Attachement._maxSize(profile):
            raise Exception("File too large")

        #Extraction des données
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            pages = await TextExtractor.extractPages(tmp_path, ext)
            text = "\n\n".join(t for _, t in pages) if pages is not None else await TextExtractor.extract(tmp_path, ext)
        except ExtractionError as e:
            #Fichier refusé par les contrôles (archive trop volumineuse, ressources dépassées...) : message explicite
            Logger.write(f"[HTTP] [400] add_attachment — extraction refused: {e}", type=ERROR)
            raise Exception(f"Unable to extract file content : {e}")
        except Exception as e:
            Logger.write(f"[HTTP] [500] add_attachment — extraction error: {e}", type=ERROR)
            raise Exception("Unable to extract file content")
        finally:
            os.unlink(tmp_path)

        key = FileStore.saveUpload(filename, content, process=session)
        tokens = max(1, len(text) // 4)
        agent_ctx.addAttachment(key, filename, text, tokens, pages=pages)

        return {"key": key, "filename": filename, "tokens": tokens}