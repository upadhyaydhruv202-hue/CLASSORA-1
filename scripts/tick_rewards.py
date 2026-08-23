"""Run CLASSORA Rewards expiry and notification jobs against the live store."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from src.database.config import is_supabase_configured  # noqa: E402
from src.rewards import service as rewards  # noqa: E402

print("supabase_configured", is_supabase_configured())
result = rewards.tick_jobs({"user_role": "administrator", "staff_data": {"username": "cli-tick"}})
print(json.dumps(result, indent=2, default=str))
