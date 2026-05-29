import os
import json
import httpx
from mcp.server.fastmcp import FastMCP
from lib.config.config import Config
from lib.com.database import DataBase
from lib.com.filter_builder import FilterBuilder
import sys

class CrudTools:

    #Enregistre dynamiquement les outils MCP pour toutes les ressources CRUD configurées.
    @staticmethod
    def register_crud_tools(app:FastMCP):
        for resource_name, cfg in Config.get(type="crud").items():
            print(f"RESSOURCE {resource_name}", file=sys.stderr, flush=True)
            endpoint = cfg.get("endpoint", resource_name)
            name = cfg.get("name", resource_name)
            entity = cfg.get("entity", resource_name)

            for op in cfg.get("methods", []):
                description = Config.get(key=f"MCP_CRUD_DEFAULT_{op.upper()}", type="env").format(resource=name)

                if op == "show":
                    fn = CrudTools._make_show_tool(resource_name, endpoint, entity, description)
                elif op == "list":
                    fn = CrudTools._make_list_tool(resource_name, endpoint, description)
                else:
                    raise Exception(f"CRUD type {op} not allowed")
                app.tool()(fn)

    #------------------------------------------------------------------------------------

    _FILTER_DOC = (
        "\n\nFilters: list of condition objects. "
        "Each condition: {field, op, value, logic?}. "
        "op values: eq, neq, gt, lt, gte, lte, lk, nlk, ilk, nilk, in, nin, btw, nbtw, ist, isf. "
        "logic: 'and' (default) or 'or' — joins this condition to the previous one. "
        "For a parenthesised group use {group: [...conditions], logic?} instead of field/op. "
        "value is a list for in/nin (e.g. [1,2,3]) and btw/nbtw (e.g. [10,20]); omit for ist/isf. "
        "Example: [{\"field\":\"status\",\"op\":\"eq\",\"value\":\"active\"},"
        "{\"field\":\"amount\",\"op\":\"gte\",\"value\":100,\"logic\":\"and\"}]"
    )

    @staticmethod
    def _make_list_tool(resource_name: str, endpoint: str, description: str):
        async def fn(
            bearer_token: str,
            page: int = 1,
            limit: int = 12,
            filters: list[dict] | None = None,
            sort: str = "",
        ) -> dict:
            params: dict = {"page": page, "limit": limit}
            if filters:
                params["filters"] = FilterBuilder.build(filters)
            if sort:
                params["sort"] = sort
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"{Config.get(key='APP_URL', type='env')}/api/{endpoint}",
                    headers=CrudTools._get_headers(bearer_token),
                    params=params,
                )
                r.raise_for_status()
                return r.json()

        fn.__name__ = f"list_{resource_name}"
        fn.__doc__ = description + CrudTools._FILTER_DOC
        return fn

    @staticmethod
    def _make_show_tool(resource_name: str, endpoint: str, entity:str, description: str):
        async def fn(reference: str, bearer_token: str) -> dict:
            id = DataBase.findRessourceId(entity=entity, reference=reference)
            print(f"ID : {id}", file=sys.stderr, flush=True)
            #@TODO : si rien n'est trouvé

            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"{Config.get(key='APP_URL', type='env')}/api/{endpoint}/{id}",
                    headers=CrudTools._get_headers(bearer_token),
                )
                r.raise_for_status()
                return r.json()

        fn.__name__ = f"show_{resource_name}"
        fn.__doc__ = description
        return fn

    @staticmethod
    def _get_headers(bearer_token: str) -> dict:
        return {"Authorization": f"Bearer {bearer_token}", "Accept": "application/json"}




