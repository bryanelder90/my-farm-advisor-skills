---
name: eda-field-level
description: Field-level EDA across growers comparing field-boundary geometry, CDL/crop rotation patterns, and weather along the Illinois → Iowa → Nebraska Corn Belt transect. Generates static PNG outputs and summary tables.
version: 1.0.0
author: Boreal Bytes
tags: [eda, field-level, geometry, cdl, crop-rotation, weather, comparison, cross-grower]
---

# Workflow: eda-field-level

## Description

Analyze and compare field-level agricultural data across three Corn Belt growers — Illinois (Iroquois County), Iowa (Kossuth County), and Nebraska (Buffalo County) — with 10 fields each. Produces static visualizations and summary statistics covering three dimensions:

1. **Field boundary geometry** — area, perimeter, and shape compactness
2. **CDL crop rotation** — rotation diversity, corn/soybean year distribution, and rotation pattern frequencies
3. **Weather** — growing season precipitation, GDD, and monthly climatology

## When to Use This Workflow

- **Cross-grower comparison**: Compare field characteristics across the IL→IA→NE transect
- **Field geometry analysis**: Identify shape regimes (irregular, square, circular) and size distributions
- **Rotation pattern analysis**: Quantify rotation diversity and common sequences per region
- **Weather gradient analysis**: Compare precipitation and GDD across the Corn Belt
- **Assignment 2 reporting**: Generate the quantitative EDA figures for a static report

## Prerequisites

```bash
pip install pandas geopandas numpy matplotlib seaborn scipy
```

## Quick Start

```python
from pathlib import Path
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import seaborn as sns

# Load a single grower's field boundaries
DATA = Path("/home/coder/my-farm-advisor-runtime/data-pipeline")
fields = gpd.read_file(
    DATA / "growers/illinois-grower/farms/illinois-grower-illinois/boundary/field_boundaries.geojson"
)

# Quick geometry summary
print(f"Fields: {len(fields)}")
print(fields[["field_id", "area_acres"]].describe())
```

## Common Tasks

### Category 1: Field Boundary Geometry

#### Task 1: Load field boundaries and compute shape metrics

**What**: Load all three growers' boundaries, project to equal-area CRS (EPSG:5070), and compute compactness (isoperimetric quotient).

**When to use**: Starting point for any geometry analysis.

**Code**:

```python
from pathlib import Path
import geopandas as gpd
import pandas as pd
import numpy as np

DATA = Path("/home/coder/my-farm-advisor-runtime/data-pipeline")

GROWERS = [
    {"slug": "illinois-grower", "farm": "illinois-grower-illinois", "label": "Illinois"},
    {"slug": "iowa-grower",      "farm": "iowa-grower-iowa",           "label": "Iowa"},
    {"slug": "nebraska-grower",  "farm": "nebraska-grower-nebraska",   "label": "Nebraska"},
]

records = []
for g in GROWERS:
    path = DATA / "growers" / g["slug"] / "farms" / g["farm"] / "boundary" / "field_boundaries.geojson"
    gdf = gpd.read_file(path)

    # Project to equal-area for accurate area/perimeter
    gdf_proj = gdf.to_crs("EPSG:5070")
    area_m2 = gdf_proj.geometry.area
    perimeter_m = gdf_proj.geometry.length

    for _, row in gdf.iterrows():
        idx = row.name
        a_m2 = area_m2.iloc[idx]
        p_m = perimeter_m.iloc[idx]
        compactness = (4 * np.pi * a_m2) / (p_m * p_m) if p_m > 0 else 0
        records.append({
            "grower": g["label"],
            "field_id": row["field_id"],
            "area_acres": row.get("area_acres", a_m2 / 4046.8564224),
            "area_m2": a_m2,
            "perimeter_m": p_m,
            "compactness": compactness,
        })

geo_df = pd.DataFrame(records)
print(geo_df.groupby("grower")[["area_acres", "compactness"]].describe().round(3))
```

#### Task 2: Visualize field area distribution across growers

**What**: Histogram with KDE overlay of field area in acres, faceted by grower.

**When to use**: Compare field size regimes across regions.

**Code**:

