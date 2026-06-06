"""In-memory chat session store.

Sessions are never expired — this is a single-user local tool and sessions
are lost on process restart by design.
"""

import uuid
from dataclasses import dataclass, field

MAX_HISTORY_TURNS = 20  # keep last 20 exchange pairs = 40 messages
MAX_SESSIONS = 500      # evict oldest when exceeded (single-user local tool)


@dataclass
class ChatSession:
    session_id: str
    messages: list[dict] = field(default_factory=list)
    # OpenAI-format: [{"role": "user"|"assistant", "content": "..."}]


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, ChatSession] = {}

    def get_or_create(self, session_id: str | None) -> ChatSession:
        """Return existing session by ID, or create a new one.

        Evicts the oldest session when the store reaches MAX_SESSIONS.
        """
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]
        if len(self._sessions) >= MAX_SESSIONS:
            oldest_key = next(iter(self._sessions))
            del self._sessions[oldest_key]
        new_id = str(uuid.uuid4())
        session = ChatSession(session_id=new_id)
        self._sessions[new_id] = session
        return session

    def delete(self, session_id: str) -> bool:
        """Delete a session. Returns True if it existed."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def add_turn(
        self, session: ChatSession, user_msg: str, assistant_msg: str
    ) -> None:
        """Append a user/assistant exchange and trim to MAX_HISTORY_TURNS pairs."""
        session.messages.append({"role": "user", "content": user_msg})
        session.messages.append({"role": "assistant", "content": assistant_msg})
        # Trim oldest turns when we exceed the cap
        if len(session.messages) > MAX_HISTORY_TURNS * 2:
            session.messages = session.messages[-(MAX_HISTORY_TURNS * 2) :]
