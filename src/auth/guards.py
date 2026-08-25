"""Session guards without Streamlit. FastAPI binds the current user via contextvars."""

from contextvars import ContextVar

from src.auth.rbac import has_role

_session: ContextVar[dict] = ContextVar("classora_session", default=None)


def bind_session(session: dict | None):
    _session.set(session or {})


def current_session() -> dict:
    return _session.get() or {}


def session_teacher_id(session_state=None):
    data = session_state if session_state is not None else current_session()
    if not has_role(data, "teacher"):
        return None
    teacher = data.get("teacher_data") or {}
    return teacher.get("teacher_id")


def require_teacher() -> bool:
    return session_teacher_id() is not None


def require_same_teacher(teacher_id, session_state=None) -> bool:
    current = session_teacher_id(session_state)
    if current is None or teacher_id is None:
        return False
    try:
        return int(current) == int(teacher_id)
    except (TypeError, ValueError):
        return False
