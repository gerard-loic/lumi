import os
from typing import Annotated, Optional
from pydantic import Field
from lib.mcp.tools import MCPTool
from lib.agent.events import RagEvent
from lib.rag.retriever import Retriever
from lib.http.auth import Auth
from lib.session.session import AuthSessionManager
from lib.files.ragstore import RagStore

class RAGTool(MCPTool):
    name = "rag"
    description = "Recherche dans la base de connaissances"

    async def search_knowledge_base(
        self,
        query: Annotated[str, Field(description="Question ou sujet à rechercher dans la base de connaissances")],
        collection: Annotated[Optional[str], Field(default=None, description="Nom de la collection (optionnel, utilise la collection par défaut si absent)")] = None,
    ) -> list[dict]:
        """
        Recherche les passages les plus pertinents dans la base de connaissances.
        À utiliser dès que l'utilisateur pose une question sur un sujet documenté ou demande des informations générales non couvertes par les autres outils.
        Retourne les extraits de texte les plus pertinents avec leur score de similarité.
        Ne pas utiliser si la question porte sur un fichier que l'utilisateur a joint à la conversation (voir search_attached_files).
        """
        #À défaut de collection explicitement demandée par le LLM, utilise celle du profil de la session en cours
        if collection is None:
            profile = AuthSessionManager.get_profile(Auth.getSessionId())
            if profile:
                collection = profile.getConfigValue("rag.collection")

        retriever = Retriever(collection=collection)
        results = await retriever.search(query)

        #Signale au client les documents utilisés pour construire la réponse (un événement par source distincte).
        #`results` est déjà trié par similarité décroissante (ORDER BY embedding <=> ... dans PgVector.search) :
        #on préserve cet ordre plutôt que de trier les pages par numéro.
        pages_by_source: dict[str, list[int]] = {}
        url_by_source: dict[str, str] = {}
        label_by_source: dict[str, str] = {}
        for r in results:
            metadata = r.get("metadata", {})
            source = metadata.get("source")
            if not source:
                continue
            pages = pages_by_source.setdefault(source, [])
            page = metadata.get("page")
            if page is not None and page not in pages:
                pages.append(page)
            if metadata.get("file_url"):
                url_by_source.setdefault(source, metadata["file_url"])
            #`filename` absent pour les documents indexés avant son introduction : repli sur le basename de `source`
            label_by_source.setdefault(source, metadata.get("filename") or os.path.basename(source))
        for source, pages in pages_by_source.items():
            url = url_by_source.get(source)
            self.emit(RagEvent.get(source=label_by_source[source], locations=pages, url=RagStore.signUrl(url) if url else None))

        return results
