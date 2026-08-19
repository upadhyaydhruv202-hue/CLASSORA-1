from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.auth.guards import bind_session
from src.auth.tokens import decode_token

_bearer = HTTPBearer(auto_error=False)


def get_session(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict | None:
    token = creds.credentials if creds else None
    session = decode_token(token)
    if session and session.get("demo_mode"):
        bind_session(None)
        return None
    bind_session(session)
    return session


def require_session(session: dict | None = Depends(get_session)) -> dict:
    if not session or not session.get("is_logged_in"):
        raise HTTPException(status_code=401, detail="Sign in required.")
    return session


def require_role(*roles: str):
    def _inner(session: dict = Depends(require_session)) -> dict:
        if session.get("user_role") not in roles:
            raise HTTPException(status_code=403, detail="Not allowed for this portal.")
        return session

    return _inner
