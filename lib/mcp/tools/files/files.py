from typing import Annotated, Optional
from pydantic import BaseModel, Field
from lib.mcp.toolloader import MCPTool, slow_tool, tool_description
from lib.http.auth import Auth
from lib.agent.events import RagEvent
from lib.rag.attachmentretriever import AttachmentRetriever


class ExtraitFichier(BaseModel):
    fichier: str = Field(description="Nom du fichier joint dont provient l'extrait")
    extrait: str = Field(description="Extrait de texte pertinent")
    page: Optional[int] = Field(default=None, description="Numéro de page dont provient l'extrait, si le fichier est paginé (PDF)")


class ResultatFichiersJoints(BaseModel):
    resultats: list[ExtraitFichier] = Field(description="Extraits les plus pertinents parmi les fichiers joints par l'utilisateur à la conversation")


class FilesTool(MCPTool):
    name = "files"
    description = "Recherche dans les fichiers joints à la conversation par l'utilisateur"

    @slow_tool
    @tool_description(name="[files.search_attached_files]")
    async def search_attached_files(
        self,
        query: Annotated[str, Field(description="Question ou sujet à rechercher dans les fichiers joints par l'utilisateur à la conversation")],
    ) -> ResultatFichiersJoints:
        """
        Recherche les passages les plus pertinents parmi les fichiers que l'utilisateur a joints à la
        conversation (via le bouton de pièce jointe du chat). À utiliser dès que l'utilisateur pose une
        question sur le contenu d'un document qu'il a envoyé, ou demande un résumé/une analyse d'un fichier joint.
        Ne pas confondre avec search_knowledge_base (base de connaissances générale) : cet outil ne porte
        que sur les fichiers explicitement joints par l'utilisateur dans cette conversation. Si aucun fichier
        n'a été joint, retourne une liste vide.
        """
        session_id = Auth.getSessionId()
        results = await AttachmentRetriever().search(session_id, query)

        #Signale au client les documents utilisés pour construire la réponse (un événement par fichier distinct)
        for filename, pages in AttachmentRetriever.group_pages_by_file(results).items():
            self.emit(RagEvent.get(source=filename, locations=pages))

        return ResultatFichiersJoints(resultats=[
            ExtraitFichier(fichier=r["filename"], extrait=r["text"], page=r.get("page")) for r in results
        ])
