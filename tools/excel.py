import csv
import io
from pydantic import BaseModel, Field
from typing import Annotated, Optional
from openpyxl import Workbook
from lib.files.filestore import FileStore
from lib.agent.events import FileEvent
from lib.mcp.tools import MCPTool
from lib.mcp.tools import native_tool

class FichierExcel(BaseModel):
    url: str = Field(description="URL de téléchargement du fichier Excel généré.")


class ExcelService(MCPTool):
    name = "excel"
    description = "Génération de fichiers Excel"

    @native_tool
    def generer_fichier_excel(
        self,
        donnees_csv: Annotated[
            str,
            Field(description=(
                "Données tabulaires au format CSV (séparateur virgule). "
                "La première ligne doit contenir les en-têtes de colonnes. "
                "Exemple : \"Nom,Ville,Débit\\nDupont,Paris,100\\nMartin,Lyon,200\""
            )),
        ],
        nom_fichier: Annotated[
            Optional[str],
            Field(default=None, description="Nom du fichier Excel à générer (ex: 'export.xlsx'). Si omis, 'export.xlsx' est utilisé."),
        ] = None,
    ) -> FichierExcel:
        """
        Génère un fichier Excel (.xlsx) à partir de données CSV et retourne l'URL de téléchargement.
        À utiliser dès que l'utilisateur demande un export Excel, un tableau téléchargeable, ou un fichier de données.
        """
        filename = (nom_fichier or "export").removesuffix(".xlsx") + ".xlsx"

        reader = csv.reader(io.StringIO(donnees_csv.strip()))
        rows = list(reader)

        wb = Workbook()
        ws = wb.active
        for row in rows:
            ws.append(row)

        buffer = io.BytesIO()
        wb.save(buffer)

        url = FileStore.save(filename=filename, content=buffer.getvalue())
        self.emit(FileEvent.get(name=filename, url=url))
        return FichierExcel(url=url)
