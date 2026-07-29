import os
import re
from datetime import datetime

from lib.cron.tasks.crontask import CronTask
from lib.rag.vectorstore import VectorStore
from lib.rag.indexer import Indexer
from lib.agent.profile import ProfileManager

"""
Ragindexer : gestion d'indexation de fichiers pour le RAG
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
config :
"config":{
    "folders" : [
        "/folder"
    ],
    "profile" : "default"
}
"""
class Ragindexer(CronTask):
    def __init__(self, config:dict):
        super().__init__(
            className="Ragindexer",
            config=config
        )
        #Profil dont la collection RAG (profiles.<profile>.rag.collection) est utilisée pour l'indexation
        self._collection = ProfileManager.getProfile(self.config.get("profile", "default")).getConfigValue("rag.collection")

    async def run(self):
        await super().run()
        print(f"[RagIndexer] {self.config}")

        files = self._listFiles()
        for file in files:
            exists = await self._exists(file=file)
            if not exists:
                await self._indexFile(source=file)


    def _listFiles(self):
        folders = self.config["folders"]
        files = []
        for folder in folders:
            folder = os.path.expanduser(folder)
            for root, _, filenames in os.walk(folder):
                for filename in filenames:
                    files.append(os.path.join(root, filename))
        return files

    #Vérifie si le fichier est déjà indexé et à jour (le fichier sur disque n'a pas été modifié depuis)
    async def _exists(self, file:str) -> bool:
        metadata = await VectorStore.sourceMetadata(collection=self._collection, source=file)
        if metadata is None:
            return False
        stored_mtime = metadata.get("mtime")
        if stored_mtime is None:
            return False
        return stored_mtime >= os.path.getmtime(file)

    #Indexe (ou réindexe) un fichier : supprime les chunks existants pour cette source puis réindexe depuis le disque
    async def _indexFile(self, source:str):
        indexer = Indexer(collection=self._collection)
        result = await indexer.reindexFile(path=source, source=source)
        self.log(text=f"File indexed in RAG :  '{source}' ({result['chunks_indexed']} chunks, {result['deleted_chunks']} deleted)")

