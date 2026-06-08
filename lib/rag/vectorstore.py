import asyncio
import json
import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector
from lib.config.config import Config


class VectorStore:
    TABLE = "rag_documents"

    @staticmethod
    def _new_conn():
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
    async def ensure_table() -> None:
        dim = Config.get("RAG_EMBEDDING_DIM")

        def _run():
            conn = VectorStore._new_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS {VectorStore.TABLE} (
                            id         SERIAL PRIMARY KEY,
                            collection TEXT    NOT NULL,
                            content    TEXT    NOT NULL,
                            metadata   JSONB   DEFAULT '{{}}',
                            embedding  VECTOR({dim})
                        )
                    """)
                    cur.execute(f"""
                        CREATE INDEX IF NOT EXISTS {VectorStore.TABLE}_hnsw_idx
                        ON {VectorStore.TABLE}
                        USING hnsw (embedding vector_cosine_ops)
                    """)
                    cur.execute(f"""
                        CREATE INDEX IF NOT EXISTS {VectorStore.TABLE}_collection_idx
                        ON {VectorStore.TABLE} (collection)
                    """)
                    conn.commit()
            finally:
                conn.close()

        await asyncio.to_thread(_run)

    @staticmethod
    async def insert(collection: str, content: str, metadata: dict, embedding: list[float]) -> None:
        def _run():
            conn = VectorStore._new_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        f"INSERT INTO {VectorStore.TABLE} (collection, content, metadata, embedding)"
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
            conn = VectorStore._new_conn()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        f"""SELECT content, metadata, 1 - (embedding <=> %s::vector) AS score
                            FROM {VectorStore.TABLE}
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
    async def delete_collection(collection: str) -> int:
        def _run():
            conn = VectorStore._new_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        f"DELETE FROM {VectorStore.TABLE} WHERE collection = %s",
                        (collection,),
                    )
                    count = cur.rowcount
                    conn.commit()
                return count
            finally:
                conn.close()

        return await asyncio.to_thread(_run)
