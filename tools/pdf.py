import re
from typing import Annotated, Optional

from fpdf import FPDF
from fpdf.fonts import FontFace
from pydantic import BaseModel, Field

from lib.agent.events import FileEvent
from lib.files.filestore import FileStore
from lib.mcp.tools import MCPTool, confirmation_tool, native_tool, restricted_tool

_LINE_H = 6
_FONT = "DejaVuSans"
_FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

_TABLE_HEADER_STYLE = FontFace(emphasis="B", fill_color=(220, 220, 220))


def _make_pdf() -> FPDF:
    pdf = FPDF()
    pdf.add_font(_FONT, style="", fname=_FONT_REGULAR)
    pdf.add_font(_FONT, style="B", fname=_FONT_BOLD)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_margins(20, 20, 20)
    pdf.add_page()
    return pdf


def _parse_table(table_lines: list[str]) -> list[list[str]]:
    rows = []
    for line in table_lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(re.match(r"^:?-+:?$", c) for c in cells if c):
            continue  # ligne séparatrice |---|---|
        rows.append(cells)
    return rows


class FichierPDF(BaseModel):
    url: str = Field(description="URL de téléchargement du fichier PDF généré.")


class PdfService(MCPTool):
    name = "pdf"
    description = "Génération de fichiers PDF"

    @native_tool
    @confirmation_tool(
        question="Je vais générer le fichier PDF. Dois-je continuer ?",
        options=["Oui", "Non"],
        validation_option=0,
    )
    def generer_fichier_pdf(
        self,
        contenu_markdown: Annotated[
            str,
            Field(
                description=(
                    "Contenu du document en Markdown. "
                    "Supporte les titres (# ## ###), le gras (**texte**), "
                    "les tableaux (| col | col |), "
                    "les listes à puces (- item) et numérotées (1. item), et les paragraphes. "
                    'Exemple : "# Rapport\\n\\n| Col A | Col B |\\n|---|---|\\n| val | val |"'
                )
            ),
        ],
        nom_fichier: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Nom du fichier PDF (ex: 'rapport.pdf'). Si omis, 'document.pdf' est utilisé.",
            ),
        ] = None,
    ) -> FichierPDF:
        """
        Génère un fichier PDF à partir de contenu Markdown et retourne l'URL de téléchargement.
        À utiliser dès que l'utilisateur demande un export PDF, un document téléchargeable, un rapport ou un compte-rendu.
        """
        filename = (nom_fichier or "document").removesuffix(".pdf") + ".pdf"
        pdf = _make_pdf()

        lines = contenu_markdown.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]

            if re.match(r"^\s*\|", line):
                table_lines = []
                while i < len(lines) and re.match(r"^\s*\|", lines[i]):
                    table_lines.append(lines[i])
                    i += 1
                self._render_table(pdf, _parse_table(table_lines))
                continue

            if line.startswith("### "):
                self._heading(pdf, line[4:], size=13)
            elif line.startswith("## "):
                self._heading(pdf, line[3:], size=16)
            elif line.startswith("# "):
                self._heading(pdf, line[2:], size=20)
            elif re.match(r"^[-*] ", line):
                self._bullet(pdf, line[2:])
            elif m := re.match(r"^(\d+)\. (.*)", line):
                self._numbered(pdf, m.group(1), m.group(2))
            elif line.strip() == "":
                pdf.ln(4)
            else:
                pdf.set_font(_FONT, size=11)
                self._write_inline(pdf, line)
                pdf.ln()
            i += 1

        content = bytes(pdf.output())
        url = FileStore.save(filename=filename, content=content)
        self.emit(FileEvent.get(name=filename, url=url))
        return FichierPDF(url=url)

    def _render_table(self, pdf: FPDF, rows: list[list[str]]) -> None:
        if not rows:
            return
        pdf.ln(2)
        pdf.set_font(_FONT, size=10)
        with pdf.table(
            first_row_as_headings=True,
            headings_style=_TABLE_HEADER_STYLE,
            borders_layout="ALL",
            line_height=6,
        ) as table:
            for row_data in rows:
                row = table.row()
                for cell in row_data:
                    row.cell(cell)
        pdf.ln(2)

    def _heading(self, pdf: FPDF, text: str, size: int) -> None:
        pdf.ln(2)
        pdf.set_font(_FONT, style="B", size=size)
        pdf.multi_cell(0, size * 0.45, text.strip())
        pdf.ln(2)

    def _bullet(self, pdf: FPDF, text: str) -> None:
        pdf.set_font(_FONT, size=11)
        pdf.write(_LINE_H, "  - ")
        self._write_inline(pdf, text.strip())
        pdf.ln()

    def _numbered(self, pdf: FPDF, num: str, text: str) -> None:
        pdf.set_font(_FONT, size=11)
        pdf.write(_LINE_H, f"  {num}. ")
        self._write_inline(pdf, text.strip())
        pdf.ln()

    def _write_inline(self, pdf: FPDF, text: str) -> None:
        size = pdf.font_size_pt
        for part in re.split(r"(\*\*[^*]+\*\*)", text):
            if part.startswith("**") and part.endswith("**"):
                pdf.set_font(_FONT, style="B", size=size)
                pdf.write(_LINE_H, part[2:-2])
            elif part:
                pdf.set_font(_FONT, size=size)
                pdf.write(_LINE_H, part)
