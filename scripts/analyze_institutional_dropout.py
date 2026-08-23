"""Run institutional dropout root-cause analysis against the live classroom store."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from src.dropout import service as dropout  # noqa: E402
from src.database.config import is_supabase_configured  # noqa: E402

print("supabase_configured", is_supabase_configured())
result = dropout.run_analysis(persist=True, actor="cli-analyze")
print(json.dumps({
    "insufficient": result.get("insufficient"),
    "reason": result.get("reason"),
    "overview": result.get("overview"),
    "factors": len(result.get("factors") or []),
    "persist": result.get("persist"),
    "durationMs": result.get("durationMs"),
    "version": result.get("version"),
}, indent=2, default=str))
