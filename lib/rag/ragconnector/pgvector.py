import asyncio
import json
import psycopg2
import psycopg2.extras
from psycopg2 import sql
from pgvector.psycopg2 import register_vector
from lib.config.config import Config
from lib.rag.collection import RagCollection

"""
PgVector : service de RAG PostreSQL PgVector
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class PgVector:
    #Connexion standard à la BDD
    @staticmethod
    def _connect_raw():
        cfg = Config.get("services")["bdd"]
        return psycopg2.connect(
            host=cfg["host"],
            port=cfg["port"],
            database=cfg["database"],
            user=cfg["username"],
            password=cfg["password"],
        )

    #Connexion en vectoriel à la BDD
    @staticmethod
    def _connect():
        conn = PgVector._connect_raw()
        register_vector(conn)
        return conn

    #Table de la collection (rag.collections.<collection>.pgvector.table). Plusieurs collections peuvent partager
    #une table si elles ont la même dimension d'embedding (la colonne `collection` les distingue)
    @staticmethod
    def _tableName(collection: str) -> str:
        return RagCollection.get(collection)["pgvector"]["table"]

    @staticmethod
    def _table(collection: str) -> sql.Identifier:
        return sql.Identifier(PgVector._tableName(collection))

    #S'assurer que les prérequis de la collection soient présents
    @staticmethod
    async def ensureTable(collection: str) -> None:
        dim = int(RagCollection.get(collection)["embedding_dim"])

        def _run():
            table_name = PgVector._tableName(collection)
            table    = sql.Identifier(table_name)
            hnsw_idx = sql.Identifier(f"{table_name}_hnsw_idx")
            coll_idx = sql.Identifier(f"{table_name}_collection_idx")

            conn = PgVector._connect_raw()
            try:
                with conn.cursor() as cur:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                    cur.execute(sql.SQL("""
                        CREATE TABLE IF NOT EXISTS {} (
                            id         SERIAL PRIMARY KEY,
                            collection TEXT    NOT NULL,
                            content    TEXT    NOT NULL,
                            metadata   JSONB   DEFAULT '{{}}',
                            embedding  VECTOR({})
                        )
                    """).format(table, sql.SQL(str(dim))))
                    cur.execute(sql.SQL("""
                        CREATE INDEX IF NOT EXISTS {}
                        ON {}
                        USING hnsw (embedding vector_cosine_ops)
                    """).format(hnsw_idx, table))
                    cur.execute(sql.SQL("""
                        CREATE INDEX IF NOT EXISTS {}
                        ON {} (collection)
                    """).format(coll_idx, table))
                    conn.commit()
            finally:
                conn.close()

        await asyncio.to_thread(_run)

    #Ajout
    @staticmethod
    async def insert(collection: str, content: str, metadata: dict, embedding: list[float]) -> None:
        def _run():
            conn = PgVector._connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        sql.SQL(
                            "INSERT INTO {} (collection, content, metadata, embedding)"
                            " VALUES (%s, %s, %s, %s)"
                        ).format(PgVector._table(collection)),
                        (collection, content, json.dumps(metadata), embedding),
                    )
                    conn.commit()
            finally:
                conn.close()

        await asyncio.to_thread(_run)

    #Recherche
    @staticmethod
    async def search(collection: str, embedding: list[float], top_k: int) -> list[dict]:
        def _run():
            conn = PgVector._connect()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        sql.SQL("""
                            SELECT content, metadata, 1 - (embedding <=> %s::vector) AS score
                            FROM {}
                            WHERE collection = %s
                            ORDER BY embedding <=> %s::vector
                            LIMIT %s
                        """).format(PgVector._table(collection)),
                        (embedding, collection, embedding, top_k),
                    )
                    rows = cur.fetchall()
                return [
                    {
                        "content":  r["content"],
                        "metadata": dict(r["metadata"]) if r["metadata"] else {},
                        "score":    float(r["score"]),
                    }
                    for r in rows
                ]
            finally:
                conn.close()

        return await asyncio.to_thread(_run)

    #Statistiques d'une collection : nombre de chunks (0 si la table n'existe pas encore)
    @staticmethod
    async def stats(collection: str) -> int:
        def _run():
            conn = PgVector._connect_raw()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT to_regclass(%s)", (f'"{PgVector._tableName(collection)}"',))
                    if cur.fetchone()[0] is None:
                        return 0
                    cur.execute(
                        sql.SQL("SELECT COUNT(*) FROM {} WHERE collection = %s").format(PgVector._table(collection)),
                        (collection,),
                    )
                    return cur.fetchone()[0]
            finally:
                conn.close()

        return await asyncio.to_thread(_run)

    #Retourne si un document existe
    @staticmethod
    async def sourceExists(collection: str, source: str) -> bool:
        def _run():
            conn = PgVector._connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        sql.SQL(
                            "SELECT 1 FROM {} WHERE collection = %s AND metadata->>'source' = %s LIMIT 1"
                        ).format(PgVector._table(collection)),
                        (collection, source),
                    )
                    return cur.fetchone() is not None
            finally:
                conn.close()

        return await asyncio.to_thread(_run)

    #Retourne les métadonnées d'un document indexé
    @staticmethod
    async def sourceMetadata(collection: str, source: str) -> dict | None:
        def _run():
            conn = PgVector._connect()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        sql.SQL(
                            "SELECT metadata FROM {} WHERE collection = %s AND metadata->>'source' = %s LIMIT 1"
                        ).format(PgVector._table(collection)),
                        (collection, source),
                    )
                    row = cur.fetchone()
                    if row is None:
                        return None
                    return dict(row["metadata"]) if row["metadata"] else {}
            finally:
                conn.close()

        return await asyncio.to_thread(_run)

    #Supprimer un document
    @staticmethod
    async def deleteBySource(collection: str, source: str) -> int:
        def _run():
            conn = PgVector._connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        sql.SQL(
                            "DELETE FROM {} WHERE collection = %s AND metadata->>'source' = %s"
                        ).format(PgVector._table(collection)),
                        (collection, source),
                    )
                    count = cur.rowcount
                    conn.commit()
                return count
            finally:
                conn.close()

        return await asyncio.to_thread(_run)

    #Supprimer une collection
    @staticmethod
    async def deleteCollection(collection: str) -> int:
        def _run():
            conn = PgVector._connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        sql.SQL(
                            "DELETE FROM {} WHERE collection = %s"
                        ).format(PgVector._table(collection)),
                        (collection,),
                    )
                    count = cur.rowcount
                    conn.commit()
                return count
            finally:
                conn.close()

        return await asyncio.to_thread(_run)
