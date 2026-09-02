import sqlite3
import os
import uuid
from lib.config.config import Config


"""
PipelineLog — Gestion de la base de données locale de logs pour les pipelines (données rémanantes)
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class PipelineLog:
    @staticmethod
    def init():
        storage_dir = Config.get("directories.local_storage_dir")
        os.makedirs(storage_dir, exist_ok=True)
        PipelineLog.db_path = os.path.join(storage_dir, "pipelines_logs.db")
        cnx = PipelineLog._connect()
        try:
            with cnx:
                cnx.execute("CREATE TABLE IF NOT EXISTS pipeline_process (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TIMESTAMP, started_at TIMESTAMP, ended_at TIMESTAMP, process_uid VARCHAR(255), pipeline_uid VARCHAR(255), is_success BOOLEAN)")
                cnx.execute("CREATE TABLE IF NOT EXISTS pipeline_block (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TIMESTAMP, pipeline_process_id INTEGER, name VARCHAR(255), logs TEXT, is_success BOOLEAN)")
        finally:
            cnx.close()


    #Ouvre une connexion dédiée au thread courant (SQLite interdit le partage entre threads)
    @staticmethod
    def _connect():
        cnx = sqlite3.connect(PipelineLog.db_path)
        cnx.row_factory = sqlite3.Row
        return cnx

    
    #Crée une ligne dans pipeline_process et retourne son id
    @staticmethod
    def createProcess(pipeline_uid: str, process_uid: str = None) -> int:
        if process_uid is None:
            process_uid = str(uuid.uuid4())
        cnx = PipelineLog._connect()
        try:
            with cnx:
                cursor = cnx.execute(
                    "INSERT INTO pipeline_process (created_at, started_at, process_uid, pipeline_uid) VALUES (datetime('now'), datetime('now'), ?, ?)",
                    (process_uid, pipeline_uid)
                )
            return cursor.lastrowid
        finally:
            cnx.close()


    #Crée une ligne dans pipeline_block et retourne son id
    @staticmethod
    def createBlock(pipeline_process_id: int, name: str, logs: str = None, is_success: bool = None) -> int:
        cnx = PipelineLog._connect()
        try:
            with cnx:
                cursor = cnx.execute(
                    "INSERT INTO pipeline_block (created_at, pipeline_process_id, name, logs, is_success) VALUES (datetime('now'), ?, ?, ?, ?)",
                    (pipeline_process_id, name, logs, is_success)
                )
            return cursor.lastrowid
        finally:
            cnx.close()


    #Met à jour is_success et / ou started_at / ended_at d'une ligne de pipeline_process
    @staticmethod
    def updateProcess(process_id: int, is_success: bool = None, started_at: str = None, ended_at: str = None):
        fields = []
        params = []
        if is_success is not None:
            fields.append("is_success = ?")
            params.append(is_success)
        if started_at is not None:
            fields.append("started_at = ?")
            params.append(started_at)
        if ended_at is not None:
            fields.append("ended_at = ?")
            params.append(ended_at)
        if not fields:
            return
        params.append(process_id)
        cnx = PipelineLog._connect()
        try:
            with cnx:
                cnx.execute(
                    f"UPDATE pipeline_process SET {', '.join(fields)} WHERE id = ?",
                    params
                )
        finally:
            cnx.close()


    #Met à jour is_success et / ou logs d'une ligne de pipeline_block
    @staticmethod
    def updateBlock(block_id: int, is_success: bool = None, logs: str = None):
        fields = []
        params = []
        if is_success is not None:
            fields.append("is_success = ?")
            params.append(is_success)
        if logs is not None:
            fields.append("logs = ?")
            params.append(logs)
        if not fields:
            return
        params.append(block_id)
        cnx = PipelineLog._connect()
        try:
            with cnx:
                cnx.execute(
                    f"UPDATE pipeline_block SET {', '.join(fields)} WHERE id = ?",
                    params
                )
        finally:
            cnx.close()


    #Récupère une ligne de pipeline_process à partir de son process_uid (None si absente)
    @staticmethod
    def getProcess(process_uid: str) -> sqlite3.Row:
        cnx = PipelineLog._connect()
        try:
            return cnx.execute(
                "SELECT * FROM pipeline_process WHERE process_uid = ?",
                (process_uid,)
            ).fetchone()
        finally:
            cnx.close()


    #Récupère les lignes de pipeline_block d'un pipeline_process (limitées à N si fourni)
    @staticmethod
    def getBlocks(pipeline_process_id: int, limit: int = None) -> list:
        query = "SELECT * FROM pipeline_block WHERE pipeline_process_id = ? ORDER BY id ASC"
        params = [pipeline_process_id]
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        cnx = PipelineLog._connect()
        try:
            return cnx.execute(query, params).fetchall()
        finally:
            cnx.close()


    #Récupère une ligne de pipeline_block à partir de son id (None si absente)
    @staticmethod
    def getBlock(block_id: int) -> sqlite3.Row:
        cnx = PipelineLog._connect()
        try:
            return cnx.execute(
                "SELECT * FROM pipeline_block WHERE id = ?",
                (block_id,)
            ).fetchone()
        finally:
            cnx.close()
