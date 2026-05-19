import os
import inspect
import importlib.util
from mcp.server.fastmcp import FastMCP


class ServiceLoader:

    @staticmethod
    def register_services(app: FastMCP, services_dir: str = None):
        if services_dir is None:
            services_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "services"
            )

        for filename in sorted(os.listdir(services_dir)):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            module_name = f"services.{filename[:-3]}"
            filepath = os.path.join(services_dir, filename)

            spec = importlib.util.spec_from_file_location(module_name, filepath)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            for fn_name, fn in inspect.getmembers(module, inspect.isfunction):
                if fn_name.startswith("_") or fn.__module__ != module_name:
                    continue
                app.tool()(fn)