```python
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import pandas as pd
import numpy as np

# Assume geo_df from Task 1
fig, axes = plt.subplots(1, 3, figsize=(14, 4), sharex=True, sharey=True)
growers = ["Illinois", "Iowa", "Nebraska"]
    colors = ["#27AE60", "#F39C12", "#2980B9"]  # green (IL), gold (IA), blue (NE)

for ax, grp, clr in zip(axes, growers, colors):
    subset = geo_df[geo_df["grower"] == grp]["area_acres"]
    sns.histplot(subset, bins=6, kde=True, color=clr, ax=ax, edgecolor="white")
    ax.set_title(f"{grp} (n={len(subset)})", fontsize=11)
    ax.set_xlabel("Area (acres)")
    ax.set_ylabel("Count")

plt.suptitle("Field Area Distribution by Grower", fontsize=13, fontweight="bold")
plt.tight_layout()
plt.savefig(
    "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-level/output/geometry/field_area_histogram.png",
    dpi=300, bbox_inches="tight",
)
plt.close()
```

#### Task 3: Compare shape compactness across growers

**What**: Box plot of the isoperimetric quotient (4πA/P²) by grower. Values near 1 = perfect circle, ~0.79 = square, lower = irregular.

**When to use**: Quantify shape regularity differences — IL irregular field boundaries vs IA grid squares vs NE center-pivot circles.

**Code**:

```python
fig, ax = plt.subplots(figsize=(8, 5))
palette = {"Illinois": "#27AE60", "Iowa": "#F39C12", "Nebraska": "#2980B9"}
sns.boxplot(data=geo_df, x="grower", y="compactness", palette=palette, ax=ax,
            order=["Illinois", "Iowa", "Nebraska"])
sns.stripplot(data=geo_df, x="grower", y="compactness", color="black",
              alpha=0.5, jitter=True, size=5, ax=ax,
              order=["Illinois", "Iowa", "Nebraska"])

# Reference lines
ax.axhline(0.79, color="gray", linestyle="--", alpha=0.4, label="Square (0.79)")
ax.axhline(0.60, color="gray", linestyle=":", alpha=0.4, label="Irregular (0.60)")
ax.set_title("Field Shape Compactness by Grower", fontsize=13, fontweight="bold")
ax.set_xlabel("")
ax.set_ylabel("Isoperimetric Quotient (4πA / P²)")
ax.legend(fontsize=9)
plt.tight_layout()
plt.savefig(
    "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-level/output/geometry/shape_compactness_boxplot.png",
    dpi=300, bbox_inches="tight",
)
plt.close()
```

#### Task 4: Explore area vs perimeter relationship

**What**: Scatter plot of field area vs perimeter, colored by grower, with theoretical shape lines (circle, square) overlaid.

**When to use**: See how each grower's fields cluster in shape-space — IL irregular, IA square, NE circular.

**Code**:

```python
import numpy as np

fig, ax = plt.subplots(figsize=(8, 6))
colors = {"Illinois": "#27AE60", "Iowa": "#F39C12", "Nebraska": "#2980B9"}
for grp in ["Illinois", "Iowa", "Nebraska"]:
    subset = geo_df[geo_df["grower"] == grp]
    ax.scatter(subset["area_acres"], subset["perimeter_m"],
               c=colors[grp], label=grp, alpha=0.7, edgecolors="white", s=60)

# Theoretical shape lines (circle: P = 2*sqrt(π*A), square: P = 4*sqrt(A))
area_range = np.linspace(1, 700, 100)
ax.plot(area_range, 2 * np.sqrt(np.pi * area_range * 4046.8564224),
        "k--", alpha=0.3, label="Circle")
ax.plot(area_range, 4 * np.sqrt(area_range * 4046.8564224),
        "k:", alpha=0.3, label="Square")
ax.set_xlabel("Area (acres)")
ax.set_ylabel("Perimeter (m)")
ax.set_title("Field Area vs Perimeter", fontsize=13, fontweight="bold")
ax.legend()
plt.tight_layout()
plt.savefig(
    "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-level/output/geometry/area_vs_perimeter_scatter.png",
    dpi=300, bbox_inches="tight",
)
plt.close()
```

#### Task 5: Create a geospatial field location map

**What**: A map of all 30 field polygons across the three growers, with state outlines and a basemap for geographic context.

