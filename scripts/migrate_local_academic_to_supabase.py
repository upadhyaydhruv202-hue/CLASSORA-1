"""Migrate locally cached academic resources into Supabase (one-shot)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from src.academic import service as academic  # noqa: E402
from src.database.config import is_supabase_configured, supabase  # noqa: E402
from src.success import store  # noqa: E402

LOCAL = ROOT / "data" / "success_store.json"


def main():
    if not is_supabase_configured():
        print("Supabase is not configured.")
        return 1
    academic.ensure_catalog()
    # Reset availability after prior schema-drift fallback.
    store._AVAIL["academic_resources"] = True
    local = json.loads(LOCAL.read_text(encoding="utf-8")) if LOCAL.exists() else {}
    rows = list((local.get("tables") or {}).get("academic_resources") or [])
    print("local_rows", len(rows))
    # Map local subject ids -> cloud subjects by name/year/semester.
    cloud_subjects = { (str(r.get("name") or "").lower(), r.get("year_id"), r.get("semester_id")): r for r in (store.select("academic_resource_subjects") or []) }
    cloud_sources = { str(r.get("code") or ""): r for r in (store.select("academic_resource_sources") or []) }
    local_sources = { str(r.get("id")): r for r in ((local.get("tables") or {}).get("academic_resource_sources") or []) }
    # Prefer live sources from catalog defaults.
    live_sources = { str(r.get("code") or ""): r for r in academic.sources(include_inactive=True) }
    types = { str(r.get("code") or "").upper(): r for r in academic.types(include_inactive=True) }
    local_types = { str(r.get("id")): r for r in ((local.get("tables") or {}).get("academic_resource_types") or []) }
    local_subjects = { str(r.get("id")): r for r in ((local.get("tables") or {}).get("academic_resource_subjects") or []) }

    existing_urls = { str(r.get("original_url") or "") for r in (store.select("academic_resources") or []) }
    created = duplicated = failed = 0
    for row in rows:
        url = str(row.get("original_url") or "")
        if not url or url in existing_urls:
            duplicated += 1
            continue
        local_sub = local_subjects.get(str(row.get("subject_id"))) or {}
        key = (str(local_sub.get("name") or "").lower(), local_sub.get("year_id") or row.get("year_id"), local_sub.get("semester_id") or row.get("semester_id"))
        subject = cloud_subjects.get(key)
        if not subject:
            subject, err = academic.get_or_create_subject(
                local_sub.get("name") or row.get("title") or "Subject",
                local_sub.get("code") or "",
                row.get("year_id") or local_sub.get("year_id"),
                row.get("semester_id") or local_sub.get("semester_id"),
            )
            if not subject:
                failed += 1
                print("subject fail", err, row.get("title"))
                continue
            cloud_subjects[key] = subject
        local_src = local_sources.get(str(row.get("source_id"))) or {}
        source = live_sources.get(str(local_src.get("code") or "")) or cloud_sources.get(str(local_src.get("code") or ""))
        if not source:
            # fall back to brainspot_y2 / first source
            source = next(iter(live_sources.values()), None)
        local_type = local_types.get(str(row.get("resource_type_id"))) or {}
        type_code = str(local_type.get("code") or "OTHER").upper()
        rtype = types.get(type_code) or types.get("OTHER")
        payload = {
            "title": row.get("title"),
            "description": row.get("description") or "",
            "year_id": row.get("year_id") or subject.get("year_id"),
            "semester_id": row.get("semester_id") or subject.get("semester_id"),
            "subject_id": subject["id"],
            "resource_type_id": rtype["id"],
            "source_id": source["id"],
            "original_url": url,
            "resource_format": row.get("resource_format") or "WEBPAGE",
            "is_active": row.get("is_active") is not False,
            "tags": row.get("tags") or "",
            "display_order": row.get("display_order") or 0,
            "created_by": row.get("created_by") or "migrate",
            "created_at": row.get("created_at") or academic._now(),
            "updated_at": row.get("updated_at") or academic._now(),
        }
        saved = store.insert("academic_resources", payload)
        if not saved:
            failed += 1
            print("fail", store.last_error("academic_resources")[:120], url[:80])
            continue
        existing_urls.add(url)
        created += 1
    print(json_dumps := __import__("json").dumps({
        "created": created,
        "duplicates": duplicated,
        "failed": failed,
        "cloud_total": len(store.select("academic_resources") or []),
    }, indent=2))
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
