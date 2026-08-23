"""Run academic resource sync against registered sources. Admin-only catalog population."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from src.academic import service as academic  # noqa: E402
from src.database.config import is_supabase_configured  # noqa: E402
from src.success import store  # noqa: E402

print("supabase_configured", is_supabase_configured())
report, err = academic.sync_registered_sources(actor="cli-sync")
if err:
    print("ERROR", err)
    sys.exit(1)
print(json.dumps(report, indent=2))
rows = store.select("academic_resources") or []
print("TOTAL_RESOURCES", len(rows))
print("TOTAL_SUBJECTS", len(store.select("academic_resource_subjects") or []))
if rows:
    print("SAMPLE", rows[0].get("title"), rows[0].get("original_url"))
