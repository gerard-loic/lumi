import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def render_chart(chart: dict) -> io.BytesIO:
    chart_type = chart.get("type", "barres")
    titre = chart.get("titre", "")
    données = chart.get("données", {})

    fig, ax = plt.subplots(figsize=(8, 4.5))

    if chart_type == "barres":
        labels = données.get("labels", [])
        series = données.get("series", [])
        x = list(range(len(labels)))
        n = max(len(series), 1)
        width = 0.8 / n
        for idx, série in enumerate(series):
            offsets = [xi + (idx - n / 2 + 0.5) * width for xi in x]
            ax.bar(offsets, série.get("valeurs", []), width=width, label=série.get("nom", ""))
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        if len(series) > 1:
            ax.legend()

    elif chart_type == "courbes":
        labels = données.get("labels", [])
        series = données.get("series", [])
        for série in series:
            ax.plot(labels, série.get("valeurs", []), marker="o", label=série.get("nom", ""))
        if len(series) > 1:
            ax.legend()

    elif chart_type == "camembert":
        labels = données.get("labels", [])
        valeurs = données.get("valeurs", [])
        pairs = [(l, v) for l, v in zip(labels, valeurs) if v and v > 0]
        if not pairs:
            ax.text(0.5, 0.5, "Aucune donnée", ha="center", va="center", transform=ax.transAxes)
        else:
            labels, valeurs = zip(*pairs)
            ax.pie(valeurs, labels=labels, autopct="%1.1f%%", startangle=90)
            ax.axis("equal")

    if titre:
        ax.set_title(titre)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf
