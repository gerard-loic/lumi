from typing import Annotated, Optional
from pydantic import Field
from lib.mcp.tools import MCPTool
from lib.agent.events import RagEvent
from lib.rag.retriever import Retriever
from lib.http.auth import Auth
from lib.session.session import AuthSessionManager

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
        for r in results:
            source = r.get("metadata", {}).get("source")
            if not source:
                continue
            pages = pages_by_source.setdefault(source, [])
            page = r["metadata"].get("page")
            if page is not None and page not in pages:
                pages.append(page)
        for source, pages in pages_by_source.items():
            self.emit(RagEvent.get(source=source, locations=pages))

        return results