**When to use**: Show the geographic transect — Illinois (east, humid) → Iowa (central) → Nebraska (west, semi-arid). Provides spatial context for the precipitation and rotation diversity gradients.

**Code**:

```python
import geopandas as gpd
import contextily as ctx
import shapely.geometry
import matplotlib.pyplot as plt

DATA = Path("/home/coder/my-farm-advisor-runtime/data-pipeline")

GROWERS = [
    {"slug": "illinois-grower", "farm": "illinois-grower-illinois", "label": "Illinois"},
    {"slug": "iowa-grower",      "farm": "iowa-grower-iowa",           "label": "Iowa"},
    {"slug": "nebraska-grower",  "farm": "nebraska-grower-nebraska",   "label": "Nebraska"},
]

# Load field boundaries
field_dfs = []
for g in GROWERS:
    path = DATA / "growers" / g["slug"] / "farms" / g["farm"] / "boundary" / "field_boundaries.geojson"
    gdf = gpd.read_file(path)
    gdf["grower"] = g["label"]
    field_dfs.append(gdf)
fields = pd.concat(field_dfs, ignore_index=True)

# Load state outlines
states = gpd.read_file(DATA / "shared" / "geoadmin" / "l1_states" / "states_usa.geojson")
target_states = states[states["state_name"].isin(["Illinois", "Iowa", "Nebraska"])]

# Project to Web Mercator for contextily
target_states_3857 = target_states.to_crs("EPSG:3857")
fields_3857 = fields.to_crs("EPSG:3857")

fig, ax = plt.subplots(figsize=(12, 7))

# Set extent to cover all 3 counties with margin
extent = shapely.geometry.box(-100.5, 40.0, -86.5, 44.0)
extent_3857 = gpd.GeoSeries([extent], crs="EPSG:4326").to_crs("EPSG:3857").total_bounds
ax.set_xlim(extent_3857[0], extent_3857[2])
ax.set_ylim(extent_3857[1], extent_3857[3])

# Basemap
ctx.add_basemap(ax, crs="EPSG:3857", source=ctx.providers.CartoDB.Positron, alpha=0.7)

# State outlines
target_states_3857.boundary.plot(ax=ax, color="gray", linewidth=0.8, alpha=0.5)

# Fields by grower
colors = {"Illinois": "#27AE60", "Iowa": "#F39C12", "Nebraska": "#2980B9"}
for grp in ["Illinois", "Iowa", "Nebraska"]:
    subset = fields_3857[fields_3857["grower"] == grp]
    subset.plot(ax=ax, color=colors[grp], edgecolor="white", linewidth=0.3, alpha=0.7, label=grp)

# Grower labels
for g in GROWERS:
    path = DATA / "growers" / g["slug"] / "farms" / g["farm"] / "boundary" / "field_boundaries.geojson"
    gdf = gpd.read_file(path)
    centroid = gdf.to_crs("EPSG:3857").geometry.centroid
    ax.text(centroid.x.mean(), centroid.y.mean(), g["label"],
            fontsize=10, fontweight="bold", ha="center", va="bottom",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="gray", alpha=0.85))

ax.set_title("Field Locations Across the Corn Belt Transect", fontsize=13, fontweight="bold")
ax.set_xlabel("")
ax.set_ylabel("")
ax.legend(loc="lower right")
plt.tight_layout()
plt.savefig(
    "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-level/output/geometry/field_location_map.png",
    dpi=300, bbox_inches="tight",
)
plt.close()
```

### Category 2: CDL Crop Rotation

#### Task 6: Analyze crop rotation diversity

**What**: Bar chart counting fields by rotation diversity (1=continuous, 2=two-crop, 3=three+-crop) per grower.

**When to use**: Compare rotation complexity — IL and IA are mostly corn-soy (diversity=2), NE has more wheat-inclusive rotations (diversity=3).

**Code**:

