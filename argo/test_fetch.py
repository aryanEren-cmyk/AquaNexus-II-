import argopy

BOX = [
    60, 100,    # longitude
    0, 30,      # latitude
    0, 2000,    # depth
    "2025-01-01",
    "2025-02-01"
]

print("Fetching ARGO data...")

ds = (
    argopy.DataFetcher(
        ds="phy",
        parallel=True
    )
    .region(BOX)
    .to_xarray()
)

print("\nSUCCESS!")
print(ds)