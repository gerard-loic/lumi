import asyncio
import json
import psycopg2
import psycopg2.extras
from psycopg2 import sql
from pgvector.psycopg2 import register_vector
from lib.config.config import Config

"""
PgVector : service de RAG PostreSQL PgVector
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class PgVector:
    @staticmethod
    def _connect():
        cfg = Config.get("services")["bdd"]
        conn = psycopg2.connect(
            host=cfg["host"],
            port=cfg["port"],
            database=cfg["database"],
            user=cfg["username"],
            password=cfg["password"],
        )
        register_vector(conn)
        return conn

    @staticmethod
    def _table() -> sql.Identifier:
        return sql.Identifier(Config.get("rag.pgvector.table"))

    @staticmethod
    async def ensureTable() -> None:
        dim = int(Config.get("rag.embedding_dim"))

        def _run():
            table_name = Config.get("rag.pgvector.table")
            table    = sql.Identifier(table_name)
            hnsw_idx = sql.Identifier(f"{table_name}_hnsw_idx")
            coll_idx = sql.Identifier(f"{table_name}_collection_idx")

            conn = PgVector._connect()
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
                        ).format(PgVector._table()),
                        (collection, content, json.dumps(metadata), embedding),
                    )
                    conn.commit()
            finally:
                conn.close()

        await asyncio.to_thread(_run)

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
                        """).format(PgVector._table()),
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

    @staticmethod
    async def stats() -> dict:
        def _run():
            conn = PgVector._connect()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        sql.SQL("""
                            SELECT collection, COUNT(*) AS chunks
                            FROM {}
                            GROUP BY collection
                            ORDER BY collection
                        """).format(PgVector._table())
                    )
                    rows = cur.fetchall()
                collections = [{"name": r["collection"], "chunks": r["chunks"]} for r in rows]
                total = sum(c["chunks"] for c in collections)
                return {"total_chunks": total, "collections": collections}
            finally:
                conn.close()

        return await asyncio.to_thread(_run)

    @staticmethod
    async def sourceExists(collection: str, source: str) -> bool:
        def _run():
            conn = PgVector._connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        sql.SQL(
                            "SELECT 1 FROM {} WHERE collection = %s AND metadata->>'source' = %s LIMIT 1"
                        ).format(PgVector._table()),
                        (collection, source),
                    )
                    return cur.fetchone() is not None
            finally:
                conn.close()

        return await asyncio.to_thread(_run)

    @staticmethod
    async def deleteBySource(collection: str, source: str) -> int:
        def _run():
            conn = PgVector._connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        sql.SQL(
                            "DELETE FROM {} WHERE collection = %s AND metadata->>'source' = %s"
                        ).format(PgVector._table()),
                        (collection, source),
                    )
                    count = cur.rowcount
                    conn.commit()
                return count
            finally:
                conn.close()

        return await asyncio.to_thread(_run)

    @staticmethod
    async def deleteCollection(collection: str) -> int:
        def _run():
            conn = PgVector._connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        sql.SQL(
                            "DELETE FROM {} WHERE collection = %s"
                        ).format(PgVector._table()),
                        (collection,),
                    )
                    count = cur.rowcount
                    conn.commit()
                return count
            finally:
                conn.close()

        return await asyncio.to_thread(_run)
