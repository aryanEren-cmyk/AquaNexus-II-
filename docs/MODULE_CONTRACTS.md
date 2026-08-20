# AquaNexus Module Contracts

This document defines how each specialized module communicates with
the AquaNexus Agent.

The internal implementation of each module is independent.

Only the input/output contract needs to remain consistent.

---

## 1. General Rule

Every module should expose functions that:

1. Accept clearly defined inputs.
2. Perform the required analysis.
3. Return a Python dictionary.
4. Return predictable field names.
5. Never return raw unstructured text when structured data is possible.
6. Raise clear errors when required data is unavailable.

The Agent should interact with modules through their public functions,
not through their internal implementation.

---

# 2. ARGO Module

Location:

```text
argo/

Purpose

Provide oceanographic observations and analysis from ARGO data.

Expected capabilities
Profile retrieval
Temperature lookup
Salinity lookup
Depth/pressure information
Profile statistics
Temperature gradients
Anomaly detection
Spatial/temporal comparisons
Example input
{
    "latitude": 15.2,
    "longitude": 68.4,
    "parameter": "temperature",
    "depth": 100
}
Example output
{
    "source": "argo",
    "latitude": 15.2,
    "longitude": 68.4,
    "depth": 100,
    "parameter": "temperature",
    "value": 18.9,
    "unit": "degC",
    "timestamp": "2026-07-15T00:00:00Z"
}
Profile analysis example
{
    "profile_id": "example-profile",
    "surface_temperature": 30.6,
    "mean_temperature": 23.4,
    "deepest_depth": 200,
    "thermocline": {
        "detected": True,
        "start_depth": 25,
        "end_depth": 50
    }
}
3. Oil Spill Module

Location:

oil-spill/
Purpose

Detect and analyze possible oil-spill regions.

Expected capabilities
Identify possible spill locations
Estimate affected area where supported
Determine confidence/severity
Provide geographic information
Support map visualization
Combine spill information with ocean conditions where required
Example input
{
    "latitude": 15.2,
    "longitude": 68.4,
    "time_range": "recent"
}
Example output
{
    "source": "oil_spill",
    "spill_detected": True,
    "latitude": 15.2,
    "longitude": 68.4,
    "confidence": 0.87,
    "affected_area_km2": 42.5,
    "severity": "high",
    "timestamp": "2026-08-01T00:00:00Z"
}

If a value cannot be determined from available data, return:

None

rather than inventing a value.

4. Marine Minerals Module

Location:

minerals/
Purpose

Provide information about potentially significant marine mineral
regions.

Expected capabilities
Identify mineral/resource locations
Retrieve available mineral information
Rank or classify regions where supported
Provide geographic coordinates
Support map visualization
Example input
{
    "latitude": 10.5,
    "longitude": 72.3,
    "radius_km": 100
}
Example output
{
    "source": "marine_minerals",
    "locations": [
        {
            "latitude": 10.8,
            "longitude": 72.7,
            "resource": "polymetallic_nodules",
            "potential": "high"
        }
    ]
}
5. Submarine Cable Module

Location:

cables/
Purpose

Provide information about submarine cable locations and relevant
environmental risks.

Expected capabilities
Find cables in a region
Retrieve cable routes
Identify nearby ocean conditions
Identify potential environmental/geophysical risks where supported
Provide geographic information
Support map visualization
Example input
{
    "latitude": 15.2,
    "longitude": 68.4,
    "radius_km": 100
}
Example output
{
    "source": "submarine_cables",
    "cables": [
        {
            "name": "Example Cable",
            "coordinates": [
                [15.1, 68.2],
                [15.3, 68.6]
            ],
            "status": "active",
            "risk_level": "medium"
        }
    ]
}
6. Agent Contract

Location:

agent/

The Agent is responsible for selecting and orchestrating modules.

It should NOT contain the internal implementation of ARGO,
Oil Spill, Minerals, or Cables.

Example:

User Question
      |
      v
    Agent
      |
      +----> ARGO
      |
      +----> CABLES
      |
      v
Combine Results
      |
      v
Final Response
Example

User:

"Is there unusual ocean warming near submarine cables in the
Arabian Sea?"

The Agent may call:

ARGO
+
CABLES

Then combine the results.

7. Backend Contract

Location:

backend/

The backend exposes APIs to the frontend.

Chat request
{
    "message": "Is the Arabian Sea unusually warm?",
    "session_id": "unique-session-id"
}
Chat response
{
    "text": "The recent observations indicate...",
    "chart_data": null,
    "map_data": null
}

The backend should remain independent from the frontend's internal
implementation.

8. Visualization Contract

Modules should return enough structured information for the frontend
to visualize results.

Possible visualization types:

map
chart
profile
table
indicator

Example:

{
    "visualization": {
        "type": "map",
        "points": [
            {
                "latitude": 15.2,
                "longitude": 68.4,
                "label": "Possible Oil Spill"
            }
        ]
    }
}

The frontend decides how the visualization looks.

The module only provides the data.

9. Important Rules
Rule 1 — No fabricated data

If real data is unavailable:

None

or an explicit status such as:

"data_available": False

Do NOT silently generate fake scientific measurements.

Rule 2 — Keep modules independent

Do not import another teammate's internal implementation unless
the architecture explicitly requires it.

Use public functions/interfaces.

Rule 3 — Return structured data

Prefer:

{
    "value": 28.4,
    "unit": "degC"
}

over:

"The temperature is 28.4 degrees."

The Agent can turn structured data into natural language.

Rule 4 — Document assumptions

If an analysis uses a heuristic rather than a scientifically validated
method, clearly identify it in the result.

Rule 5 — Do not break the contract

If you need to change an input or output field, inform the team before
changing it.

The Agent, Backend, and Frontend may depend on these fields.

10. Final Integration Model
                 FRONTEND
                     |
                     v
                  BACKEND
                     |
                     v
                    AGENT
                     |
       +------+------+------+------+ 
       |      |      |      |
       v      v      v      v
     ARGO   OIL    MINERALS CABLES
       |      |      |      |
       +------+------+------+ 
                     |
                     v
              STRUCTURED DATA
                     |
                     v
                   AGENT
                     |
                     v
                 BACKEND
                     |
                     v
                FRONTEND

The specialized modules provide domain intelligence.

The Agent coordinates them.

The Backend exposes the system.

The Frontend presents the results to the user.



Save it.


**After this, only one file remains: `DEVELOPMENT.md`.** Then we can stop planning and start actually building ARGO.