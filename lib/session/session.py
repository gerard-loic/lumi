import asyncio
from datetime import datetime, timezone
"""
Session — Gestion du cycle de vie des sessions (authentification + historique LLM)
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class AuthSession:
    def __init__(self, session_id: str, expires_at: int, authentication: dict, auth_fingerprint: str = ""):
        self.session_id      = session_id
        self.expires_at      = expires_at
        self.authentication  = authentication
        self.auth_fingerprint = auth_fingerprint
        self.files:   list[str]  = []
        self.history: list[dict] = []
        self.ws_connected: bool  = False

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
    def add(session_id: str, expires_at: int, authentication: dict, auth_fingerprint: str = ""):
        AuthSessionManager._sessions.append(
            AuthSession(session_id=session_id, expires_at=expires_at, authentication=authentication, auth_fingerprint=auth_fingerprint)
        )

    @staticmethod
    def has_active_ws_for(auth_fingerprint: str) -> bool:
        for session in AuthSessionManager._sessions:
            if session.auth_fingerprint == auth_fingerprint and session.ws_connected:
                return True
        return False

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
    def claim_ws(session_id: str) -> bool:
        session = AuthSessionManager.get(session_id)
        if not session or session.ws_connected:
            return False
        session.ws_connected = True
        return True

    @staticmethod
    def release_ws(session_id: str) -> None:
        session = AuthSessionManager.get(session_id)
        if session:
            session.ws_connected = False

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
