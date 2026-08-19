# Submarine Cable Module (P5)

This module is the independent submarine cable component of the AquaNexus system.

## Intended purpose

The cable module will eventually handle:

- submarine cable dataset management
- finding cables near a latitude/longitude
- cable metadata lookup
- environmental risk assessment for cable corridors
- GeoJSON export for map visualization
- a FastAPI interface for communication with the AquaNexus AI agent

## Current status

This is an initial scaffold only. No implementation logic, API code, database access, external data fetching, or AI integration has been added yet.

## Planned package layout

- `app/`: application logic and service modules
- `data/`: local data storage and related datasets
- `tests/`: validation tests for future module behaviors
- `requirements.txt`: Python dependencies for the module

## Scope boundary

This module is intentionally isolated from the other AquaNexus modules during the initial phase. It is designed to be developed independently and later integrated through clearly defined interfaces.

## Data Source

This dataset is used for the SIH prototype to provide a local, reproducible view of worldwide submarine cable routes. The source is the ArcGIS worldwide Submarine Cables layer, which is published as a FeatureServer and supports GeoJSON export.

A local GeoJSON copy is stored under the module's data folder so the demo can run without depending on the external service at runtime. This keeps the prototype self-contained while still reflecting the authoritative source data.

Source URL: https://services.arcgis.com/6DIQcwlPy8knb6sg/arcgis/rest/services/SubmarineCables/FeatureServer/2
