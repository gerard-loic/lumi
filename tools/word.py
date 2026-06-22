import io
import re
from typing import Annotated, Optional

from docx import Document
from docx.shared import Pt, RGBColor
from pydantic import BaseModel, Field

from lib.agent.events import FileEvent
from lib.files.filestore import FileStore
from lib.mcp.tools import MCPTool, confirmation_tool, native_tool


class FichierWord(BaseModel):
    url: str = Field(description="URL de téléchargement du fichier Word généré.")


class WordService(MCPTool):
    name = "word"
    description = "Génération de fichiers Word"

    @native_tool
    @confirmation_tool(
        question="Je vais générer le fichier Word. Dois-je continuer ?",
        options=["Oui", "Non"],
        validation_option=0,
    )
    def generer_fichier_word(
        self,
        contenu_markdown: Annotated[
            str,
            Field(
                description=(
                    "Contenu du document en Markdown. "
                    "Supporte les titres (# ## ###), le gras (**texte**), "
                    "les tableaux (| col | col |), "
                    "les listes à puces (- item) et numérotées (1. item), et les paragraphes. "
                    'Exemple : "# Rapport\\n\\n**Résumé** : texte\\n\\n- item 1\\n- item 2"'
                )
            ),
        ],
        nom_fichier: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Nom du fichier Word (ex: 'rapport.docx'). Si omis, 'document.docx' est utilisé.",
            ),
        ] = None,
    ) -> FichierWord:
        """
        Génère un fichier Word (.docx) à partir de contenu Markdown et retourne l'URL de téléchargement.
        À utiliser dès que l'utilisateur demande un export Word, un document téléchargeable, un rapport ou un compte-rendu au format Word.
        """
        filename = (nom_fichier or "document").removesuffix(".docx") + ".docx"
        doc = Document()

        lines = contenu_markdown.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]

            if re.match(r"^\s*\|", line):
                table_lines = []
                while i < len(lines) and re.match(r"^\s*\|", lines[i]):
                    table_lines.append(lines[i])
                    i += 1
                self._render_table(doc, _parse_table(table_lines))
                continue

            if line.startswith("### "):
                doc.add_heading(line[4:].strip(), level=3)
            elif line.startswith("## "):
                doc.add_heading(line[3:].strip(), level=2)
            elif line.startswith("# "):
                doc.add_heading(line[2:].strip(), level=1)
            elif re.match(r"^[-*] ", line):
                p = doc.add_paragraph(style="List Bullet")
                _write_inline(p, line[2:].strip())
            elif m := re.match(r"^(\d+)\. (.*)", line):
                p = doc.add_paragraph(style="List Number")
                _write_inline(p, m.group(2).strip())
            elif line.strip() == "":
                doc.add_paragraph("")
            else:
                p = doc.add_paragraph()
                _write_inline(p, line)

            i += 1

        buffer = io.BytesIO()
        doc.save(buffer)

        url = FileStore.save(filename=filename, content=buffer.getvalue())
        self.emit(FileEvent.get(name=filename, url=url))
        return FichierWord(url=url)

    def _render_table(self, doc: Document, rows: list[list[str]]) -> None:
        if not rows:
            return
        col_count = max(len(r) for r in rows)
        table = doc.add_table(rows=len(rows), cols=col_count)
        table.style = "Table Grid"
        for r_idx, row_data in enumerate(rows):
            for c_idx, cell_text in enumerate(row_data):
                cell = table.cell(r_idx, c_idx)
                cell.text = cell_text
                if r_idx == 0:
                    for run in cell.paragraphs[0].runs:
                        run.bold = True
        doc.add_paragraph("")


def _parse_table(table_lines: list[str]) -> list[list[str]]:
    rows = []
    for line in table_lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(re.match(r"^:?-+:?$", c) for c in cells if c):
            continue
        rows.append(cells)
    return rows


def _write_inline(paragraph, text: str) -> None:
    for part in re.split(r"(\*\*[^*]+\*\*)", text):
        if part.startswith("**") and part.endswith("**"):
            run = paragraph.add_run(part[2:-2])
            run.bold = True
        elif part:
            paragraph.add_run(part)
