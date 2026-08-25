
import re

class PipelineContext:
    #Détecte "{% for var in path %}", "{% endfor %}", "{% if cond %}", "{% elif cond %}",
    #"{% else %}", "{% endif %}", ou une variable "{path}"
    _TOKEN_RE = re.compile(
        r'\{%\s*for\s+(?P<for_var>\w+)\s+in\s+(?P<for_iter>[\w\.\[\]]+)\s*%\}'
        r'|\{%\s*endfor\s*%\}'
        r'|\{%\s*if\s+(?P<if_expr>.+?)\s*%\}'
        r'|\{%\s*elif\s+(?P<elif_expr>.+?)\s*%\}'
        r'|\{%\s*else\s*%\}'
        r'|\{%\s*endif\s*%\}'
        r'|\{(?P<var>[\w\.\[\]]+)\}'
    )
    _PATH_TOKEN_RE = re.compile(r'^(\w+)((?:\[\d+\])*)$')
    #Opérateurs supportés dans les conditionnelles : == != >= <= > < IN NOT IN
    _COND_RE = re.compile(
        r'^(?P<left>.+?)\s*(?P<op>==|!=|>=|<=|\bNOT\s+IN\b|\bIN\b|>|<)\s*(?P<right>.+)$',
        re.IGNORECASE
    )

    def __init__(self):
        self._data = {}

    def set(self, key:str, value):
        self._data[key] = value

    def get(self, key:str):
        data = self._data[key]
        if isinstance(data, (str)):
            data = self.transform(text=data)
        return data

    #Fusionne un dict de valeurs dans le contexte, en transformant au passage les chaines
    #(et les chaines imbriquées dans des dict/list) pour permettre de référencer des valeurs
    #déjà présentes dans le contexte
    def merge(self, values:dict):
        for key, value in values.items():
            self.set(key, self._transformValue(value))


    def transform(self, text:str)->str:
        tokens = self._tokenize(text)
        nodes, _, stop = self._parse(tokens, 0)
        if stop is not None:
            raise ValueError(f"Balise {{% {stop[0]} %}} sans bloc correspondant dans le template")
        return self._renderNodes(nodes, self._data)

    def _transformValue(self, value):
        if isinstance(value, str):
            return self.transform(value)
        if isinstance(value, dict):
            return {k: self._transformValue(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._transformValue(v) for v in value]
        return value

    def _tokenize(self, text:str)->list:
        tokens = []
        pos = 0
        for m in self._TOKEN_RE.finditer(text):
            if m.start() > pos:
                tokens.append(("text", text[pos:m.start()]))
            if m.group("for_var") is not None:
                tokens.append(("for", m.group("for_var"), m.group("for_iter")))
            elif m.group("if_expr") is not None:
                tokens.append(("if", m.group("if_expr")))
            elif m.group("elif_expr") is not None:
                tokens.append(("elif", m.group("elif_expr")))
            elif m.group("var") is not None:
                tokens.append(("var", m.group("var")))
            elif re.search(r'\bendfor\b', m.group(0)):
                tokens.append(("endfor",))
            elif re.search(r'\belse\b', m.group(0)):
                tokens.append(("else",))
            else:
                tokens.append(("endif",))
            pos = m.end()
        if pos < len(text):
            tokens.append(("text", text[pos:]))
        return tokens

    #Parcourt les tokens et construit l'arbre de noeuds, en s'arrêtant sur une balise de
    #fermeture/enchainement ("endfor", "elif", "else", "endif"). Renvoie (nodes, index, stop_token)
    #où stop_token est la balise ayant provoqué l'arrêt (None si fin des tokens atteinte)
    def _parse(self, tokens:list, index:int):
        nodes = []
        while index < len(tokens):
            token = tokens[index]
            if token[0] in ("endfor", "elif", "else", "endif"):
                return nodes, index + 1, token
            if token[0] == "for":
                _, loop_var, iter_path = token
                body_nodes, index, stop = self._parse(tokens, index + 1)
                if stop is None or stop[0] != "endfor":
                    raise ValueError("Balise {% for %} sans {% endfor %} correspondant")
                nodes.append(("for", loop_var, iter_path, body_nodes))
                continue
            if token[0] == "if":
                branches = []
                cond = token[1]
                index += 1
                while True:
                    body_nodes, index, stop = self._parse(tokens, index)
                    branches.append((cond, body_nodes))
                    if stop is None:
                        raise ValueError("Balise {% if %} sans {% endif %} correspondant")
                    if stop[0] == "endif":
                        break
                    if stop[0] == "elif":
                        cond = stop[1]
                        continue
                    if stop[0] == "else":
                        cond = None
                        continue
                nodes.append(("if", branches))
                continue
            nodes.append(token)
            index += 1
        return nodes, index, None

    def _renderNodes(self, nodes:list, scope:dict)->str:
        parts = []
        for node in nodes:
            if node[0] == "text":
                parts.append(node[1])
            elif node[0] == "var":
                parts.append(str(self._resolvePath(node[1], scope)))
            elif node[0] == "if":
                for cond, body_nodes in node[1]:
                    if cond is None or self._evalCondition(cond, scope):
                        parts.append(self._renderNodes(body_nodes, scope))
                        break
            else:
                _, loop_var, iter_path, body_nodes = node
                for item in self._resolvePath(iter_path, scope) or []:
                    item_scope = dict(scope)
                    item_scope[loop_var] = item
                    parts.append(self._renderNodes(body_nodes, item_scope))
        return "".join(parts)

    def _resolvePath(self, path:str, scope:dict):
        value = None
        for i, token in enumerate(path.split(".")):
            m = self._PATH_TOKEN_RE.match(token)
            if not m:
                raise ValueError(f"Expression invalide dans le template : {token}")
            name, indexes = m.group(1), m.group(2)
            value = scope[name] if i == 0 else self._getAttr(value, name)
            for idx in re.findall(r'\[(\d+)\]', indexes):
                value = value[int(idx)]
        return value

    def _evalCondition(self, expr:str, scope:dict)->bool:
        m = self._COND_RE.match(expr.strip())
        if not m:
            raise ValueError(f"Condition invalide dans le template : {expr}")
        left = self._evalOperand(m.group("left"), scope)
        op = re.sub(r'\s+', ' ', m.group("op").strip()).upper()
        right = self._evalOperand(m.group("right"), scope)
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op == ">=":
            return left >= right
        if op == "<=":
            return left <= right
        if op == ">":
            return left > right
        if op == "<":
            return left < right
        if op == "IN":
            return left in right
        if op == "NOT IN":
            return left not in right
        raise ValueError(f"Opérateur non supporté dans le template : {op}")

    #Résout un opérande de condition : littéral (nombre, chaine, booléen, liste) ou chemin de variable
    def _evalOperand(self, token:str, scope:dict):
        token = token.strip()
        if len(token) >= 2 and token[0] == token[-1] and token[0] in ('"', "'"):
            return token[1:-1]
        if token.startswith('[') and token.endswith(']'):
            items = [t.strip() for t in token[1:-1].split(',') if t.strip() != '']
            return [self._evalOperand(t, scope) for t in items]
        if re.fullmatch(r'-?\d+', token):
            return int(token)
        if re.fullmatch(r'-?\d+\.\d+', token):
            return float(token)
        if token.lower() in ("true", "false"):
            return token.lower() == "true"
        if token.lower() in ("none", "null"):
            return None
        return self._resolvePath(token, scope)

    @staticmethod
    def _getAttr(obj, name:str):
        if isinstance(obj, dict):
            return obj[name]
        return getattr(obj, name)