```python
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

DATA = Path("/home/coder/my-farm-advisor-runtime/data-pipeline")

GROWERS = [
    {"slug": "illinois-grower", "farm": "illinois-grower-illinois", "label": "Illinois"},
    {"slug": "iowa-grower",      "farm": "iowa-grower-iowa",           "label": "Iowa"},
    {"slug": "nebraska-grower",  "farm": "nebraska-grower-nebraska",   "label": "Nebraska"},
]

rotations = []
for g in GROWERS:
    path = (DATA / "growers" / g["slug"] / "farms" / g["farm"]
            / "derived" / "tables" / f"{g['farm'].replace('-', '_')}_crop_rotation.csv")
    df = pd.read_csv(path)
    df["grower"] = g["label"]
    rotations.append(df)

rot_df = pd.concat(rotations, ignore_index=True)

# Count fields per diversity level per grower
diversity_counts = rot_df.groupby(["grower", "crop_diversity"]).size().reset_index(name="count")

fig, ax = plt.subplots(figsize=(8, 5))
sns.barplot(data=diversity_counts, x="grower", y="count", hue="crop_diversity",
            palette="Set2", ax=ax, order=["Illinois", "Iowa", "Nebraska"])
ax.set_title("Crop Rotation Diversity by Grower", fontsize=13, fontweight="bold")
ax.set_xlabel("")
ax.set_ylabel("Number of Fields")
ax.legend(title="Crop Diversity", labels=["1 crop", "2 crops", "3+ crops"])
plt.tight_layout()
plt.savefig(
    "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-level/output/rotation/rotation_diversity_bar.png",
    dpi=300, bbox_inches="tight",
)
plt.close()
```

#### Task 7: Visualize corn-soybean year distribution

**What**: Horizontal stacked bar showing corn_years and soybean_years per field, grouped and colored by grower.

**When to use**: Identify continuous corn fields (corn_years=5) vs classic rotation (3 corn, 2 soy) within each grower.

**Code**:

```python
fig, ax = plt.subplots(figsize=(10, 8))
rot_df["field_label"] = rot_df["grower"] + " — " + rot_df["field_id"].str[-8:]

# Sort by grower then corn_years descending
rot_df = rot_df.sort_values(["grower", "corn_years"], ascending=[True, False])
y_pos = range(len(rot_df))

ax.barh(y_pos, rot_df["corn_years"], height=0.6, label="Corn", color="#F39C12")
ax.barh(y_pos, rot_df["soybean_years"], height=0.6, left=rot_df["corn_years"],
        label="Soybeans", color="#27AE60")

ax.set_yticks(y_pos)
ax.set_yticklabels(rot_df["field_label"], fontsize=7)
ax.set_xlabel("Years (2021-2025)")
ax.set_title("Corn vs Soybean Years per Field", fontsize=13, fontweight="bold")
ax.legend()
# Draw grower separators
prev_grower = None
for i, (idx, row) in enumerate(rot_df.iterrows()):
    if prev_grower is not None and row["grower"] != prev_grower:
        ax.axhline(i - 0.5, color="gray", linewidth=0.8, linestyle="--", alpha=0.5)
    prev_grower = row["grower"]

plt.tight_layout()
plt.savefig(
    "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-level/output/rotation/corn_soy_stacked_bar.png",
    dpi=300, bbox_inches="tight",
)
plt.close()
```

#### Task 8: Compare rotation transition patterns across growers

**What**: Row-normalized heatmap of crop→crop transition frequencies for each grower. Built by parsing the `rotation_patterns` column (e.g., `"Corn → Soybeans; Soybeans → Corn"`) and counting each pair.

**When to use**: Compare rotation *dynamics* — IL and IA show tight Corn↔Soybeans loops, NE shows a more distributed graph with Winter Wheat and Forest transitions.

**Code**:

```python
from collections import Counter

fig, axes = plt.subplots(1, 3, figsize=(15, 5))
order = ["Illinois", "Iowa", "Nebraska"]

for ax, grp in zip(axes, order):
    subset = rot_df[rot_df["grower"] == grp]
    counter = Counter()
    for patterns in subset["rotation_patterns"]:
        for pair in patterns.split("; "):
            counter[pair] += 1

    pairs = list(counter.keys())
    from_crops = sorted(set(p.split(" → ")[0] for p in pairs))
    to_crops = sorted(set(p.split(" → ")[1] for p in pairs))
    all_crops = sorted(set(from_crops + to_crops))

    matrix = pd.DataFrame(0, index=all_crops, columns=all_crops, dtype=float)
    for pair, count in counter.items():
        frm, to = pair.split(" → ")
        matrix.loc[frm, to] = count

    matrix = matrix.div(matrix.sum(axis=1), axis=0).fillna(0)

    sns.heatmap(matrix, annot=True, fmt=".2f", cmap="YlGn",
                ax=ax, cbar_kws={"shrink": 0.6, "label": "Transition probability"},
                vmin=0, vmax=1, linewidths=0.5)
    ax.set_title(f"{grp} (n={len(subset)} fields)", fontsize=11, fontweight="bold")
    ax.set_xlabel("To crop")
    ax.set_ylabel("From crop")

plt.suptitle("Crop Rotation Transition Matrices", fontsize=13, fontweight="bold")
plt.tight_layout()
plt.savefig(
    "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-level/output/rotation/rotation_transition_heatmap.png",
    dpi=300, bbox_inches="tight",
)
plt.close()
```

