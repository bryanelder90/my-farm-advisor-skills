# Field-Season Dashboard Guide

Build a single aligned 5-panel dashboard that shows NDVI, weather, and CDL crop information for one field in one growing season.

## When to use

You need a quick visual summary of what happened in a specific field-year. The dashboard overlays Sentinel NDVI, daily precipitation, temperature extremes, cumulative GDD, and a crop-stage progress bar onto a shared calendar axis so you can read the season's story from one figure.

## Inputs

| Source | Location (under data-pipeline runtime) | Required |
|--------|----------------------------------------|----------|
| Field boundary | `growers/<grower>/farms/<farm>/fields/<field>/boundary/field_boundary.geojson` | Yes |
| Sentinel NDVI | `growers/<grower>/farms/<farm>/fields/<field>/satellite/sentinel/<year>/<scene>/<scene>_ndvi.tif` | Yes |
| Daily weather | `growers/<grower>/farms/<farm>/derived/tables/<farm>_weather_2021_2025.csv` | Yes |
| CDL composition | `growers/<grower>/farms/<farm>/derived/tables/<farm>_cdl_2021_2025_full_composition.csv` | Yes |

## Dashboard panels (top to bottom)

1. **Crop-stage bar** — Colored segments showing typical growth-stage GDD windows (corn, soybean, or winter wheat). A red marker shows actual season progress. CDL crop label and total GDD are displayed.

2. **NDVI** — Mean ± interquartile range from Sentinel-2 NDVI rasters, masked to the field boundary. Peak NDVI annotated with value and date.

3. **Precipitation** — Daily bars (mm) with cumulative line overlay. Total seasonal precipitation annotated.

4. **Temperature** — Filled Tmax–Tmin daily range. 0°C freeze reference line. Hottest and coldest days annotated.

5. **Cumulative GDD** — Running sum of growing-degree days (base 10°C). Growth-stage threshold lines (silking, maturity, etc.) shown in crop-appropriate colors.

A caption below the panels summarizes the key seasonal numbers.

## Usage

### Prerequisites

- `DATA_PIPELINE_DATA_ROOT` set to the runtime root (e.g. `/home/coder/my-farm-advisor-runtime`)
- Data-pipeline venv at `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv`
- A field that has Sentinel NDVI, daily weather, and CDL data for the target year

### Command

Run from the runtime source copy:

```bash
export DATA_PIPELINE_DATA_ROOT=/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/eda/eda_field_season_dashboard.py \
  --grower-slug nebraska-grower \
  --farm-slug nebraska-grower-nebraska \
  --field-slug osm-1352429400 \
  --year 2025
```

### Parameters

| Flag | Default | Description |
|------|---------|-------------|
| `--grower-slug` | `nebraska-grower` | Grower slug |
| `--farm-slug` | `nebraska-grower-nebraska` | Farm slug |
| `--field-slug` | `osm-1352429400` | Field slug |
| `--year` | `2025` | Growing season year |
| `--output-dir` | runtime default | Override output directory |

### Output

A single PNG at `eda/field-season-dashboard/output/<field>_<year>_dashboard.png` (300 dpi).

## Example

The default parameters produce a 2025 dashboard for Nebraska field `osm-1352429400` (Soybeans, Buffalo County). Try a different year to see the contrast:

```bash
# 2021 was Corn in this field — compare the NDVI and GDD profiles
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/eda/eda_field_season_dashboard.py \
  --field-slug osm-1352429400 --year 2021
```

## Notes

- The crop-stage bar adapts to the CDL crop: corn, soybean, or winter wheat stage thresholds.
- GDD uses base 10°C, standard for corn. The same base is applied for soybeans and wheat.
- NDVI is extracted via zonal statistics masked to the field boundary (rasterio.mask.mask) for accuracy.
- Full-year x-axis (Jan–Dec) captures winter wheat's fall planting and spring green-up.
