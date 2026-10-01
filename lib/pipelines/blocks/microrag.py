import os
import asyncio
import tempfile
from pathlib import Path
from lib.pipelines._abstract import Block
from lib.pipelines.pipelinecontext import PipelineContext
from lib.pipelines.utils.filesource import resolve_file_refs, FileSourceError
from lib.rag.textextractor import TextExtractor
from lib.mcp.client import mcp_manager
from lib.utils.uuid import Uuid
from lib.log.logger import Logger, ERROR, OK

#Bloc MicroRag : prépare un ou plusieurs fichiers pour le micro-RAG d'un bloc Agent (équivalent pipeline des
#pièces jointes d'une conversation websocket, cf. lib/rag/attachement.py).
#Le texte est extrait ici (page par page pour un PDF). Les chunks et embeddings ne sont calculés que si un bloc Agent
#en a besoin (mode "rag", ou "auto" sur un contenu trop long, cf. AttachmentRetriever.retrieve), une seule fois : ils
#sont ensuite réutilisés par les blocs Agent suivants. Rien n'est écrit en base vectorielle, tout reste dans le
#contexte du run.
#
#Paramètres de configuration (clé "config" du bloc) :
#  - source             (str|dict|list, obligatoire) : fichier(s) à intégrer. Voir lib/pipelines/utils/filesource.py ;
#                                                      une liste (ou "{var}" pointant vers une liste) intègre tous les fichiers.
#  - allowed_extensions (list, défaut : formats des pièces jointes) : extensions acceptées.
#  - max_file_size_mb   (int,  défaut 20)            : taille maximale d'un fichier.
#  - append             (bool, défaut False)         : ajoute les fichiers à ceux déjà présents sous "output"
#                                                      (enchaînement de plusieurs blocs MicroRag) au lieu de les remplacer.
#  - output             (str,  défaut "micro_rag")   : clé du contexte où stocker les fichiers préparés, à passer
#                                                      au bloc Agent via sa clé "micro_rag" (ex : "micro_rag": "{micro_rag}").
class MicroRag(Block):
    _DEFAULT_EXTENSIONS = [".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".md", ".html", ".htm", ".py", ".js", ".ts", ".txt", ".csv"]

    def __init__(self, block_uid:str, config:dict, on_success_block:str=None, on_error_block:str=None):
        super().__init__("MicroRag", block_uid, config, on_success_block=on_success_block, on_error_block=on_error_block)

    def execute(self, context:PipelineContext):
        allowed_extensions = [e.lower() for e in context.getConfig(key="allowed_extensions", default=self._DEFAULT_EXTENSIONS)]
        max_size = int(context.getConfig(key="max_file_size_mb", default=20)) * 1024 * 1024
        append   = bool(context.getConfig(key="append", default=False))
        output   = context.getConfig(key="output", default="micro_rag")

        try:
            refs = resolve_file_refs(self._config.get("source"), context)
        except FileSourceError as e:
            Logger.write(f"[Block MicroRag] {e}", type=ERROR)
            return False

        attachments = []
        for ref in refs:
            ext = Path(ref.filename).suffix.lower()
            if ext not in allowed_extensions:
                Logger.write(f"[Block MicroRag] {ref.filename} : extension '{ext}' not allowed", type=ERROR)
                return False
            try:
                content = ref.read()
            except FileSourceError as e:
                Logger.write(f"[Block MicroRag] {e}", type=ERROR)
                return False
            if not content:
                Logger.write(f"[Block MicroRag] {ref.filename} : empty file", type=ERROR)
                return False
            if len(content) > max_size:
                Logger.write(f"[Block MicroRag] {ref.filename} : file too large", type=ERROR)
                return False

            try:
                #Exécuté sur la boucle FastAPI, comme reflect() dans le bloc Agent (propagation des contextvars pour
                #Logger.capture())
                attachment = asyncio.run_coroutine_threadsafe(self._prepare(ref, ext, content), mcp_manager.loop).result()
            except Exception as e:
                Logger.write(f"[Block MicroRag] {ref.filename} : preparation failed : {e}", type=ERROR)
                return False

            attachments.append(attachment)
            pages = f"{len(attachment['pages'])} page(s), " if attachment["pages"] else ""
            Logger.write(f"[Block MicroRag] {ref.filename} : {pages}~{attachment['tokens']} token(s)", type=OK)

        if append:
            try:
                previous = context.resolve(output)
            except (KeyError, IndexError, ValueError):
                previous = []
            attachments = [*(previous or []), *attachments]

        context.set(output, attachments)
        return True

    #Pièce jointe au format AgentContext.addAttachment ; "chunks" est rempli au premier passage en micro-RAG
    async def _prepare(self, ref, ext:str, content:bytes)->dict:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            pages = await TextExtractor.extractPages(tmp_path, ext)
            text = "\n\n".join(t for _, t in pages) if pages is not None else await TextExtractor.extract(tmp_path, ext)
        finally:
            os.unlink(tmp_path)

        return {
            "key": ref.key or Uuid.get(),
            "filename": ref.filename,
            "text": text,
            "tokens": max(1, len(text) // 4),
            "pages": pages,
            "chunks": None,
            "embedding_model": None,
        }
