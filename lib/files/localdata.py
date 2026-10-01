import sqlite3
import os
from lib.config.config import Config


"""
LocalData — Gestion de la base de données locale (données rémanantes)
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class LocalData:
    @staticmethod
    def init():
        storage_dir = Config.get("directories.local_storage_dir")
        os.makedirs(storage_dir, exist_ok=True)
        LocalData.db_path = os.path.join(storage_dir, "local.db")
        cnx = LocalData._connect()
        try:
            with cnx:
                cnx.execute("CREATE TABLE IF NOT EXISTS llm_usage (created_at TIMESTAMP, session_uid VARCHAR(255), token_used INTEGER)")
        finally:
            cnx.close()


    #Ouvre une connexion dédiée au thread courant (SQLite interdit le partage entre threads)
    @staticmethod
    def _connect():
        cnx = sqlite3.connect(LocalData.db_path)
        cnx.row_factory = sqlite3.Row
        return cnx


    #Log une utilisation de tokens
    @staticmethod
    def logLLMUsage(session_uid: str, token_used: int):
        cnx = LocalData._connect()
        try:
            with cnx:
                cnx.execute(
                    "INSERT INTO llm_usage (created_at, session_uid, token_used) VALUES (datetime('now'), ?, ?)",
                    (session_uid, token_used)
                )
        finally:
            cnx.close()


    #Retourne des données de consommation
    @staticmethod
    def getLLMUsage(currentMonth: bool = True):
        cnx = LocalData._connect()
        try:
            if currentMonth:
                cursor = cnx.execute(
                    "SELECT strftime('%Y', created_at) AS year, strftime('%m', created_at) AS month, SUM(token_used) AS token_used, "
                    "SUM(CASE WHEN token_used = 0 THEN 1 ELSE 0 END) AS request_count "
                    "FROM llm_usage "
                    "WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now') "
                    "GROUP BY year, month"
                )
            else:
                cursor = cnx.execute(
                    "SELECT strftime('%Y', created_at) AS year, strftime('%m', created_at) AS month, SUM(token_used) AS token_used, "
                    "SUM(CASE WHEN token_used = 0 THEN 1 ELSE 0 END) AS request_count "
                    "FROM llm_usage "
                    "GROUP BY year, month "
                    "ORDER BY year, month"
                )
            rows = [dict(r) for r in cursor.fetchall()]
        finally:
            cnx.close()
        if not rows:
            from datetime import datetime
            now = datetime.now()
            rows = [{"year": str(now.year), "month": f"{now.month:02d}", "token_used": 0, "request_count": 0}]
        return rows
