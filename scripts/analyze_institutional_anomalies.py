"""Run institutional cohort anomaly analysis against the live classroom store."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from src.cohort import service as cohort  # noqa: E402
from src.database.config import is_supabase_configured  # noqa: E402

print("supabase_configured", is_supabase_configured())
result = cohort.run_analysis(persist=True, actor="cli-analyze")
print(json.dumps({
    "coldStart": result.get("cold_start"),
    "cohortsAnalyzed": result.get("cohorts_analyzed"),
    "anomalies": len(result.get("events") or []),
    "persist": result.get("persist"),
    "durationMs": result.get("durationMs"),
    "dimensions": result.get("dimensions"),
}, indent=2, default=str))
