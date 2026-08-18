"""Refresh or inspect the near-real-time ARGO live cache."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time


if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from argo.live.live_argo import fetch_live_argo


def main() -> None:
    """Fetch live ARGO data when needed and print JSON-friendly metadata."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Refresh from IFREMER ERDDAP even when the live cache is fresh.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=15,
        help="Recent UTC time window to query. Default: 15.",
    )
    args = parser.parse_args()

    started_at = time.perf_counter()
    try:
        result = fetch_live_argo(lookback_days=args.lookback_days, force=args.force)
        exit_code = 0
    except Exception as exc:
        result = {
            "status": "failed",
            "error": str(exc),
        }
        exit_code = 1

    result["runtime_seconds"] = time.perf_counter() - started_at
    print(json.dumps(result, indent=2, default=str))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
