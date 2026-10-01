from datetime import date, datetime

#DataView : vue tabulaire manipulable construite à partir d'un dict ou d'une liste.
#Ne réside pas dans lib/pipelines/blocks pour rester un utilitaire réutilisable (à l'image de
#lib/pipelines/utils/apirequest.py) ; le bloc DataView se contente de l'instancier et d'enchainer
#ses méthodes selon la configuration.
#
#Représentation interne : une liste de lignes (dict) + une liste ordonnée de colonnes (self._columns
#fait foi pour l'ordre et la présence des colonnes). Les cellules absentes valent None. Toutes les
#méthodes de transformation modifient la vue en place et renvoient self pour permettre le chainage :
#    DataView.from_data(data).filter(...).order_by("age", desc=True).drop_columns("token").to_list()

#Opérateurs disponibles pour where() et pour la construction de prédicats côté bloc.
#Chaque fonction reçoit (valeur_de_la_ligne, valeur_de_reference) et renvoie un booléen. Les
#comparaisons d'ordre sont neutres sur None (jamais vraies) pour ne pas lever sur des cellules vides.
OPERATORS = {
    "==":         lambda a, b: a == b,
    "!=":         lambda a, b: a != b,
    ">":          lambda a, b: a is not None and a > b,
    "<":          lambda a, b: a is not None and a < b,
    ">=":         lambda a, b: a is not None and a >= b,
    "<=":         lambda a, b: a is not None and a <= b,
    "in":         lambda a, b: a in b if b is not None else False,
    "not in":     lambda a, b: a not in b if b is not None else True,
    "contains":   lambda a, b: b in a if a is not None else False,
    "startswith": lambda a, b: str(a).startswith(str(b)) if a is not None else False,
    "endswith":   lambda a, b: str(a).endswith(str(b)) if a is not None else False,
}


