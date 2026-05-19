from mcp.server.fastmcp import FastMCP
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from lib.config.config import Config
from lib.com.database import DataBase
from lib.mcp.crudtools import CrudTools
from lib.mcp.serviceloader import ServiceLoader

Config.init()
DataBase.connect()

app = FastMCP("mcp-test")

#CrudTools.register_crud_tools(app)
ServiceLoader.register_services(app)


if __name__ == "__main__":
    app.run()
