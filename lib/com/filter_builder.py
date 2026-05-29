class FilterBuilder:
    """Converts a list of filter dicts to the API filter string syntax.

    Each condition dict:
        field   (str)              : attribute name
        op      (str)              : operator — eq, neq, gt, lt, gte, lte,
                                     lk, nlk, ilk, nilk, in, nin,
                                     btw, nbtw, ist, isf
        value   (str|int|float|list): operand(s); omit for ist/isf;
                                     list for in/nin/btw/nbtw
        logic   ("and"|"or")       : how this item joins the PREVIOUS one
                                     (ignored on the first item, default "and")

    To AND/OR a parenthesised group, use a group item instead of field/op:
        {"logic": "and", "group": [...conditions]}

    Example:
        [
            {"field": "status", "op": "eq",  "value": "active"},
            {"field": "amount", "op": "gte", "value": 100, "logic": "and"},
            {"logic": "or", "group": [
                {"field": "type", "op": "in", "value": ["invoice", "credit"]},
            ]},
        ]
        → "status:eq(active)|n|amount:gte(100)|u|[type:in(invoice,credit)]"
    """

    _LOGIC = {"and": "|n|", "or": "|u|"}

    @classmethod
    def build(cls, filters: list[dict]) -> str:
        if not filters:
            return ""
        parts: list[str] = []
        for i, item in enumerate(filters):
            logic = item.get("logic", "and")
            sep = cls._LOGIC.get(logic, "|n|")
            segment = (
                f"[{cls.build(item['group'])}]"
                if "group" in item
                else cls._condition(item)
            )
            parts.append(segment if i == 0 else sep + segment)
        return "".join(parts)

    @classmethod
    def _condition(cls, item: dict) -> str:
        field = item["field"]
        op = item["op"]
        value = item.get("value")

        if op in ("ist", "isf"):
            return f"{field}:{op}()"
        if op in ("in", "nin"):
            v = ",".join(str(x) for x in value) if isinstance(value, list) else str(value)
            return f"{field}:{op}({v})"
        if op in ("btw", "nbtw"):
            if isinstance(value, list) and len(value) == 2:
                return f"{field}:{op}({value[0]},{value[1]})"
            return f"{field}:{op}({value})"
        if op in ("ilk", "nilk"):
            v = str(value).strip("%")
            return f"{field}:{op}(%{v}%)"
        return f"{field}:{op}({value})"
