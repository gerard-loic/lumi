import os
import re
from datetime import date
from typing import Annotated, Optional

from fpdf import FPDF
from fpdf.fonts import FontFace
from pydantic import BaseModel, Field

from tools.charts._charts import render_chart
from tools.pdf import _pdf_template as pt
from lib.agent.events import FileEvent
from lib.files.filestore import FileStore
from lib.mcp.tools import MCPTool, confirmation_tool

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

_MUTED_RGB = (90, 90, 90)

_INLINE_RE = re.compile(
    r"(\*\*[^*]+\*\*)"        # **bold**
    r"|(\*[^*]+\*)"            # *italic* (rendu sans mise en forme, police manquante)
    r"|(~~[^~]+~~)"            # ~~strikethrough~~
    r"|(__[^_]+__)"            # __underline__
    r"|(`[^`]+`)"              # `inline code`
    r"|(\[[^\]]+\]\([^)]+\))"  # [text](url)
)


class _TemplatedPDF(FPDF):
    """
    PDF dont l'en-tête, le pied de page et les couleurs suivent le gabarit
    configuré (voir tools/pdf/_pdf_template.py). Le gabarit est entièrement
    facultatif : sans configuration ni titre, le rendu reste celui d'un PDF nu.
    """

    def __init__(self, titre: str | None):
        super().__init__()
        self.titre = titre
        self.color_rgb = pt.hex_to_rgb(pt.template_color())
        self.logo_path = pt.template_logo()
        self.footer_text = pt.template_footer_text()
        self.chrome = bool(titre or self.logo_path or self.footer_text)

    def _on_cover_page(self) -> bool:
        return bool(self.titre) and self.page_no() == 1

    def header(self) -> None:
        if not self.chrome or self._on_cover_page():
            return
        y = 10
        if self.logo_path:
            self.image(self.logo_path, x=self.l_margin, y=y, h=10)
        if self.titre:
            self.set_font(_FONT, style="B", size=10)
            self.set_text_color(*self.color_rgb)
            self.set_xy(self.l_margin, y)
            self.cell(self.epw, 10, self.titre, align="R")
        self.set_draw_color(*self.color_rgb)
        self.set_line_width(0.4)
        self.line(self.l_margin, y + 14, self.w - self.r_margin, y + 14)
        self.set_text_color(0, 0, 0)
        self.set_y(y + 18)

    def footer(self) -> None:
        if not self.chrome or self._on_cover_page():
            return
        self.set_y(-15)
        self.set_font(_FONT, size=9)
        self.set_text_color(*_MUTED_RGB)
        text = f"Page {self.page_no()}/{{nb}}"
        if self.footer_text:
            text = f"{self.footer_text}  —  {text}"
        self.cell(0, 10, text, align="C")
        self.set_text_color(0, 0, 0)


def _render_cover(pdf: _TemplatedPDF, titre: str, sous_titre: str | None) -> None:
    pdf.add_page()
    if pdf.logo_path:
        pdf.image(pdf.logo_path, x=pdf.w / 2 - 15, y=30, w=30)
    pdf.set_y(110)
    pdf.set_font(_FONT, style="B", size=26)
    pdf.set_text_color(*pdf.color_rgb)
    pdf.multi_cell(0, 12, titre, align="C")
    if sous_titre:
        pdf.ln(4)
        pdf.set_font(_FONT, size=14)
        pdf.set_text_color(*_MUTED_RGB)
        pdf.multi_cell(0, 8, sous_titre, align="C")
    pdf.set_y(-35)
    pdf.set_font(_FONT, size=10)
    pdf.set_text_color(*_MUTED_RGB)
    pdf.cell(0, 10, date.today().strftime("%d/%m/%Y"), align="C")
    pdf.set_text_color(0, 0, 0)


def _make_pdf(titre: str | None = None, sous_titre: str | None = None) -> _TemplatedPDF:
    pdf = _TemplatedPDF(titre)
    pdf.add_font(_FONT, style="", fname=_FONT_REGULAR)
    pdf.add_font(_FONT, style="B", fname=_FONT_BOLD)
    pdf.add_font(_FONT_MONO, style="", fname=_FONT_MONO_REGULAR)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_margins(20, 30 if pdf.chrome else 20, 20)
    pdf.alias_nb_pages()
    if titre:
        _render_cover(pdf, titre, sous_titre)
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
        titre: Annotated[
            Optional[str],
            Field(
                default=None,
                description=(
                    "Titre du document. S'il est fourni, une page de garde est ajoutée "
                    "(titre, sous-titre, date) ainsi qu'un en-tête et un pied de page "
                    "(titre, numérotation) sur les pages suivantes, selon le gabarit configuré."
                ),
            ),
        ] = None,
        sous_titre: Annotated[
            Optional[str],
            Field(default=None, description="Sous-titre affiché sous le titre sur la page de garde (ignoré si titre est omis)."),
        ] = None,
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
        Si titre est fourni, applique le gabarit (page de garde, en-tête, pied de page) configuré
        pour l'outil PDF (voir la clé de configuration "pdf").
        """
        filename = (nom_fichier or "document").removesuffix(".pdf") + ".pdf"
        pdf = _make_pdf(titre, sous_titre)

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

    def _render_table(self, pdf: _TemplatedPDF, rows: list[list[str]]) -> None:
        if not rows:
            return
        pdf.ln(2)
        pdf.set_font(_FONT, size=10)
        header_style = FontFace(emphasis="B", color=(255, 255, 255), fill_color=pdf.color_rgb)
        with pdf.table(
            first_row_as_headings=True,
            headings_style=header_style,
            borders_layout="ALL",
            line_height=6,
        ) as table:
            for row_data in rows:
                row = table.row()
                for cell in row_data:
                    row.cell(cell)
        pdf.ln(2)

    def _heading(self, pdf: _TemplatedPDF, text: str, size: int) -> None:
        pdf.ln(2)
        pdf.set_font(_FONT, style="B", size=size)
        pdf.set_text_color(*pdf.color_rgb)
        pdf.multi_cell(0, size * 0.45, text.strip())
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)

    def _bullet(self, pdf: _TemplatedPDF, text: str) -> None:
        pdf.set_font(_FONT, size=11)
        pdf.write(_LINE_H, "  • ")
        self._write_inline(pdf, text.strip())
        pdf.ln()

    def _numbered(self, pdf: _TemplatedPDF, num: str, text: str) -> None:
        pdf.set_font(_FONT, size=11)
        pdf.write(_LINE_H, f"  {num}. ")
        self._write_inline(pdf, text.strip())
        pdf.ln()

    def _write_inline(self, pdf: _TemplatedPDF, text: str) -> None:
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
