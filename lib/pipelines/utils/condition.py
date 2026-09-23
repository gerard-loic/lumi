import re

#condition : évaluateur d'expressions booléennes sur des variables de contexte, partagé par le bloc
#Condition (et réutilisable ailleurs). Réside dans lib/pipelines/utils comme apirequest / dataview /
#filesource.
#
#Grammaire (par ordre de priorité croissante) :
#    or_expr    := and_expr (OR and_expr)*
#    and_expr   := not_expr (AND not_expr)*
#    not_expr   := NOT not_expr | comparison
#    comparison := primary (COMP primary)?
#    primary    := '(' or_expr ')' | operand
#
#Opérateurs de comparaison (COMP) : =  ==  !=  <>  <  >  <=  >=  IN  "NOT IN"
#Opérateurs logiques : AND  OR  NOT   (insensibles à la casse), groupements par parenthèses.
#
#Opérandes :
#  - chaine littérale : "texte" ou 'texte' ;
#  - nombre : 42, -3.5 ;
#  - booléen : true / false ; nul : none / null (insensibles à la casse) ;
#  - liste : [a, "b", 3]  (utile avec IN / NOT IN) ;
#  - chemin de variable de contexte : trigger.data.role  ou  {trigger.data.role}
#    (indexation de liste supportée : mails[0].subject).
#
#Notes :
#  - un `primary` seul (sans comparaison) est évalué par sa valeur de vérité :
#    "trigger.data.debug"  ou  "flag AND autre_flag" sont valides ;
#  - comparaisons d'ordre (< > <= >=) : None de part et d'autre -> résultat faux (jamais d'erreur),
#    et si les deux membres sont numériques (nombre ou chaine numérique) ils sont comparés en float ;
#  - IN / NOT IN : test d'appartenance direct (`in`), sensible à la casse.

_STR_RE  = r'"[^"]*"|\'[^\']*\''
_NUM_RE  = r'-?\d+\.\d+|-?\d+'
_PATH_RE = r'[A-Za-z_][\w.\[\]]*'

#L'ordre des alternatives compte : multi-caractères et mots-clés avant les formes courtes / chemins.
_TOKEN_RE = re.compile(
    r'\s+'
    r'|(?P<lparen>\()'
    r'|(?P<rparen>\))'
    rf'|(?P<str>{_STR_RE})'
    r'|(?P<list>\[[^\]]*\])'
    rf'|(?P<num>{_NUM_RE})'
    r'|(?P<op><=|>=|==|!=|<>|<|>|=)'
    r'|(?P<kw>\b(?:AND|OR|NOT\s+IN|NOT|IN|TRUE|FALSE|NULL|NONE)\b)'
    r'|(?P<bvar>\{[\w.\[\]]+\})'
    rf'|(?P<path>{_PATH_RE})',
    re.IGNORECASE,
)

_ORD = {
    "<":  lambda a, b: a < b,
    ">":  lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    ">=": lambda a, b: a >= b,
}


class ConditionError(Exception):
    pass


#Évalue `expression` et renvoie un booléen. `resolver(path)` doit renvoyer la valeur typée d'une
#variable de contexte (ou lever / renvoyer selon la politique de l'appelant pour une variable absente).
def evaluate(expression:str, resolver)->bool:
    tokens = _tokenize(expression)
    parser = _Parser(tokens, resolver)
    value = parser.parse_or()
    parser.expect_end()
    return bool(value)


def _tokenize(expression:str):
    tokens = []
    pos = 0
    for m in _TOKEN_RE.finditer(expression):
        if m.start() != pos:
            raise ConditionError(f"caractère inattendu dans l'expression : {expression[pos:m.start()]!r}")
        pos = m.end()
        kind = m.lastgroup
        if kind is None:  #espaces
            continue
        text = m.group()
        if kind == "kw":
            text = re.sub(r'\s+', ' ', text).upper()
        tokens.append((kind, text))
    if pos != len(expression):
        raise ConditionError(f"caractère inattendu dans l'expression : {expression[pos:]!r}")
    return tokens


