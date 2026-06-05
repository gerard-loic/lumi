import sys
import psycopg2
import psycopg2.extras
from psycopg2 import sql
from lib.config.config import Config
from lib.mcp.services import Service

class PostgreSQL(Service):
    def __init__(self, data:dict):
        service_format = {
            "host" : "str",
            "port" : "int",
            "database" : "str",
            "username" : "str",
            "password" : "str"
        }
        super().__init__(data=data, serviceDataFormat=service_format)
        self._connect()

    def _connect(self):
        try:
            self.cnx = psycopg2.connect(
                user=self.getConfValue(key="username"),
                password=self.getConfValue(key="password"),
                host=self.getConfValue(key="host"),
                port=self.getConfValue(key="port"),
                database=self.getConfValue(key="database")
            )

            self.db_cursor = self.cnx.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            self.db_cursor.execute("SELECT version();")
            record = self.db_cursor.fetchone()
            self.authenticated = True
            return True
        except Exception as e:
            return False


    def findRessourceId(self, entity:str, reference:str, attributes:list=["id:int","uid:str","name:str"]):
        int_cols = []
        str_cols = []
        for attribute in attributes:
            attribute_name, attribute_type = attribute.split(":")
            if attribute_type == "int" and reference.isdigit():
                int_cols.append(sql.Identifier(attribute_name))
            elif attribute_type == "str":
                str_cols.append(sql.Identifier(attribute_name))

        parts = [sql.SQL("SELECT id FROM {table}").format(table=sql.Identifier(entity))]
        params = []

        where_clauses = [sql.SQL("1=1")]
        for col in int_cols:
            where_clauses.append(sql.SQL("{col} = %s").format(col=col))
            params.append(reference)
        parts.append(sql.SQL(" WHERE ") + sql.SQL(" AND ").join(where_clauses))

        if str_cols:
            similarity_sum = sql.SQL(" + ").join(
                sql.SQL("similarity({col}, %s)").format(col=col) for col in str_cols
            )
            parts.append(sql.SQL(" ORDER BY ") + similarity_sum + sql.SQL(" DESC"))
            params.extend([reference] * len(str_cols))

        parts.append(sql.SQL(" LIMIT 1"))


        self.db_cursor.execute(sql.Composed(parts), params)
        record = self.db_cursor.fetchone()

        return record["id"] if record else None
