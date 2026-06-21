# Grower Web Map Subskill Instructions

## Purpose

Generate a self-contained Leaflet HTML map per grower that visualizes field polygon boundaries from the data-pipeline runtime output.

## Runtime contract

- `DATA_PIPELINE_DATA_ROOT` must be set to the runtime root.
- Grower data lives under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower-slug>`.
- The script reads GeoJSON field boundaries and writes an HTML map to the grower directory.

## Usage

Run from the runtime source copy:

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/generate_grower_map.py --grower-slug <grower-slug>
```

## Output

- `growers/<grower-slug>/grower_map.html` — self-contained interactive web map.
- Leaflet JS/CSS loaded from CDN; no external data files embedded.
- Polygon styling: semi-transparent fill, colored stroke, hover highlight.
- Click popup: grower, farm, field name, area, county.
- Field list sidebar: click to zoom to field extent.
