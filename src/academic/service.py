"""Academic resource catalog. Stores metadata + original URLs only. No scraping."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

from src.success import store

YEARS = (
    {"id": "YEAR_1", "label": "1st Year", "semesters": ("SEM_1", "SEM_2")},
    {"id": "YEAR_2", "label": "2nd Year", "semesters": ("SEM_3", "SEM_4")},
    {"id": "YEAR_3", "label": "3rd Year", "semesters": ("SEM_5", "SEM_6")},
    {"id": "YEAR_4", "label": "4th Year", "semesters": ("SEM_7", "SEM_8")},
)

SEMESTERS = (
    {"id": "SEM_1", "label": "Semester 1", "year_id": "YEAR_1"},
    {"id": "SEM_2", "label": "Semester 2", "year_id": "YEAR_1"},
    {"id": "SEM_3", "label": "Semester 3", "year_id": "YEAR_2"},
    {"id": "SEM_4", "label": "Semester 4", "year_id": "YEAR_2"},
    {"id": "SEM_5", "label": "Semester 5", "year_id": "YEAR_3"},
    {"id": "SEM_6", "label": "Semester 6", "year_id": "YEAR_3"},
    {"id": "SEM_7", "label": "Semester 7", "year_id": "YEAR_4"},
    {"id": "SEM_8", "label": "Semester 8", "year_id": "YEAR_4"},
)

YEAR_IDS = {row["id"] for row in YEARS}
SEMESTER_IDS = {row["id"] for row in SEMESTERS}
SEMESTER_YEAR = {row["id"]: row["year_id"] for row in SEMESTERS}

FORMATS = ("PDF", "WEBPAGE", "DOCUMENT", "IMAGE", "VIDEO", "OTHER")

DEFAULT_TYPES = (
    {"code": "NOTES", "name": "Notes", "display_order": 10},
    {"code": "PYQ", "name": "PYQ", "display_order": 20},
    {"code": "ASSIGNMENT", "name": "Assignment", "display_order": 30},
    {"code": "PRACTICAL", "name": "Practical", "display_order": 40},
    {"code": "QUESTION_BANK", "name": "Question Bank", "display_order": 50},
    {"code": "REFERENCE", "name": "Reference Material", "display_order": 60},
    {"code": "VIDEO", "name": "Video", "display_order": 70},
    {"code": "EBOOK", "name": "E-book", "display_order": 80},
    {"code": "LAB_MANUAL", "name": "Lab Manual", "display_order": 90},
    {"code": "CHEAT_SHEET", "name": "Cheat Sheet", "display_order": 100},
    {"code": "IMPORTANT_QUESTIONS", "name": "Important Questions", "display_order": 110},
    {"code": "SYLLABUS", "name": "Syllabus", "display_order": 120},
    {"code": "OTHER", "name": "Other", "display_order": 130},
)

DEFAULT_SOURCES = (
    {
        "code": "brainspot_it",
        "name": "The Brain Spot — Information Technology",
        "website_url": "https://thebrainspot.org/information-technology/",
        "description": "Senior-maintained Information Technology resources.",
        "organization": "The Brain Spot",
        "section": "Information Technology",
    },
    {
        "code": "brainspot_y2",
        "name": "The Brain Spot — 2nd Year",
        "website_url": "https://thebrainspot.org/2nd-year/",
        "description": "Senior-maintained 2nd year resources.",
        "organization": "The Brain Spot",
        "section": "2nd Year",
    },
    {
        "code": "brainspot_y3",
        "name": "The Brain Spot — 3rd Year",
        "website_url": "https://thebrainspot.org/3rd-year/",
        "description": "Senior-maintained 3rd year resources.",
        "organization": "The Brain Spot",
        "section": "3rd Year",
    },
    {
        "code": "ldrp_study",
        "name": "LDRP Study Material",
        "website_url": "https://ldrp.bhavsarneev.de/index.php",
        "description": "LDRP study material collected by seniors.",
        "organization": "LDRP Study Material",
        "section": "All semesters",
    },
    {
        "code": "collegpt",
        "name": "ColleGPT",
        "website_url": "https://www.collegpt.com/courses",
        "description": "ColleGPT course and academic resources.",
        "organization": "ColleGPT",
        "section": "Courses",
    },
)

UNSAFE_SCHEMES = {"javascript", "data", "file", "vbscript", "blob"}


def _now():
    return datetime.now(timezone.utc).isoformat()


def installed() -> bool:
    return store.available("academic_resources") and store.available("academic_resource_sources")


def install_error() -> str:
    if installed():
        return ""
    return (
        "Academic resource tables are not installed. "
        "Run supabase/schema_academic_resources.sql in the Supabase SQL Editor."
    )


def normalize_url(raw: str) -> tuple[str | None, str | None]:
    text = str(raw or "").strip()
    if not text:
        return None, "Original URL is required."
    parsed = urlparse(text)
    scheme = (parsed.scheme or "").lower()
    if scheme in UNSAFE_SCHEMES:
        return None, "That URL scheme is not allowed."
    if scheme not in ("https", "http"):
        return None, "Enter a valid HTTPS URL."
    if scheme != "https":
        return None, "Only HTTPS URLs are allowed."
    if not parsed.netloc or "." not in parsed.netloc:
        return None, "Enter a valid HTTPS URL."
    if parsed.username or parsed.password:
        return None, "URLs with embedded credentials are not allowed."
    cleaned = urlunparse((
        "https",
        parsed.netloc.lower(),
        parsed.path or "/",
        parsed.params,
        parsed.query,
        "",
    ))
    return cleaned, None


def infer_format(url: str, explicit: str | None = None) -> str:
    chosen = str(explicit or "").strip().upper()
    if chosen in FORMATS:
        return chosen
    path = urlparse(url).path.lower()
    if path.endswith(".pdf"):
        return "PDF"
    if path.endswith((".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx")):
        return "DOCUMENT"
    if path.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return "IMAGE"
    if path.endswith((".mp4", ".webm", ".mov")):
        return "VIDEO"
    return "WEBPAGE"


def resolve_year_id(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw in YEAR_IDS:
        return raw
    key = raw.upper().replace(" ", "_").replace("-", "_")
    aliases = {
        "1": "YEAR_1", "YEAR1": "YEAR_1", "1ST": "YEAR_1", "1ST_YEAR": "YEAR_1", "FIRST": "YEAR_1",
        "2": "YEAR_2", "YEAR2": "YEAR_2", "2ND": "YEAR_2", "2ND_YEAR": "YEAR_2", "SECOND": "YEAR_2",
        "3": "YEAR_3", "YEAR3": "YEAR_3", "3RD": "YEAR_3", "3RD_YEAR": "YEAR_3", "THIRD": "YEAR_3",
        "4": "YEAR_4", "YEAR4": "YEAR_4", "4TH": "YEAR_4", "4TH_YEAR": "YEAR_4", "FOURTH": "YEAR_4",
    }
    return aliases.get(key)


def resolve_semester_id(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw in SEMESTER_IDS:
        return raw
    key = raw.upper().replace(" ", "_").replace("-", "_")
    if key in SEMESTER_IDS:
        return key
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits.isdigit() and 1 <= int(digits) <= 8:
        return f"SEM_{int(digits)}"
    aliases = {f"SEMESTER_{n}": f"SEM_{n}" for n in range(1, 9)}
    aliases.update({f"SEMESTER{n}": f"SEM_{n}" for n in range(1, 9)})
    return aliases.get(key)


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _ensure_types():
    rows = store.select("academic_resource_types") or []
    have = {str(row.get("code") or "").upper() for row in rows}
    for item in DEFAULT_TYPES:
        if item["code"] in have:
            continue
        store.insert("academic_resource_types", {
            "code": item["code"],
            "name": item["name"],
            "display_order": item["display_order"],
            "is_active": True,
            "created_at": _now(),
            "updated_at": _now(),
        })


def _ensure_sources():
    rows = store.select("academic_resource_sources") or []
    have = {str(row.get("code") or "") for row in rows}
    for item in DEFAULT_SOURCES:
        if item["code"] in have:
            continue
        store.insert("academic_resource_sources", {
            "code": item["code"],
            "name": item["name"],
            "website_url": item["website_url"],
            "description": item.get("description"),
            "organization": item.get("organization"),
            "section": item.get("section"),
            "is_active": True,
            "created_at": _now(),
            "updated_at": _now(),
        })


def ensure_catalog() -> str:
    if not installed():
        return install_error()
    _ensure_types()
    _ensure_sources()
    return ""


def years():
    return list(YEARS)


def semesters(year_id=None):
    if year_id and year_id in YEAR_IDS:
        return [row for row in SEMESTERS if row["year_id"] == year_id]
    return list(SEMESTERS)


def types(*, include_inactive=False):
    rows = store.select("academic_resource_types") or []
    if not include_inactive:
        rows = [row for row in rows if row.get("is_active") is not False]
    rows.sort(key=lambda row: (int(row.get("display_order") or 0), str(row.get("name") or "")))
    return rows


def sources(*, include_inactive=False):
    rows = store.select("academic_resource_sources") or []
    if not include_inactive:
        rows = [row for row in rows if row.get("is_active") is not False]
    rows.sort(key=lambda row: str(row.get("name") or ""))
    return rows


def subjects(*, year_id=None, semester_id=None, include_inactive=False):
    rows = store.select("academic_resource_subjects") or []
    out = []
    for row in rows:
        if not include_inactive and str(row.get("status") or "ACTIVE").upper() != "ACTIVE":
            continue
        if year_id and row.get("year_id") != year_id:
            continue
        if semester_id and row.get("semester_id") != semester_id:
            continue
        out.append(row)
    out.sort(key=lambda row: str(row.get("name") or ""))
    return out


def catalog(*, year_id=None, semester_id=None, include_inactive=False):
    err = ensure_catalog()
    return {
        "installed": not err,
        "detail": err,
        "years": years(),
        "semesters": semesters(year_id),
        "subjects": subjects(year_id=year_id, semester_id=semester_id, include_inactive=include_inactive),
        "types": types(include_inactive=include_inactive),
        "sources": sources(include_inactive=include_inactive),
        "formats": list(FORMATS),
    }


def _by_id(table, value):
    if value in (None, ""):
        return None
    rows = store.select(table) or []
    for row in rows:
        if str(row.get("id")) == str(value):
            return row
    return None


def _year_label(year_id):
    for row in YEARS:
        if row["id"] == year_id:
            return row["label"]
    return year_id


def _semester_label(semester_id):
    for row in SEMESTERS:
        if row["id"] == semester_id:
            return row["label"]
    return semester_id


def _public_resource(row, type_map=None, source_map=None, subject_map=None):
    type_map = type_map or {}
    source_map = source_map or {}
    subject_map = subject_map or {}
    subject = subject_map.get(str(row.get("subject_id"))) or _by_id("academic_resource_subjects", row.get("subject_id")) or {}
    rtype = type_map.get(str(row.get("resource_type_id"))) or _by_id("academic_resource_types", row.get("resource_type_id")) or {}
    source = source_map or {}
    src = source.get(str(row.get("source_id"))) if isinstance(source, dict) else None
    src = src or _by_id("academic_resource_sources", row.get("source_id")) or {}
    return {
        "id": row.get("id"),
        "title": row.get("title"),
        "description": row.get("description") or "",
        "yearId": row.get("year_id"),
        "yearLabel": _year_label(row.get("year_id")),
        "semesterId": row.get("semester_id"),
        "semesterLabel": _semester_label(row.get("semester_id")),
        "subjectId": row.get("subject_id"),
        "subjectName": subject.get("name"),
        "subjectCode": subject.get("code") or "",
        "resourceTypeId": row.get("resource_type_id"),
        "resourceType": rtype.get("name") or rtype.get("code"),
        "resourceTypeCode": rtype.get("code"),
        "sourceId": row.get("source_id"),
        "sourceName": src.get("organization") or src.get("name"),
        "sourceSection": src.get("section") or "",
        "sourceWebsiteUrl": src.get("website_url"),
        "originalUrl": row.get("original_url"),
        "resourceFormat": row.get("resource_format") or "WEBPAGE",
        "discoveryStatus": row.get("discovery_status") or "VERIFIED",
        "isActive": row.get("is_active") is not False,
        "tags": row.get("tags") or "",
        "displayOrder": row.get("display_order") or 0,
        "lastVerifiedAt": row.get("last_verified_at"),
        "createdAt": row.get("created_at"),
        "updatedAt": row.get("updated_at"),
    }


def _maps():
    types_map = {str(row.get("id")): row for row in (store.select("academic_resource_types") or [])}
    sources_map = {str(row.get("id")): row for row in (store.select("academic_resource_sources") or [])}
    subjects_map = {str(row.get("id")): row for row in (store.select("academic_resource_subjects") or [])}
    return types_map, sources_map, subjects_map


def _search_needles(raw: str) -> set[str]:
    text = str(raw or "").strip().lower()
    if not text:
        return set()
    needles = {text}
    extras = {
        "assignments": {"assignment", "assignments"},
        "assignment": {"assignment", "assignments"},
        "notes": {"note", "notes"},
        "pyqs": {"pyq", "previous year"},
        "pyq": {"pyq", "previous year"},
    }
    needles.update(extras.get(text, set()))
    if text.endswith("s") and len(text) > 4:
        needles.add(text[:-1])
    return needles


def _matches_search(public, needle: str) -> bool:
    if not needle:
        return True
    hay = " ".join([
        str(public.get("title") or ""),
        str(public.get("description") or ""),
        str(public.get("subjectName") or ""),
        str(public.get("subjectCode") or ""),
        str(public.get("resourceType") or ""),
        str(public.get("resourceTypeCode") or ""),
        str(public.get("sourceName") or ""),
        str(public.get("sourceSection") or ""),
        str(public.get("tags") or ""),
    ]).lower()
    return any(token in hay for token in _search_needles(needle))


def list_resources(
    *,
    year_id=None,
    semester_id=None,
    subject_id=None,
    type_id=None,
    type_code=None,
    source_id=None,
    source_code=None,
    search="",
    sort="recent",
    page=1,
    limit=20,
    include_inactive=False,
):
    err = ensure_catalog()
    if err:
        return {"items": [], "total": 0, "page": 1, "limit": limit, "detail": err, "installed": False}
    year_id = resolve_year_id(year_id) or (year_id if year_id in YEAR_IDS else None)
    semester_id = resolve_semester_id(semester_id) or (semester_id if semester_id in SEMESTER_IDS else None)
    types_map, sources_map, subjects_map = _maps()
    type_ids = set()
    if type_id:
        type_ids.add(str(type_id))
    if type_code:
        needle_type = str(type_code).strip().lower()
        for row in types_map.values():
            if needle_type in {str(row.get("id")), str(row.get("code") or "").lower(), str(row.get("name") or "").lower()}:
                type_ids.add(str(row.get("id")))
    source_ids = set()
    if source_id:
        source_ids.add(str(source_id))
    if source_code:
        needle_source = str(source_code).strip().lower()
        for row in sources_map.values():
            blob = f"{row.get('id')} {row.get('code') or ''} {row.get('name') or ''}".lower()
            if needle_source == str(row.get("id")) or needle_source == str(row.get("code") or "").lower() or needle_source in blob:
                source_ids.add(str(row.get("id")))
    if subject_id:
        subject_id = str(subject_id)
        matched_subject = subjects_map.get(subject_id)
        if not matched_subject:
            needle_subject = subject_id.lower()
            for row in subjects_map.values():
                if needle_subject in {str(row.get("id")), str(row.get("code") or "").lower(), str(row.get("name") or "").lower()}:
                    subject_id = str(row.get("id"))
                    break
    needle = str(search or "").strip().lower()
    rows = store.select("academic_resources") or []
    items = []
    for row in rows:
        if not include_inactive and row.get("is_active") is False:
            continue
        src = sources_map.get(str(row.get("source_id"))) or {}
        if not include_inactive and src.get("is_active") is False:
            continue
        sub = subjects_map.get(str(row.get("subject_id"))) or {}
        if not include_inactive and str(sub.get("status") or "ACTIVE").upper() != "ACTIVE":
            continue
        if year_id and row.get("year_id") != year_id:
            continue
        if semester_id and row.get("semester_id") != semester_id:
            continue
        if subject_id and str(row.get("subject_id")) != str(subject_id):
            continue
        if type_ids and str(row.get("resource_type_id")) not in type_ids:
            continue
        if source_ids and str(row.get("source_id")) not in source_ids:
            continue
        public = _public_resource(row, types_map, sources_map, subjects_map)
        if not _matches_search(public, needle):
            continue
        items.append(public)
    sort = str(sort or "recent").lower()
    if sort == "alpha":
        items.sort(key=lambda row: str(row.get("title") or "").lower())
    elif sort in ("updated", "recently_updated"):
        items.sort(key=lambda row: str(row.get("updatedAt") or ""), reverse=True)
    else:
        items.sort(key=lambda row: (-_as_int(row.get("displayOrder"), 0), str(row.get("createdAt") or "")), reverse=False)
        items.sort(key=lambda row: str(row.get("createdAt") or ""), reverse=True)
    try:
        page = max(1, int(page or 1))
        limit = min(50, max(1, int(limit or 20)))
    except (TypeError, ValueError):
        page, limit = 1, 20
    total = len(items)
    start = (page - 1) * limit
    return {
        "items": items[start:start + limit],
        "total": total,
        "page": page,
        "limit": limit,
        "installed": True,
        "detail": "",
    }


def get_resource(resource_id, *, include_inactive=False):
    row = _by_id("academic_resources", resource_id)
    if not row:
        return None, "Resource not found."
    if not include_inactive and row.get("is_active") is False:
        return None, "Resource not found."
    return _public_resource(row), None


def _validate_relation(year_id, semester_id, subject_id, type_id, source_id):
    if year_id not in YEAR_IDS:
        return None, "Choose a valid year."
    if semester_id not in SEMESTER_IDS:
        return None, "Choose a valid semester."
    if SEMESTER_YEAR[semester_id] != year_id:
        return None, "That semester does not belong to the selected year."
    subject = _by_id("academic_resource_subjects", subject_id)
    if not subject or str(subject.get("status") or "ACTIVE").upper() != "ACTIVE":
        return None, "Choose a valid subject."
    if subject.get("year_id") != year_id or subject.get("semester_id") != semester_id:
        return None, "That subject does not belong to the selected year and semester."
    rtype = _by_id("academic_resource_types", type_id)
    if not rtype or rtype.get("is_active") is False:
        return None, "Choose a valid resource type."
    source = _by_id("academic_resource_sources", source_id)
    if not source or source.get("is_active") is False:
        return None, "Choose a valid source."
    return {"subject": subject, "type": rtype, "source": source}, None


def create_resource(payload: dict, *, actor: str):
    err = ensure_catalog()
    if err:
        return None, err
    title = str(payload.get("title") or "").strip()
    if len(title) < 3:
        return None, "Title is required."
    year_id = str(payload.get("year_id") or payload.get("yearId") or "").strip()
    semester_id = str(payload.get("semester_id") or payload.get("semesterId") or "").strip()
    related, rel_err = _validate_relation(
        year_id,
        semester_id,
        payload.get("subject_id") or payload.get("subjectId"),
        payload.get("resource_type_id") or payload.get("resourceTypeId"),
        payload.get("source_id") or payload.get("sourceId"),
    )
    if rel_err:
        return None, rel_err
    url, url_err = normalize_url(payload.get("original_url") or payload.get("originalUrl"))
    if url_err:
        return None, url_err
    subject_id = related["subject"]["id"]
    type_id = related["type"]["id"]
    for existing in store.select("academic_resources") or []:
        if str(existing.get("original_url") or "") == url:
            return None, "That resource URL is already listed."
        if (
            str(existing.get("subject_id")) == str(subject_id)
            and str(existing.get("resource_type_id")) == str(type_id)
            and str(existing.get("original_url") or "") == url
        ):
            return None, "That resource URL is already listed for this subject and type."
    fmt = infer_format(url, payload.get("resource_format") or payload.get("resourceFormat"))
    row = store.insert("academic_resources", {
        "title": title[:200],
        "description": str(payload.get("description") or "").strip()[:2000],
        "year_id": year_id,
        "semester_id": semester_id,
        "subject_id": subject_id,
        "resource_type_id": type_id,
        "source_id": related["source"]["id"],
        "original_url": url,
        "resource_format": fmt,
        "is_active": True,
        "tags": str(payload.get("tags") or "").strip()[:400],
        "display_order": _as_int(payload.get("display_order") or payload.get("displayOrder") or 0),
        "created_by": (actor or "")[:80],
        "created_at": _now(),
        "updated_at": _now(),
    })
    if not row:
        return None, store.last_error("academic_resources") or "Could not save the resource."
    return _public_resource(row[0]), None


def update_resource(resource_id, payload: dict):
    current = _by_id("academic_resources", resource_id)
    if not current:
        return None, "Resource not found."
    year_id = str(payload.get("year_id") or payload.get("yearId") or current.get("year_id") or "").strip()
    semester_id = str(payload.get("semester_id") or payload.get("semesterId") or current.get("semester_id") or "").strip()
    subject_id = payload.get("subject_id") if payload.get("subject_id") is not None else payload.get("subjectId", current.get("subject_id"))
    type_id = payload.get("resource_type_id") if payload.get("resource_type_id") is not None else payload.get("resourceTypeId", current.get("resource_type_id"))
    source_id = payload.get("source_id") if payload.get("source_id") is not None else payload.get("sourceId", current.get("source_id"))
    related, rel_err = _validate_relation(year_id, semester_id, subject_id, type_id, source_id)
    if rel_err:
        return None, rel_err
    url = current.get("original_url")
    if payload.get("original_url") or payload.get("originalUrl"):
        url, url_err = normalize_url(payload.get("original_url") or payload.get("originalUrl"))
        if url_err:
            return None, url_err
    title = str(payload.get("title") or current.get("title") or "").strip()
    if len(title) < 3:
        return None, "Title is required."
    fmt = infer_format(url, payload.get("resource_format") or payload.get("resourceFormat") or current.get("resource_format"))
    values = {
        "title": title[:200],
        "description": str(payload.get("description") if "description" in payload else current.get("description") or "").strip()[:2000],
        "year_id": year_id,
        "semester_id": semester_id,
        "subject_id": related["subject"]["id"],
        "resource_type_id": related["type"]["id"],
        "source_id": related["source"]["id"],
        "original_url": url,
        "resource_format": fmt,
        "tags": str(payload.get("tags") if "tags" in payload else current.get("tags") or "").strip()[:400],
        "updated_at": _now(),
    }
    if "is_active" in payload or "isActive" in payload:
        values["is_active"] = bool(payload.get("is_active") if "is_active" in payload else payload.get("isActive"))
    if payload.get("display_order") is not None or payload.get("displayOrder") is not None:
        values["display_order"] = _as_int(payload.get("display_order") or payload.get("displayOrder") or 0)
    updated = store.update("academic_resources", {"id": current["id"]}, values)
    if not updated:
        return None, store.last_error("academic_resources") or "Could not update the resource."
    return _public_resource(updated[0]), None


def set_resource_active(resource_id, active: bool):
    return update_resource(resource_id, {"is_active": active})


def verify_resource(resource_id):
    current = _by_id("academic_resources", resource_id)
    if not current:
        return None, "Resource not found."
    updated = store.update("academic_resources", {"id": current["id"]}, {
        "last_verified_at": _now(),
        "updated_at": _now(),
    })
    if not updated:
        return None, "Could not verify the resource."
    return _public_resource(updated[0]), None


def create_subject(payload: dict):
    err = ensure_catalog()
    if err:
        return None, err
    name = str(payload.get("name") or "").strip()
    if len(name) < 2:
        return None, "Subject name is required."
    year_id = str(payload.get("year_id") or payload.get("yearId") or "").strip()
    semester_id = str(payload.get("semester_id") or payload.get("semesterId") or "").strip()
    if year_id not in YEAR_IDS:
        return None, "Choose a valid year."
    if semester_id not in SEMESTER_IDS or SEMESTER_YEAR[semester_id] != year_id:
        return None, "Choose a valid semester for that year."
    for row in store.select("academic_resource_subjects") or []:
        if (
            str(row.get("name") or "").strip().lower() == name.lower()
            and row.get("year_id") == year_id
            and row.get("semester_id") == semester_id
        ):
            return None, "That subject already exists for this semester."
    saved = store.insert("academic_resource_subjects", {
        "name": name[:120],
        "code": str(payload.get("code") or "").strip()[:40] or None,
        "description": str(payload.get("description") or "").strip()[:500] or None,
        "year_id": year_id,
        "semester_id": semester_id,
        "status": "ACTIVE",
        "created_at": _now(),
        "updated_at": _now(),
    })
    if not saved:
        return None, store.last_error("academic_resource_subjects") or "Could not save the subject."
    return saved[0], None


def update_subject(subject_id, payload: dict):
    current = _by_id("academic_resource_subjects", subject_id)
    if not current:
        return None, "Subject not found."
    values = {"updated_at": _now()}
    if payload.get("name"):
        values["name"] = str(payload.get("name")).strip()[:120]
    if "code" in payload:
        values["code"] = str(payload.get("code") or "").strip()[:40] or None
    if "description" in payload:
        values["description"] = str(payload.get("description") or "").strip()[:500] or None
    if payload.get("status"):
        status = str(payload.get("status")).strip().upper()
        if status not in ("ACTIVE", "INACTIVE"):
            return None, "Status must be ACTIVE or INACTIVE."
        values["status"] = status
    updated = store.update("academic_resource_subjects", {"id": current["id"]}, values)
    if not updated:
        return None, "Could not update the subject."
    return updated[0], None


def create_source(payload: dict):
    err = ensure_catalog()
    if err:
        return None, err
    name = str(payload.get("name") or "").strip()
    if len(name) < 2:
        return None, "Source name is required."
    url, url_err = normalize_url(payload.get("website_url") or payload.get("websiteUrl"))
    if url_err:
        return None, url_err
    code = str(payload.get("code") or name).strip().lower().replace(" ", "_")[:40]
    for row in store.select("academic_resource_sources") or []:
        if str(row.get("code") or "") == code:
            return None, "A source with that code already exists."
    saved = store.insert("academic_resource_sources", {
        "code": code,
        "name": name[:160],
        "website_url": url,
        "description": str(payload.get("description") or "").strip()[:500] or None,
        "is_active": True,
        "created_at": _now(),
        "updated_at": _now(),
    })
    if not saved:
        return None, "Could not save the source."
    return saved[0], None


def update_source(source_id, payload: dict):
    current = _by_id("academic_resource_sources", source_id)
    if not current:
        return None, "Source not found."
    values = {"updated_at": _now()}
    if payload.get("name"):
        values["name"] = str(payload.get("name")).strip()[:160]
    if payload.get("website_url") or payload.get("websiteUrl"):
        url, url_err = normalize_url(payload.get("website_url") or payload.get("websiteUrl"))
        if url_err:
            return None, url_err
        values["website_url"] = url
    if "description" in payload:
        values["description"] = str(payload.get("description") or "").strip()[:500] or None
    if "is_active" in payload or "isActive" in payload:
        values["is_active"] = bool(payload.get("is_active") if "is_active" in payload else payload.get("isActive"))
    updated = store.update("academic_resource_sources", {"id": current["id"]}, values)
    if not updated:
        return None, "Could not update the source."
    return updated[0], None


def create_type(payload: dict):
    err = ensure_catalog()
    if err:
        return None, err
    name = str(payload.get("name") or "").strip()
    if len(name) < 2:
        return None, "Resource type name is required."
    code = str(payload.get("code") or name).strip().upper().replace(" ", "_")[:40]
    for row in store.select("academic_resource_types") or []:
        if str(row.get("code") or "").upper() == code:
            return None, "That resource type already exists."
    saved = store.insert("academic_resource_types", {
        "code": code,
        "name": name[:80],
        "display_order": _as_int(payload.get("display_order") or payload.get("displayOrder") or 200, 200),
        "is_active": True,
        "created_at": _now(),
        "updated_at": _now(),
    })
    if not saved:
        return None, "Could not save the resource type."
    return saved[0], None


def report_broken(resource_id, *, student_id, reason: str):
    resource = _by_id("academic_resources", resource_id)
    if not resource or resource.get("is_active") is False:
        return None, "Resource not found."
    text = str(reason or "").strip() or "Resource link is not working"
    for row in store.select("academic_resource_reports") or []:
        if (
            str(row.get("resource_id")) == str(resource["id"])
            and str(row.get("student_id")) == str(student_id)
            and str(row.get("status") or "").upper() == "PENDING"
        ):
            return None, "You already reported this resource. It is waiting for review."
    saved = store.insert("academic_resource_reports", {
        "resource_id": resource["id"],
        "student_id": student_id,
        "reason": text[:500],
        "status": "PENDING",
        "created_at": _now(),
    })
    if not saved:
        return None, store.last_error("academic_resource_reports") or "Could not save the report."
    return saved[0], None


def list_reports(*, status=None):
    rows = store.select("academic_resource_reports") or []
    if status:
        rows = [row for row in rows if str(row.get("status") or "").upper() == str(status).upper()]
    rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    types_map, sources_map, subjects_map = _maps()
    out = []
    for row in rows:
        resource = _by_id("academic_resources", row.get("resource_id"))
        public = _public_resource(resource, types_map, sources_map, subjects_map) if resource else None
        out.append({
            "id": row.get("id"),
            "resourceId": row.get("resource_id"),
            "studentId": row.get("student_id"),
            "reason": row.get("reason"),
            "status": row.get("status"),
            "createdAt": row.get("created_at"),
            "reviewedAt": row.get("reviewed_at"),
            "resource": public,
        })
    return out


def review_report(report_id, decision: str):
    decision = str(decision or "").strip().upper()
    if decision not in ("REVIEWED", "RESOLVED", "DISMISSED"):
        return None, "Choose reviewed, resolved, or dismissed."
    current = _by_id("academic_resource_reports", report_id)
    if not current:
        return None, "Report not found."
    updated = store.update("academic_resource_reports", {"id": current["id"]}, {
        "status": decision,
        "reviewed_at": _now(),
    })
    if not updated:
        return None, "Could not update the report."
    return updated[0], None


def type_by_code(code: str):
    wanted = str(code or "OTHER").strip().upper()
    for row in types(include_inactive=True):
        if str(row.get("code") or "").upper() == wanted:
            return row
    other = next((row for row in types(include_inactive=True) if str(row.get("code") or "").upper() == "OTHER"), None)
    return other


def get_or_create_subject(name: str, code: str = "", year_id: str | None = None, semester_id: str | None = None):
    title = str(name or "").strip() or "Academic subject"
    year_id = year_id if year_id in YEAR_IDS else ""
    semester_id = semester_id if semester_id in SEMESTER_IDS else ""
    if year_id and semester_id and SEMESTER_YEAR.get(semester_id) != year_id:
        semester_id = ""
    for row in store.select("academic_resource_subjects") or []:
        if (
            str(row.get("name") or "").strip().lower() == title.lower()
            and str(row.get("year_id") or "") == year_id
            and str(row.get("semester_id") or "") == semester_id
        ):
            return row, None
    saved = store.insert("academic_resource_subjects", {
        "name": title[:120],
        "code": str(code or "").strip()[:40] or None,
        "year_id": year_id,
        "semester_id": semester_id,
        "status": "ACTIVE",
        "created_at": _now(),
        "updated_at": _now(),
    })
    if not saved:
        return None, store.last_error("academic_resource_subjects") or "Could not save the subject."
    return saved[0], None


def import_discovered(item: dict, source: dict, *, actor="sync", known_urls=None):
    title = str(item.get("title") or "").strip()
    url, url_err = normalize_url(item.get("original_url") or item.get("originalUrl"))
    if not title or url_err:
        return None, "skipped", url_err or "Title is required."
    known = known_urls if known_urls is not None else {
        str(existing.get("original_url") or "") for existing in (store.select("academic_resources") or [])
    }
    if url in known:
        return None, "duplicate", ""
    rtype = type_by_code(item.get("type_code") or item.get("resourceType") or "OTHER")
    if not rtype:
        return None, "failed", "Resource type catalog is missing."
    year_id = item.get("year_id") if item.get("year_id") in YEAR_IDS else ""
    semester_id = item.get("semester_id") if item.get("semester_id") in SEMESTER_IDS else ""
    if year_id and semester_id and SEMESTER_YEAR.get(semester_id) != year_id:
        semester_id = ""
    if not semester_id and not year_id:
        semester_id = "SEM_1"
        year_id = "YEAR_1"
        status_default = "NEEDS_REVIEW"
    elif not semester_id:
        # Keep year; pick first semester in that year for storage consistency.
        semester_id = next((row["id"] for row in SEMESTERS if row["year_id"] == year_id), "SEM_1")
        status_default = "NEEDS_REVIEW"
    elif not year_id:
        year_id = SEMESTER_YEAR.get(semester_id, "YEAR_1")
        status_default = "NEEDS_REVIEW"
    else:
        status_default = "AUTO_DISCOVERED"
    subject, sub_err = get_or_create_subject(
        item.get("subject_name") or title,
        item.get("subject_code") or "",
        year_id,
        semester_id,
    )
    if not subject:
        return None, "failed", sub_err
    fmt = infer_format(url, item.get("resource_format") or item.get("resourceFormat"))
    status = str(item.get("status") or status_default).upper()
    if status not in ("VERIFIED", "AUTO_DISCOVERED", "NEEDS_REVIEW"):
        status = status_default
    payload = {
        "title": title[:200],
        "description": str(item.get("description") or "").strip()[:2000],
        "year_id": year_id,
        "semester_id": semester_id,
        "subject_id": subject["id"],
        "resource_type_id": rtype["id"],
        "source_id": source["id"],
        "original_url": url,
        "resource_format": fmt,
        "is_active": True,
        "tags": str(item.get("tags") or item.get("subject_code") or "").strip()[:400],
        "display_order": 0,
        "created_by": (actor or "sync")[:80],
        "created_at": _now(),
        "updated_at": _now(),
    }
    # Prefer inserts without optional discovery_status (column may be absent on older SQL).
    saved = store.insert("academic_resources", payload)
    if not saved:
        return None, "failed", store.last_error("academic_resources") or "Could not save the resource."
    if known_urls is not None:
        known_urls.add(url)
    return _public_resource(saved[0]), "created", ""


def sync_registered_sources(*, source_id=None, actor="admin"):
    err = ensure_catalog()
    if err:
        return None, err
    from src.academic.discover import adapter_for

    sources_rows = sources(include_inactive=True)
    if source_id:
        sources_rows = [row for row in sources_rows if str(row.get("id")) == str(source_id) or str(row.get("code")) == str(source_id)]
        if not sources_rows:
            return None, "Choose a registered source."
    report = {
        "sourcesScanned": 0,
        "pagesDiscovered": 0,
        "resourcesDiscovered": 0,
        "newResources": 0,
        "updatedResources": 0,
        "duplicatesSkipped": 0,
        "needsReview": 0,
        "failed": 0,
        "sources": [],
    }
    for source in sources_rows:
        adapter = adapter_for(source)
        entry = {"code": source.get("code"), "name": source.get("name"), "ok": False, "error": "", "discovered": 0}
        if not adapter:
            entry["error"] = "No discovery adapter for this source."
            report["failed"] += 1
            report["sources"].append(entry)
            continue
        report["sourcesScanned"] += 1
        try:
            result = adapter.discover(source)
        except Exception as exc:
            entry["error"] = str(exc)
            report["failed"] += 1
            report["sources"].append(entry)
            continue
        report["pagesDiscovered"] += int(result.get("pages") or 0)
        if not result.get("ok"):
            entry["error"] = result.get("error") or "Automatic discovery unavailable."
            report["failed"] += 1
            report["sources"].append(entry)
            continue
        entry["ok"] = True
        entry["error"] = result.get("error") or ""
        known_urls = {str(row.get("original_url") or "") for row in (store.select("academic_resources") or [])}
        for item in result.get("resources") or []:
            report["resourcesDiscovered"] += 1
            try:
                _row, action, detail = import_discovered(item, source, actor=actor, known_urls=known_urls)
            except Exception as exc:
                action, detail = "failed", str(exc)
                _row = None
            if action == "created":
                report["newResources"] += 1
                if str(item.get("status") or "").upper() == "NEEDS_REVIEW":
                    report["needsReview"] += 1
            elif action == "duplicate":
                report["duplicatesSkipped"] += 1
            else:
                report["failed"] += 1
                if detail:
                    entry["error"] = f"{entry.get('error') or ''} {detail}".strip()
            entry["discovered"] += 1
        report["sources"].append(entry)
    return report, None