### Category 3: Weather

#### Task 9: Plot growing season precipitation

**What**: Box plot of growing season (April-September) total precipitation per year per grower.

**When to use**: Compare the precip gradient — Illinois wettest (~500-700 mm), Iowa moderate (~400-600 mm), Nebraska driest (~300-450 mm).

**Note**: Per-field weather data is available for all 10 Nebraska fields, but only 3 fields each in Illinois and Iowa (weather download for expanded fields is pending). The plot still shows the gradient clearly.

**Code**:

```python
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

DATA = Path("/home/coder/my-farm-advisor-runtime/data-pipeline")

GROWERS = [
    {"slug": "illinois-grower", "farm": "illinois-grower-illinois", "label": "Illinois"},
    {"slug": "iowa-grower",      "farm": "iowa-grower-iowa",           "label": "Iowa"},
    {"slug": "nebraska-grower",  "farm": "nebraska-grower-nebraska",   "label": "Nebraska"},
]

weather_records = []
for g in GROWERS:
    farm_root = DATA / "growers" / g["slug"] / "farms" / g["farm"]
    for wf in sorted(farm_root.glob("fields/*/weather/daily_weather.csv")):
        df_i = pd.read_csv(wf)
        if len(df_i) == 0:
            continue
        df_i["date"] = pd.to_datetime(df_i["date"])
        df_i["grower"] = g["label"]
        weather_records.append(df_i)

weather_df = pd.concat(weather_records, ignore_index=True)
weather_df["year"] = weather_df["date"].dt.year
weather_df["month"] = weather_df["date"].dt.month

gs = weather_df[weather_df["month"].between(4, 9)]
gs_total = gs.groupby(["grower", "year", "field_id"])["PRECTOTCORR"].sum().reset_index()

fig, ax = plt.subplots(figsize=(10, 6))
sns.boxplot(data=gs_total, x="grower", y="PRECTOTCORR", hue="year",
            palette="Blues", ax=ax, order=["Illinois", "Iowa", "Nebraska"])
ax.set_title("Growing Season Total Precipitation (Apr-Sep)", fontsize=13, fontweight="bold")
ax.set_xlabel("")
ax.set_ylabel("Total Precipitation (mm)")
ax.legend(title="Year")
plt.tight_layout()
plt.savefig(
    "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-level/output/weather/growing_season_precip.png",
    dpi=300, bbox_inches="tight",
)
plt.close()
```

#### Task 10: Plot growing season GDD

**What**: Box plot of growing season growing degree days (base 10°C) per year per grower.

**When to use**: Compare thermal regime — GDD follows the same IL→IA→NE gradient as precipitation.

**Code**:

```python
weather_df = weather_df  # reuse from Task 8
weather_df["gdd"] = ((weather_df["T2M_MAX"] + weather_df["T2M_MIN"]) / 2 - 10).clip(lower=0)
gs = weather_df[weather_df["month"].between(4, 9)]
gs_gdd = gs.groupby(["grower", "year", "field_id"])["gdd"].sum().reset_index()

fig, ax = plt.subplots(figsize=(10, 6))
sns.boxplot(data=gs_gdd, x="grower", y="gdd", hue="year",
            palette="Oranges", ax=ax, order=["Illinois", "Iowa", "Nebraska"])
ax.set_title("Growing Season GDD (Base 10°C, Apr-Sep)", fontsize=13, fontweight="bold")
ax.set_xlabel("")
ax.set_ylabel("GDD (°C-days)")
ax.legend(title="Year")
plt.tight_layout()
plt.savefig(
    "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-level/output/weather/growing_season_gdd.png",
    dpi=300, bbox_inches="tight",
)
plt.close()
```