class DataView:
    def __init__(self, rows=None, columns=None):
        self._rows = []
        self._columns = list(columns) if columns else []
        if rows:
            self.add_rows(rows)

    # --------------------------------------------------------------- construction
    #Normalise un dict / une liste / un scalaire en vue tabulaire :
    #  - list[dict]           -> une ligne par élément
    #  - list[scalaire]       -> une ligne {value_column: element}
    #  - dict[str, dict]      -> une ligne par entrée, la clé rangée dans key_column
    #  - dict[str, scalaire]  -> une ligne {key_column: cle, value_column: valeur}
    #  - dict hétérogène      -> un enregistrement unique (une seule ligne)
    #  - scalaire             -> une ligne {value_column: valeur}
    @classmethod
    def from_data(cls, data, key_column="key", value_column="value"):
        if isinstance(data, list):
            rows = []
            for item in data:
                rows.append(dict(item) if isinstance(item, dict) else {value_column: item})
            return cls(rows)

        if isinstance(data, dict):
            values = list(data.values())
            if values and all(isinstance(v, dict) for v in values):
                return cls([{key_column: k, **v} for k, v in data.items()])
            if all(not isinstance(v, (dict, list)) for v in values):
                return cls([{key_column: k, value_column: v} for k, v in data.items()])
            return cls([dict(data)])

        return cls([{value_column: data}])

    # ------------------------------------------------------------------- internes
    def _track_columns(self, row):
        for key in row:
            if key not in self._columns:
                self._columns.append(key)

    @staticmethod
    def _as_list(value):
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return list(value)
        return [value]

    #Clé de tri robuste sur colonnes hétérogènes / valeurs manquantes : (rang_de_type, valeur).
    #Le rang garantit un ordre total (None < nombres < dates < chaines) sans lever de TypeError.
    @staticmethod
    def _sortable(value):
        if value is None:
            return (0, "")
        if isinstance(value, bool):
            return (1, int(value))
        if isinstance(value, (int, float)):
            return (1, value)
        if isinstance(value, (datetime, date)):
            return (2, value.isoformat())
        return (3, str(value))

    # --------------------------------------------------------------------- lignes
    #rows : un dict (une ligne) ou un itérable de dicts. Les nouvelles colonnes sont ajoutées à la
    #suite de self._columns dans leur ordre d'apparition.
    def add_rows(self, rows):
        if isinstance(rows, dict):
            rows = [rows]
        for row in rows:
            if not isinstance(row, dict):
                raise TypeError("DataView.add_rows attend des lignes de type dict")
            row = dict(row)
            self._track_columns(row)
            self._rows.append(row)
        return self

    #predicate : callable(row) -> bool. Conserve les lignes pour lesquelles il renvoie vrai.
    def filter(self, predicate):
        self._rows = [r for r in self._rows if predicate(r)]
        return self

    #Filtre pratique basé sur OPERATORS. keep=False inverse la sélection.
    def where(self, field, op, value, keep=True):
        test = OPERATORS.get(op)
        if test is None:
            raise ValueError(f"Opérateur non supporté : {op}")
        return self.filter(lambda row: bool(test(row.get(field), value)) == keep)

    #Supprime des lignes par prédicat (celles qui valident) et/ou par position (indices, négatifs admis).
    def drop_rows(self, predicate=None, indices=None):
        if indices is not None:
            drop = {i if i >= 0 else len(self._rows) + i for i in indices}
            self._rows = [r for i, r in enumerate(self._rows) if i not in drop]
        if predicate is not None:
            self._rows = [r for r in self._rows if not predicate(r)]
        return self

    # -------------------------------------------------------------------- colonnes
    #value : une constante, ou un callable(row) -> valeur pour une colonne calculée.
    def add_column(self, name, value):
        for row in self._rows:
            row[name] = value(row) if callable(value) else value
        if name not in self._columns:
            self._columns.append(name)
        return self

    def drop_columns(self, *names):
        names = set(self._as_list(names[0]) if len(names) == 1 else names)
        self._columns = [c for c in self._columns if c not in names]
        for row in self._rows:
            for n in names:
                row.pop(n, None)
        return self

    #Ne conserve que les colonnes demandées, dans l'ordre fourni.
    def select(self, *names):
        names = self._as_list(names[0]) if len(names) == 1 else list(names)
        self._columns = list(names)
        self._rows = [{n: r.get(n) for n in names} for r in self._rows]
        return self

    def rename_column(self, old, new):
        self._columns = [new if c == old else c for c in self._columns]
        for row in self._rows:
            if old in row:
                row[new] = row.pop(old)
        return self

    # ----------------------------------------------------------------------- ordre
    #by : un nom de colonne ou une liste de noms (tri multi-critères, stable).
    def order_by(self, by, desc=False):
        keys = self._as_list(by)
        self._rows.sort(key=lambda row: [self._sortable(row.get(k)) for k in keys], reverse=bool(desc))
        return self

    # ------------------------------------------------------------------ conversion
    def _normalized_row(self, row):
        return {c: row.get(c) for c in self._columns}

    #Liste de lignes (dict). flatten=True et une seule colonne -> liste de scalaires.
    def to_list(self, flatten=False):
        rows = [self._normalized_row(r) for r in self._rows]
        if flatten and len(self._columns) == 1:
            col = self._columns[0]
            return [r[col] for r in rows]
        return rows

    #key=None      -> forme colonnaire {colonne: [valeurs...]}
    #key="col"     -> {ligne["col"]: ligne} (ou {ligne["col"]: ligne[value]} si value fourni)
    def to_dict(self, key=None, value=None):
        if key is None:
            return {c: [r.get(c) for r in self._rows] for c in self._columns}
        return {
            row.get(key): (row.get(value) if value is not None else self._normalized_row(row))
            for row in self._rows
        }

    @property
    def columns(self):
        return list(self._columns)

    def __len__(self):
        return len(self._rows)

    def __iter__(self):
        return iter(self.to_list())
