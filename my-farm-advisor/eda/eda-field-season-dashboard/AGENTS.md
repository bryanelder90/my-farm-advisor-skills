# Field-Season Dashboard — Local Instructions

## Purpose

Build a single aligned 5-panel dashboard for one field in one growing season, combining Sentinel NDVI, daily weather, and CDL crop information.

## Safe edit scope

Edits should stay in `eda/eda-field-season-dashboard/` and `data-pipeline/src/scripts/eda/`. Do not change other subskills or data-pipeline infrastructure.

## Key files

- `GUIDE.md` — workflow documentation with example commands
- `../data-pipeline/src/scripts/eda/eda_field_season_dashboard.py` — dashboard generator script

## Quick start

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/eda/eda_field_season_dashboard.py \
  --grower-slug nebraska-grower \
  --farm-slug nebraska-grower-nebraska \
  --field-slug osm-1352429400 \
  --year 2025
```

## Data inputs

- Field boundary: `fields/<field>/boundary/field_boundary.geojson`
- Sentinel NDVI: `fields/<field>/satellite/sentinel/<year>/<scene>/<scene>_ndvi.tif`
- Weather: `farms/<farm>/derived/tables/<farm>_weather_2021_2025.csv`
- CDL: `farms/<farm>/derived/tables/<farm>_cdl_2021_2025_full_composition.csv`

## Runtime contract

- `DATA_PIPELINE_DATA_ROOT` is required.
- Run from the runtime source copy (`${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src`).
- Output goes to `eda/field-season-dashboard/output/` under the runtime base.
