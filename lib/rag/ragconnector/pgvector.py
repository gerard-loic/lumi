import asyncio
import json
import psycopg2
import psycopg2.extras
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
    async def ensureTable() -> None:
        dim = Config.get("RAG_EMBEDDING_DIM")

        def _run():
            conn = PgVector._connect()
            try:
                with conn.cursor() as cur:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS {Config.get("RAG_PGVECTOR_TABLE")} (
                            id         SERIAL PRIMARY KEY,
                            collection TEXT    NOT NULL,
                            content    TEXT    NOT NULL,
                            metadata   JSONB   DEFAULT '{{}}',
                            embedding  VECTOR({dim})
                        )
                    """)
                    cur.execute(f"""
                        CREATE INDEX IF NOT EXISTS {Config.get("RAG_PGVECTOR_TABLE")}_hnsw_idx
                        ON {Config.get("RAG_PGVECTOR_TABLE")}
                        USING hnsw (embedding vector_cosine_ops)
                    """)
                    cur.execute(f"""
                        CREATE INDEX IF NOT EXISTS {Config.get("RAG_PGVECTOR_TABLE")}_collection_idx
                        ON {Config.get("RAG_PGVECTOR_TABLE")} (collection)
                    """)
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
                        f"INSERT INTO {Config.get("RAG_PGVECTOR_TABLE")} (collection, content, metadata, embedding)"
                        " VALUES (%s, %s, %s, %s)",
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
                        f"""SELECT content, metadata, 1 - (embedding <=> %s::vector) AS score
                            FROM {Config.get("RAG_PGVECTOR_TABLE")}
                            WHERE collection = %s
                            ORDER BY embedding <=> %s::vector
                            LIMIT %s""",
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
                    cur.execute(f"""
                        SELECT collection, COUNT(*) AS chunks
                        FROM {Config.get("RAG_PGVECTOR_TABLE")}
                        GROUP BY collection
                        ORDER BY collection
                    """)
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
                        f"SELECT 1 FROM {Config.get("RAG_PGVECTOR_TABLE")} WHERE collection = %s AND metadata->>'source' = %s LIMIT 1",
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
                        f"DELETE FROM {Config.get("RAG_PGVECTOR_TABLE")} WHERE collection = %s AND metadata->>'source' = %s",
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
                        f"DELETE FROM {Config.get("RAG_PGVECTOR_TABLE")} WHERE collection = %s",
                        (collection,),
                    )
                    count = cur.rowcount
                    conn.commit()
                return count
            finally:
                conn.close()

        return await asyncio.to_thread(_run)