#### Task 11: Create monthly precipitation climatology comparison

**What**: Line plot of 5-year mean monthly precipitation for each grower, with shaded ±1σ envelope.

**When to use**: Compare seasonal timing — IL has steady summer rain, NE has sharper May-Jun peak with drier July-Aug.

**Code**:

```python
weather_df["month"] = weather_df["date"].dt.month  # reuse from Task 8
monthly_total = weather_df.groupby(["grower", "field_id", "month"])["PRECTOTCORR"].sum().reset_index()
clim_stats = monthly_total.groupby(["grower", "month"]).agg(
    mean_precip=("PRECTOTCORR", "mean"),
    std_precip=("PRECTOTCORR", "std"),
).reset_index()

fig, ax = plt.subplots(figsize=(10, 6))
colors = {"Illinois": "#27AE60", "Iowa": "#F39C12", "Nebraska": "#2980B9"}
for grp in ["Illinois", "Iowa", "Nebraska"]:
    sub = clim_stats[clim_stats["grower"] == grp]
    ax.plot(sub["month"], sub["mean_precip"], "o-", color=colors[grp], label=grp, linewidth=2)
    ax.fill_between(sub["month"], sub["mean_precip"] - sub["std_precip"],
                     sub["mean_precip"] + sub["std_precip"],
                     color=colors[grp], alpha=0.15)

ax.set_xticks(range(1, 13))
ax.set_xticklabels(["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],
                   rotation=45)
ax.set_ylabel("Mean Monthly Precipitation (mm)")
ax.set_title("Monthly Precipitation Climatology (2021-2025)", fontsize=13, fontweight="bold")
ax.legend()
plt.tight_layout()
plt.savefig(
    "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-level/output/weather/monthly_precip_climatology.png",
    dpi=300, bbox_inches="tight",
)
plt.close()
```

## Complete Example

### Full Field-Level EDA Workflow

For a complete run that processes all three categories and produces all 10 visualizations plus a summary table, use the companion script:

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/eda/eda_field_level.py
```

The script produces:

```
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-level/output/
├── geometry/
│   ├── field_area_histogram.png
│   ├── shape_compactness_boxplot.png
│   ├── area_vs_perimeter_scatter.png
│   └── field_location_map.png
├── rotation/
│   ├── rotation_diversity_bar.png
│   ├── corn_soy_stacked_bar.png
│   └── rotation_transition_heatmap.png
└── weather/
    ├── growing_season_precip.png
    ├── growing_season_gdd.png
    └── monthly_precip_climatology.png
```

Run `--help` for options:

```bash
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/eda/eda_field_level.py --help
```

## Best Practices

### Workflow Order

- Start with geometry (Category 1): it requires only boundary data and establishes the field-level frame
- Add rotation (Category 2) once geometry is validated — the field_id key links both datasets
- Add weather (Category 3) last — it has the most data volume and benefits from field_id verification

### Output Conventions

- Use `<DATA_PIPELINE_DATA_ROOT>/data-pipeline/eda/field-level/output/` as the canonical output root
- Place each category's outputs in its own subdirectory (`geometry/`, `rotation/`, `weather/`)
- Save figures at 300 dpi PNG with `bbox_inches='tight'`
- Close plot handles with `plt.close()` to avoid memory leaks in batch runs

### Data Linking

All three datasets link through `field_id` — verify that the same field_ids exist across boundaries, rotation, and weather tables before attempting cross-category correlations.

### Weather Coverage Note

Per-field daily weather data is complete for all 10 Nebraska fields, but only the original 3 fields have weather data in Illinois and Iowa (the 7 expanded fields' weather download is pending). Weather visualizations for IL and IA are based on fewer data points but still represent the correct climate signal for those counties.

## Resources

- [Isoperimetric quotient](https://en.wikipedia.org/wiki/Isoperimetric_inequality)
- [USDA CDL](https://www.nass.usda.gov/Research_and_Science/Cropland/SARS1a.php)
- [NASA POWER](https://power.larc.nasa.gov/)
- [EPSG:5070](https://epsg.io/5070) — Conus Albers Equal Area projection