class _Parser:
    def __init__(self, tokens, resolver):
        self._tokens = tokens
        self._i = 0
        self._resolver = resolver

    def _peek(self):
        return self._tokens[self._i] if self._i < len(self._tokens) else (None, None)

    def _next(self):
        tok = self._peek()
        self._i += 1
        return tok

    def expect_end(self):
        if self._i != len(self._tokens):
            raise ConditionError(f"jeton inattendu : {self._peek()[1]!r}")

    # ------------------------------------------------------------------ grammaire
    def parse_or(self):
        value = self.parse_and()
        while self._peek() == ("kw", "OR"):
            self._next()
            right = self.parse_and()
            value = bool(value) or bool(right)
        return value

    def parse_and(self):
        value = self.parse_not()
        while self._peek() == ("kw", "AND"):
            self._next()
            right = self.parse_not()
            value = bool(value) and bool(right)
        return value

    def parse_not(self):
        if self._peek() == ("kw", "NOT"):
            self._next()
            return not bool(self.parse_not())
        return self.parse_comparison()

    def parse_comparison(self):
        left = self.parse_primary()
        kind, text = self._peek()
        if kind == "op" or (kind == "kw" and text in ("IN", "NOT IN")):
            self._next()
            right = self.parse_primary()
            return _compare(text, left, right)
        return left

    def parse_primary(self):
        kind, text = self._next()
        if kind == "lparen":
            value = self.parse_or()
            if self._peek()[0] != "rparen":
                raise ConditionError("parenthèse fermante ')' manquante")
            self._next()
            return value
        if kind is None:
            raise ConditionError("fin d'expression inattendue, opérande attendu")
        if kind == "rparen":
            raise ConditionError("parenthèse fermante ')' inattendue")
        if kind == "list":
            return _parse_list(text, self._resolver)
        if kind == "op" or (kind == "kw" and text in ("AND", "OR", "NOT", "IN", "NOT IN")):
            raise ConditionError(f"opérande attendu, trouvé l'opérateur {text!r}")
        return _scalar(text, self._resolver, kind)


# ------------------------------------------------------------------- opérandes
def _scalar(token:str, resolver, kind:str=None):
    if kind == "str" or (len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"')):
        return token[1:-1]
    low = token.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("none", "null"):
        return None
    if re.fullmatch(r'-?\d+', token):
        return int(token)
    if re.fullmatch(r'-?\d+\.\d+', token):
        return float(token)
    m = re.fullmatch(r'\{([\w.\[\]]+)\}', token)
    if m:
        return resolver(m.group(1))
    if re.fullmatch(_PATH_RE, token):
        return resolver(token)
    raise ConditionError(f"opérande invalide : {token!r}")


def _parse_list(raw:str, resolver):
    inner = raw[1:-1].strip()
    if not inner:
        return []
    return [_scalar(piece.strip(), resolver) for piece in _split_commas(inner)]


#Découpe sur les virgules de premier niveau en respectant les guillemets (pas d'imbrication de listes).
def _split_commas(text:str):
    parts, buf, quote = [], [], None
    for ch in text:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            buf.append(ch)
        elif ch == ",":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return parts


# ----------------------------------------------------------------- comparaison
def _compare(op:str, left, right):
    if op in ("=", "=="):
        return left == right
    if op in ("!=", "<>"):
        return left != right
    if op == "IN":
        return _membership(left, right, negate=False)
    if op == "NOT IN":
        return _membership(left, right, negate=True)

    #Opérateurs d'ordre : tolérants sur None, repli sur une comparaison numérique si les types diffèrent.
    if left is None or right is None:
        return False
    try:
        return bool(_ORD[op](left, right))
    except TypeError:
        ln, rn = _as_number(left), _as_number(right)
        if ln is None or rn is None:
            raise ConditionError(f"comparaison impossible : {left!r} {op} {right!r}")
        return bool(_ORD[op](ln, rn))


def _membership(left, right, negate:bool):
    try:
        contained = left in right
    except TypeError:
        raise ConditionError(f"l'opérande droit de IN n'est pas une collection : {right!r}")
    return (not contained) if negate else contained


def _as_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None
