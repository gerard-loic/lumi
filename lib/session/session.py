import asyncio
from datetime import datetime, timezone
"""
Session — Gestion du cycle de vie des sessions (authentification + historique LLM)
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class AuthSession:
    def __init__(self, session_id: str, expires_at: int, authentication: dict):
        self.session_id    = session_id
        self.expires_at    = expires_at
        self.authentication = authentication
        self.files:   list[str]  = []
        self.history: list[dict] = []

    def clear(self):
        from lib.files.filestore import FileStore
        for file in self.files:
            FileStore.delete(key=file)

    def addFile(self, key: str):
        self.files.append(key)


class AuthSessionManager:
    _sessions: list['AuthSession'] = []
    _confirmation_queues: dict[str, asyncio.Queue] = {}

    @staticmethod
    def add(session_id: str, expires_at: int, authentication: dict):
        AuthSessionManager._sessions.append(
            AuthSession(session_id=session_id, expires_at=expires_at, authentication=authentication)
        )

    @staticmethod
    def get(session_id: str) -> 'AuthSession | None':
        for session in AuthSessionManager._sessions:
            if session.session_id == session_id:
                return session
        return None

    @staticmethod
    def get_history(session_id: str | None) -> list[dict]:
        if not session_id:
            return []
        session = AuthSessionManager.get(session_id)
        return session.history if session else []

    @staticmethod
    def save_history(session_id: str | None, history: list[dict]) -> None:
        if not session_id:
            return
        session = AuthSessionManager.get(session_id)
        if session:
            session.history = history

    @staticmethod
    def count() -> int:
        return len(AuthSessionManager._sessions)

    @staticmethod
    async def wait_confirmation(session_id: str, timeout: int = 120) -> int:
        queue = asyncio.Queue(maxsize=1)
        AuthSessionManager._confirmation_queues[session_id] = queue
        try:
            return await asyncio.wait_for(queue.get(), timeout=timeout)
        finally:
            AuthSessionManager._confirmation_queues.pop(session_id, None)

    @staticmethod
    def resolve_confirmation(session_id: str, option: int) -> bool:
        queue = AuthSessionManager._confirmation_queues.get(session_id)
        if not queue:
            return False
        queue.put_nowait(option)
        return True

    @staticmethod
    def clear(all: bool = False):
        current_ts = datetime.now(tz=timezone.utc).timestamp()
        remaining = []
        for session in AuthSessionManager._sessions:
            if all or session.expires_at < current_ts:
                session.clear()
            else:
                remaining.append(session)
        AuthSessionManager._sessions = remaining
