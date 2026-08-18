"""Build the persistent cleaned ARGO NetCDF cache."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time


if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from argo.processor import build_processed_dataset


def main() -> None:
    """Build the processed ARGO dataset and print JSON-friendly metadata."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild the processed NetCDF even when it already exists.",
    )
    args = parser.parse_args()

    started_at = time.perf_counter()
    result = build_processed_dataset(force=args.force)
    result["runtime_seconds"] = time.perf_counter() - started_at
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
