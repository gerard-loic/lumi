from typing import Annotated, Optional
from pydantic import Field
from lib.mcp.tools import MCPTool
from lib.rag.retriever import Retriever
from lib.mcp.tools import native_tool

class RAGTool(MCPTool):
    name = "rag"
    description = "Recherche dans la base de connaissances"

    @native_tool
    async def search_knowledge_base(
        self,
        query: Annotated[str, Field(description="Question ou sujet à rechercher dans la base de connaissances")],
        collection: Annotated[Optional[str], Field(default=None, description="Nom de la collection (optionnel, utilise la collection par défaut si absent)")] = None,
    ) -> list[dict]:
        """
        Recherche les passages les plus pertinents dans la base de connaissances.
        À utiliser dès que l'utilisateur pose une question sur un sujet documenté ou demande des informations générales non couvertes par les autres outils.
        Retourne les extraits de texte les plus pertinents avec leur score de similarité.
        """
        retriever = Retriever(collection=collection)
        return await retriever.search(query)
