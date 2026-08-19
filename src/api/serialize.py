from datetime import datetime


def clean(value):
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [clean(v) for v in value]
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return clean(item())
        except Exception:
            pass
    return str(value)
