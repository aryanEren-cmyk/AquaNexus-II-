from argopy import DataFetcher
from pathlib import Path
from datetime import datetime
import pandas as pd


# Region around India
LON_MIN = 60
LON_MAX = 100

LAT_MIN = 0
LAT_MAX = 30

PRES_MIN = 0
PRES_MAX = 2000

# Start with one full year
START_DATE = "2021-01-01"
END_DATE = "2026-01-01"


OUTPUT_DIR = Path("argo/data/raw")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def download_month(start_date, end_date):

    filename = (
        OUTPUT_DIR
        / f"india_argo_{start_date.strftime('%Y_%m')}.nc"
    )

    # Allows us to resume later
    if filename.exists():
        print(f"Skipping {filename.name} - already downloaded")
        return

    print()
    print("=" * 60)
    print(f"Fetching {start_date.date()} → {end_date.date()}")
    print("=" * 60)

    box = [
        LON_MIN,
        LON_MAX,
        LAT_MIN,
        LAT_MAX,
        PRES_MIN,
        PRES_MAX,
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d"),
    ]

    try:

        ds = (
            DataFetcher(
                ds="phy",
                parallel=True
            )
            .region(box)
            .to_xarray()
        )

        print(f"Measurements: {ds.sizes.get('N_POINTS', 0):,}")

        if "PLATFORM_NUMBER" in ds:
            floats = len(set(ds["PLATFORM_NUMBER"].values.tolist()))
            print(f"Unique floats: {floats}")

        ds.to_netcdf(filename)

        print(f"Saved → {filename}")

    except Exception as e:

        print(f"FAILED: {e}")


def main():

    start = pd.Timestamp(START_DATE)
    final = pd.Timestamp(END_DATE)

    while start < final:

        end = start + pd.offsets.MonthBegin(1)

        if end > final:
            end = final

        download_month(start, end)

        start = end


if __name__ == "__main__":
    main()