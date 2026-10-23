# Water-treatment schema

This example is an independent semi-synthetic scenario inspired by the variable
semantics of the UCI Water Treatment Plant dataset (CC BY 4.0, DOI
10.24432/C5FS4C). It does not reproduce, redistribute, or claim to contain UCI
records. Public ranges are declared demonstration assumptions, not values inferred
from a confidential release table.

| Field | Meaning | Unit | Public range/domain | Role |
|---|---|---|---|---|
| `plant_day_id` | Public fixed-roster plant-day identifier | none | unique string | public privacy-unit ID |
| `raw_inflow_m3d` | Daily raw-water inflow | m3/day | 12,000-150,000 | protected numeric |
| `treated_outflow_m3d` | Daily treated-water outflow | m3/day | 9,000-145,000 | protected numeric |
| `backwash_loss_m3d` | Filter or membrane backwash water | m3/day | 150-12,000 | protected numeric |
| `sludge_water_m3d` | Water leaving with sludge handling | m3/day | 100-7,000 | protected numeric |
| `process_feed_m3d` | Main process feed including recycle | m3/day | 10,000-175,000 | protected numeric |
| `recycle_water_m3d` | Internal recycle flow | m3/day | 500-28,000 | protected numeric |
| `aeration_energy_kwh` | Aeration electricity | kWh/day | 1,800-85,000 | protected numeric |
| `pumping_energy_kwh` | Pumping electricity | kWh/day | 500-22,000 | protected numeric |
| `total_energy_kwh` | Total modeled electricity | kWh/day | 2,500-105,000 | protected numeric |
| `treatment_train` | Public technology class | category | conventional, membrane, hybrid | protected category |
| `source_water_class` | Source-water class | category | river, reservoir, groundwater, industrial_blend | protected category |
| `shift_pattern` | Operations staffing pattern | category | day, rotating, continuous | protected category |
| `operating_cost_index` | Synthetic sensitive operating target | index units/day | not released | calibration target |

Category domains and numeric bounds are supplied entirely by configuration. The
generator deliberately includes independent calibration and release rosters.

