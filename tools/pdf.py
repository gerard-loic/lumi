import os
import re
from typing import Annotated, Optional

from fpdf import FPDF
from fpdf.fonts import FontFace
from pydantic import BaseModel, Field

from tools._charts import render_chart
from lib.agent.events import FileEvent
from lib.files.filestore import FileStore
from lib.mcp.tools import MCPTool, confirmation_tool, native_tool

_LINE_H = 6
_FONT = "DejaVuSans"
_FONT_MONO = "DejaVuSansMono"


def _find_font(filename: str) -> str:
    candidates = [
        f"/usr/share/fonts/truetype/dejavu/{filename}",
        f"/usr/share/fonts/dejavu/{filename}",
        f"/usr/share/fonts/TTF/{filename}",
    ]
    try:
        import matplotlib
        candidates.append(os.path.join(matplotlib.get_data_path(), "fonts", "ttf", filename))
    except ImportError:
        pass
    for path in candidates:
        if os.path.exists(path):
            return path
    raise FileNotFoundError(f"Police introuvable : {filename}. Chemins testés : {candidates}")


_FONT_REGULAR = _find_font("DejaVuSans.ttf")
_FONT_BOLD = _find_font("DejaVuSans-Bold.ttf")
_FONT_MONO_REGULAR = _find_font("DejaVuSansMono.ttf")

_TABLE_HEADER_STYLE = FontFace(emphasis="B", fill_color=(220, 220, 220))

_INLINE_RE = re.compile(
    r"(\*\*[^*]+\*\*)"        # **bold**
    r"|(\*[^*]+\*)"            # *italic* (rendu sans mise en forme, police manquante)
    r"|(~~[^~]+~~)"            # ~~strikethrough~~
    r"|(__[^_]+__)"            # __underline__
    r"|(`[^`]+`)"              # `inline code`
    r"|(\[[^\]]+\]\([^)]+\))"  # [text](url)
)


def _make_pdf() -> FPDF:
    pdf = FPDF()
    pdf.add_font(_FONT, style="", fname=_FONT_REGULAR)
    pdf.add_font(_FONT, style="B", fname=_FONT_BOLD)
    pdf.add_font(_FONT_MONO, style="", fname=_FONT_MONO_REGULAR)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_margins(20, 20, 20)
    pdf.add_page()
    return pdf


def _parse_table(table_lines: list[str]) -> list[list[str]]:
    rows = []
    for line in table_lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(re.match(r"^:?-+:?$", c) for c in cells if c):
            continue
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
                    "Contenu du document en Markdown enrichi. "
                    "Supporte : titres (# ## ###), gras (**texte**), barré (~~texte~~), "
                    "souligné (__texte__), code inline (`texte`), liens ([texte](url)), "
                    "tableaux (| col | col |), listes à puces (- item) et numérotées (1. item). "
                    "Directives de mise en page (sur leur propre ligne) : "
                    ":::pagebreak (saut de page), "
                    ":::chart:N (insère le graphique d'index N depuis le paramètre graphiques)."
                )
            ),
        ],
        graphiques: Annotated[
            Optional[list[dict]],
            Field(
                default=None,
                description=(
                    "Graphiques à insérer (liste d'objets). Chaque élément a : "
                    "\"type\" ('barres', 'courbes' ou 'camembert'), "
                    "\"titre\" (chaîne), "
                    "\"données\" : pour 'barres'/'courbes' : {\"labels\":[...], \"series\":[{\"nom\":\"...\",\"valeurs\":[...]}]} ; "
                    "pour 'camembert' : {\"labels\":[...], \"valeurs\":[...]}. "
                    "Placer dans le markdown via :::chart:0, :::chart:1, etc. "
                    "Exemple : [{\"type\":\"camembert\",\"titre\":\"Répartition\","
                    "\"données\":{\"labels\":[\"A\",\"B\"],\"valeurs\":[60,40]}}]"
                ),
            ),
        ] = None,
        nom_fichier: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Nom du fichier PDF (ex: 'rapport.pdf'). Si omis, 'document.pdf' est utilisé.",
            ),
        ] = None,
    ) -> FichierPDF:
        """
        Génère un fichier PDF à partir de contenu Markdown enrichi et retourne l'URL de téléchargement.
        À utiliser dès que l'utilisateur demande un export PDF, un document téléchargeable, un rapport ou un compte-rendu.
        Supporte l'insertion de graphiques (barres, courbes, camembert) via le paramètre graphiques.
        """
        filename = (nom_fichier or "document").removesuffix(".pdf") + ".pdf"
        pdf = _make_pdf()

        charts = graphiques or []
        chart_images = [render_chart(c) for c in charts]

        lines = contenu_markdown.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]

            if line.strip().startswith(":::"):
                directive = line.strip()[3:].strip()
                if directive == "pagebreak":
                    pdf.add_page()
                elif directive.startswith("chart:"):
                    idx = int(directive.split(":", 1)[1])
                    if 0 <= idx < len(chart_images):
                        chart_images[idx].seek(0)
                        pdf.image(chart_images[idx], x=pdf.l_margin, w=pdf.epw)
                        pdf.ln(4)
                i += 1
                continue

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
        pdf.write(_LINE_H, "  • ")
        self._write_inline(pdf, text.strip())
        pdf.ln()

    def _numbered(self, pdf: FPDF, num: str, text: str) -> None:
        pdf.set_font(_FONT, size=11)
        pdf.write(_LINE_H, f"  {num}. ")
        self._write_inline(pdf, text.strip())
        pdf.ln()

    def _write_inline(self, pdf: FPDF, text: str) -> None:
        size = pdf.font_size_pt
        last = 0
        for m in _INLINE_RE.finditer(text):
            start, end = m.start(), m.end()
            if start > last:
                pdf.set_font(_FONT, size=size)
                pdf.write(_LINE_H, text[last:start])
            token = m.group(0)
            if token.startswith("**"):
                pdf.set_font(_FONT, style="B", size=size)
                pdf.write(_LINE_H, token[2:-2])
            elif token.startswith("*"):
                pdf.set_font(_FONT, size=size)
                pdf.write(_LINE_H, token[1:-1])
            elif token.startswith("~~"):
                pdf.set_font(_FONT, style="S", size=size)
                pdf.write(_LINE_H, token[2:-2])
            elif token.startswith("__"):
                pdf.set_font(_FONT, style="U", size=size)
                pdf.write(_LINE_H, token[2:-2])
            elif token.startswith("`"):
                pdf.set_font(_FONT_MONO, size=size - 1)
                pdf.write(_LINE_H, token[1:-1])
            elif token.startswith("["):
                link_m = re.match(r"\[([^\]]+)\]\(([^)]+)\)", token)
                if link_m:
                    pdf.set_font(_FONT, style="U", size=size)
                    pdf.write(_LINE_H, link_m.group(1), link=link_m.group(2))
            last = end
        if last < len(text):
            pdf.set_font(_FONT, size=size)
            pdf.write(_LINE_H, text[last:])
