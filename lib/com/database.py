import sys
import psycopg2
import psycopg2.extras
from psycopg2 import sql
from lib.config.config import Config

class DataBase:
    @staticmethod
    def connect():
        print("Connection to PostgreSQL : "+Config.get(type="env", key="DB_HOST"), file=sys.stderr)
        DataBase.cnx = psycopg2.connect(
            user=Config.get(type="env", key="DB_USERNAME"),
            password=Config.get(type="env", key="DB_PASSWORD"),
            host=Config.get(type="env", key="DB_HOST"),
            port=Config.get(type="env", key="DB_PORT"),
            database=Config.get(type="env", key="DB_DATABASE")
        )

        DataBase.db_cursor = DataBase.cnx.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        print(str(DataBase.cnx.get_dsn_parameters()), file=sys.stderr)
        DataBase.db_cursor.execute("SELECT version();")
        record = DataBase.db_cursor.fetchone()
        print("You are connected to : ", file=sys.stderr)
        print(str(record), file=sys.stderr)

    @staticmethod
    def findRessourceId(entity:str, reference:str, attributes:list=["id:int","uid:str","name:str"]):
        print(f"FIND RESSOURCE {reference}", file=sys.stderr, flush=True)
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

        print(sql.Composed(parts), file=sys.stderr, flush=True)

        DataBase.db_cursor.execute(sql.Composed(parts), params)
        record = DataBase.db_cursor.fetchone()
        print(record, file=sys.stderr, flush=True)

        return record["id"] if record else None
