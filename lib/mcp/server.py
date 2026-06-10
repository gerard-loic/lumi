from mcp.server.fastmcp import FastMCP
from lib.config.config import Config
from lib.mcp.tools import ToolLoader


def create_app() -> FastMCP:
    app = FastMCP(Config.get(key="app.name"))
    ToolLoader.registerTools(app=app)
    return app
