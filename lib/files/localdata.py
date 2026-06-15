import sqlite3
import os
from lib.config.config import Config

class LocalData:
    @staticmethod
    def init():
        storage_dir = Config.get("files.local_storage_dir")
        os.makedirs(storage_dir, exist_ok=True)
        LocalData.cnx = sqlite3.connect(os.path.join(storage_dir, "local.db"))
        LocalData.cnx.row_factory = sqlite3.Row
        LocalData.cursor = LocalData.cnx.cursor()
        LocalData.cursor.execute("CREATE TABLE IF NOT EXISTS llm_usage (created_at TIMESTAMP, session_uid VARCHAR(255), token_used INTEGER)")

    @staticmethod
    def logLLMUsage(session_uid: str, token_used: int):
        LocalData.cursor.execute(
            "INSERT INTO llm_usage (created_at, session_uid, token_used) VALUES (datetime('now'), ?, ?)",
            (session_uid, token_used)
        )
        LocalData.cnx.commit()


    @staticmethod
    def getLLMUsage(currentMonth: bool = True):
        if currentMonth:
            LocalData.cursor.execute(
                "SELECT strftime('%Y', created_at) AS year, strftime('%m', created_at) AS month, SUM(token_used) AS token_used, "
                "SUM(CASE WHEN token_used = 0 THEN 1 ELSE 0 END) AS request_count "
                "FROM llm_usage "
                "WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now') "
                "GROUP BY year, month"
            )
        else:
            LocalData.cursor.execute(
                "SELECT strftime('%Y', created_at) AS year, strftime('%m', created_at) AS month, SUM(token_used) AS token_used, "
                "SUM(CASE WHEN token_used = 0 THEN 1 ELSE 0 END) AS request_count "
                "FROM llm_usage "
                "GROUP BY year, month "
                "ORDER BY year, month"
            )
        rows = [dict(r) for r in LocalData.cursor.fetchall()]
        if not rows:
            from datetime import datetime
            now = datetime.now()
            rows = [{"year": str(now.year), "month": f"{now.month:02d}", "token_used": 0, "request_count": 0}]
        return rows
