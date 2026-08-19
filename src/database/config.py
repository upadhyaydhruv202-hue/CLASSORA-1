import os
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")
except Exception:
    pass


def _toml_secrets() -> dict:
    path = _ROOT / ".streamlit" / "secrets.toml"
    if not path.exists():
        return {}
    try:
        import tomllib
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        text = path.read_text(encoding="utf-8")
        found = {}
        for key, value in re.findall(r'^([A-Z0-9_]+)\s*=\s*"([^"]*)"', text, re.M):
            found[key] = value
        return found


_TOML = _toml_secrets()


def get_secret(name: str, default: str = "") -> str:
    env = str(os.environ.get(name, "") or "").strip()
    if env:
        return env
    value = _TOML.get(name, default)
    return str(value or default).strip()


def is_supabase_configured() -> bool:
    url = get_secret("SUPABASE_URL")
    key = get_secret("SUPABASE_KEY")
    if not url or not key:
        return False
    if "YOUR_PROJECT" in url or key in ("YOUR_SUPABASE_KEY", "YOUR_SUPABASE_ANON_OR_SERVICE_KEY"):
        return False
    return True


_client = None


def get_supabase_client():
    global _client
    if not is_supabase_configured():
        raise RuntimeError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY.")
    if _client is None:
        from supabase import create_client

        _client = create_client(get_secret("SUPABASE_URL"), get_secret("SUPABASE_KEY"))
    return _client


class _SupabaseProxy:
    def table(self, *args, **kwargs):
        return get_supabase_client().table(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(get_supabase_client(), name)


supabase = _SupabaseProxy()
