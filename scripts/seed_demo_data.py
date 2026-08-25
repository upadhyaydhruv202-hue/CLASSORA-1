"""Seed or reset CLASSORA prototype demo data."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from src.success.demo_ops import reset_demo_data  # noqa: E402
from src.success.demo_seed import seed  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed or reset CLASSORA demo data.")
    parser.add_argument("--reset", action="store_true", help="Delete only DEMO-labeled records, then exit.")
    parser.add_argument("--reset-and-seed", action="store_true", help="Delete DEMO records, then seed again.")
    args = parser.parse_args()
    if args.reset or args.reset_and_seed:
        print(json.dumps({"reset": reset_demo_data()}, indent=2, default=str))
        if args.reset and not args.reset_and_seed:
            return 0
    result = seed()
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
