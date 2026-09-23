from datetime import date, datetime, time
from decimal import Decimal

#tabular : conversion d'une matrice (liste de listes) en lignes exploitables par le bloc DataView
#(list[dict]) ou en forme colonnaire ({colonne: [valeurs]}). Partagé par CsvReader et ExcelReader.
#
#build_records(matrix, ...) -> list[dict]
#  - skip_rows   : nombre de lignes ignorées en tête (avant tout traitement).
#  - skip_empty  : ignore les lignes entièrement vides (toutes cellules None ou "").
#  - trim        : retire les espaces de début / fin des cellules chaine.
#  - has_header  : la première ligne restante porte les noms de colonnes.
#  - columns     : noms de colonnes imposés. Avec has_header, la première ligne est alors sautée.
#                  Sans has_header ni columns, les colonnes sont nommées "col_1", "col_2", ...
#  - infer_types : tente de convertir les cellules chaine en int puis float (utile pour un CSV,
#                  dont toutes les valeurs sont des chaines).
#
#to_output(records, as_) -> list[dict] (as_="list") ou {colonne: [valeurs]} (as_="dict").


def _json_safe(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _coerce(value):
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if stripped == "":
        return value
    try:
        return int(stripped)
    except ValueError:
        pass
    try:
        return float(stripped)
    except ValueError:
        pass
    return value


def build_records(matrix, has_header:bool=True, columns=None, skip_rows:int=0,
                  skip_empty:bool=True, trim:bool=True, infer_types:bool=False, limit:int=0):
    rows = [list(r) for r in matrix]

    if skip_rows:
        rows = rows[skip_rows:]

    rows = [[_json_safe(c) for c in r] for r in rows]

    if trim:
        rows = [[c.strip() if isinstance(c, str) else c for c in r] for r in rows]

    if skip_empty:
        rows = [r for r in rows if any(c is not None and str(c).strip() != "" for c in r)]

    if infer_types:
        rows = [[_coerce(c) for c in r] for r in rows]

    header = [str(c) for c in columns] if columns else None

    if has_header:
        if not rows:
            return []
        if header is None:
            header = [str(c) if c not in (None, "") else f"col_{i + 1}"
                      for i, c in enumerate(rows[0])]
        rows = rows[1:]

    if header is None:
        width = max((len(r) for r in rows), default=0)
        header = [f"col_{i + 1}" for i in range(width)]

    if limit and limit > 0:
        rows = rows[:limit]

    records = []
    for r in rows:
        records.append({name: (r[i] if i < len(r) else None) for i, name in enumerate(header)})
    return records


def to_output(records, as_:str="list"):
    if str(as_).lower() == "dict":
        columns = list(dict.fromkeys(k for rec in records for k in rec))
        return {c: [rec.get(c) for rec in records] for c in columns}
    return records
