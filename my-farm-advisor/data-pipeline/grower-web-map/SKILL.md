# Grower Web Map

Generate a lightweight interactive Leaflet HTML map for each grower, showing field polygon boundaries with clickable metadata popups and a field-list sidebar for zoom-to navigation.

## Quick start

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/generate_grower_map.py \
  --grower-slug illinois-grower
```

Output: `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/grower_map.html`

## Requirements

- The data-pipeline runtime must be installed and have live grower data.
- No additional Python dependencies beyond standard library.
- Leaflet CSS/JS loaded from CDN (internet required at map-open time).
