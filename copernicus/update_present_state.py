"""Refresh or inspect the Copernicus Marine present-state cache."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time


if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from copernicus.present_state import (
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_MAX_AGE_HOURS,
    DEFAULT_VARIABLES,
    fetch_present_state,
)


def main() -> None:
    """Fetch Copernicus present-state data when needed and print JSON metadata."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Refresh from Copernicus Marine even when the cache is fresh.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help=f"Recent UTC window used to locate the latest model time. Default: {DEFAULT_LOOKBACK_DAYS}.",
    )
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=DEFAULT_MAX_AGE_HOURS,
        help=f"Fresh-cache age threshold. Default: {DEFAULT_MAX_AGE_HOURS:g} hours.",
    )
    parser.add_argument(
        "--variable",
        action="append",
        dest="variables",
        help=(
            "Copernicus variable to download. Can be repeated. "
            f"Default: {', '.join(DEFAULT_VARIABLES)}."
        ),
    )
    args = parser.parse_args()

    started_at = time.perf_counter()
    try:
        result = fetch_present_state(
            force=args.force,
            max_age_hours=args.max_age_hours,
            lookback_days=args.lookback_days,
            variables=tuple(args.variables) if args.variables else DEFAULT_VARIABLES,
        )
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