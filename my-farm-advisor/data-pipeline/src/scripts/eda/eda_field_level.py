#!/usr/bin/env python3
"""
eda_field_level.py - Field-level EDA for Assignment 2

Compares field boundary geometry, CDL crop rotation, and weather
across Illinois, Iowa, and Nebraska growers (10 fields each).

Outputs static PNG figures to:
  <DATA_PIPELINE_DATA_ROOT>/data-pipeline/eda/field-level/output/{geometry,rotation,weather}/

Usage:
  export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
  python scripts/eda/eda_field_level.py [--categories geometry] [--data-root PATH]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))

from paths import farm_boundary_path, farm_cdl_rotation_path, farm_weather_path  # noqa: E402

sns.set_style("whitegrid")

GROWERS = [
    {"slug": "illinois-grower", "farm": "illinois-grower-illinois", "label": "Illinois"},
    {"slug": "iowa-grower",      "farm": "iowa-grower-iowa",           "label": "Iowa"},
    {"slug": "nebraska-grower",  "farm": "nebraska-grower-nebraska",   "label": "Nebraska"},
]

# Vibrant palette: green (humid east) → gold (central plains) → blue (semi-arid west)
GROWER_COLORS = {"Illinois": "#27AE60", "Iowa": "#F39C12", "Nebraska": "#2980B9"}
GROWER_COLORS_LIST = ["#27AE60", "#F39C12", "#2980B9"]


def _resolve_data_root(args_root: str | None) -> Path:
    if args_root:
        return Path(args_root)
    env_root = os.environ.get("DATA_PIPELINE_DATA_ROOT")
    if env_root:
        return Path(env_root)
    print("ERROR: Set DATA_PIPELINE_DATA_ROOT or pass --data-root", file=sys.stderr)
    sys.exit(1)


def _output_dir(data_root: Path, *subdirs: str) -> Path:
    out = data_root / "data-pipeline" / "eda" / "field-level" / "output"
    for s in subdirs:
        out = out / s
    out.mkdir(parents=True, exist_ok=True)
    return out


# ── Category 1: Field Boundary Geometry ──────────────────────────────

def load_geometry(data_root: Path) -> pd.DataFrame:
    import geopandas as gpd

    records = []
    for g in GROWERS:
        path = farm_boundary_path(g["slug"], g["farm"])
        if not path.exists():
            print(f"  Skipping {g['label']}: {path} not found")
            continue
        gdf = gpd.read_file(path)
        gdf_proj = gdf.to_crs("EPSG:5070")
        area_m2 = gdf_proj.geometry.area
        perimeter_m = gdf_proj.geometry.length

        for idx in range(len(gdf)):
            a = area_m2.iloc[idx]
            p = perimeter_m.iloc[idx]
            compact = (4 * np.pi * a) / (p * p) if p > 0 else 0.0
            records.append({
                "grower": g["label"],
                "field_id": gdf.iloc[idx]["field_id"],
                "area_acres": float(gdf.iloc[idx].get("area_acres", a / 4046.8564224)),
                "area_m2": float(a),
                "perimeter_m": float(p),
                "compactness": compact,
            })
    return pd.DataFrame(records)


def plot_area_histogram(geo_df: pd.DataFrame, out_dir: Path) -> Path:
    fig, axes = plt.subplots(1, 3, figsize=(14, 4), sharex=True, sharey=True)
    growers = ["Illinois", "Iowa", "Nebraska"]
    colors = ["#27AE60", "#F39C12", "#2980B9"]

    for ax, grp, clr in zip(axes, growers, colors):
        subset = geo_df[geo_df["grower"] == grp]["area_acres"]
        sns.histplot(subset, bins=6, kde=True, color=clr, ax=ax, edgecolor="white")
        ax.set_title(f"{grp} (n={len(subset)})", fontsize=11)
        ax.set_xlabel("Area (acres)")
        ax.set_ylabel("Count")

    fig.suptitle("Field Area Distribution by Grower", fontsize=13, fontweight="bold")
    plt.tight_layout()
    path = out_dir / "field_area_histogram.png"
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_compactness_boxplot(geo_df: pd.DataFrame, out_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(8, 5))
    palette = {"Illinois": "#27AE60", "Iowa": "#F39C12", "Nebraska": "#2980B9"}
    order = ["Illinois", "Iowa", "Nebraska"]
    sns.boxplot(data=geo_df, x="grower", y="compactness", palette=palette,
                hue="grower", legend=False, ax=ax, order=order)
    sns.stripplot(data=geo_df, x="grower", y="compactness", color="black",
                  alpha=0.5, jitter=True, size=5, ax=ax, order=order)

    ax.axhline(0.79, color="gray", linestyle="--", alpha=0.4, label="Square (0.79)")
    ax.axhline(0.60, color="gray", linestyle=":", alpha=0.4, label="Irregular (0.60)")
    ax.set_title("Field Shape Compactness by Grower", fontsize=13, fontweight="bold")
    ax.set_xlabel("")
    ax.set_ylabel("Isoperimetric Quotient (4πA / P²)")
    ax.legend(fontsize=9)
    plt.tight_layout()
    path = out_dir / "shape_compactness_boxplot.png"
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_area_vs_perimeter(geo_df: pd.DataFrame, out_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(8, 6))
    colors = {"Illinois": "#27AE60", "Iowa": "#F39C12", "Nebraska": "#2980B9"}

    for grp in ["Illinois", "Iowa", "Nebraska"]:
        subset = geo_df[geo_df["grower"] == grp]
        ax.scatter(subset["area_acres"], subset["perimeter_m"],
                   c=colors[grp], label=grp, alpha=0.7, edgecolors="white", s=60)

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
    path = out_dir / "area_vs_perimeter_scatter.png"
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_field_location_map(data_root: Path, out_dir: Path) -> Path:
    import geopandas as gpd
    import contextily as ctx
    import shapely.geometry

    # ── Load field boundaries with geometry ──
    field_dfs = []
    for g in GROWERS:
        path = farm_boundary_path(g["slug"], g["farm"])
        if not path.exists():
            continue
        gdf = gpd.read_file(path)
        gdf["grower"] = g["label"]
        field_dfs.append(gdf)
    fields = pd.concat(field_dfs, ignore_index=True)
    if fields.empty:
        raise ValueError("No field boundary data")

    # ── Compute per-grower bounding boxes with margin ──
    grower_extents = {}
    for g in GROWERS:
        path = farm_boundary_path(g["slug"], g["farm"])
        if not path.exists():
            continue
        gdf = gpd.read_file(path)
        bounds = gdf.to_crs("EPSG:3857").total_bounds  # [xmin, ymin, xmax, ymax]
        margin = 3000  # meters of padding
        grower_extents[g["label"]] = [
            bounds[0] - margin, bounds[1] - margin,
            bounds[2] + margin, bounds[3] + margin,
        ]

    # ── Load state outlines ──
    shared_root = data_root / "data-pipeline" / "shared"
    states_path = shared_root / "geoadmin" / "l1_states" / "states_usa.geojson"
    states = gpd.read_file(states_path)
    target_states = states[states["state_name"].isin(["Illinois", "Iowa", "Nebraska"])].copy()
    target_states_3857 = target_states.to_crs("EPSG:3857")

    fields_3857 = fields.to_crs("EPSG:3857")
    colors = {"Illinois": "#27AE60", "Iowa": "#F39C12", "Nebraska": "#2980B9"}
    panel_labels = ["Illinois (Iroquois Co.)", "Iowa (Kossuth Co.)", "Nebraska (Buffalo Co.)"]

    # ── 1-panel overview map (small, top) ──
    fig = plt.figure(figsize=(12, 10))
    gs = fig.add_gridspec(4, 3, hspace=0.05, wspace=0.05)

    # Top row: tight panels for each grower
    for col, grp in enumerate(["Illinois", "Iowa", "Nebraska"]):
        ax = fig.add_subplot(gs[0:3, col])
        extent = grower_extents[grp]
        ax.set_xlim(extent[0], extent[2])
        ax.set_ylim(extent[1], extent[3])

        try:
            ctx.add_basemap(ax, crs="EPSG:3857", source=ctx.providers.CartoDB.Positron,
                            alpha=0.6)
        except Exception:
            pass

        subset = fields_3857[fields_3857["grower"] == grp]
        subset.plot(ax=ax, color=colors[grp], edgecolor="white", linewidth=0.3,
                    alpha=0.8)
        ax.set_title(panel_labels[col], fontsize=11, fontweight="bold")
        ax.set_xlabel("")
        ax.set_ylabel("")
        ax.set_xticklabels([])
        ax.set_yticklabels([])

    # Bottom row: overview map spanning full width
    ax_overview = fig.add_subplot(gs[3, :])
    extent_overview = gpd.GeoSeries(
        [shapely.geometry.box(-103, 39.5, -86, 44.5)], crs="EPSG:4326"
    ).to_crs("EPSG:3857").total_bounds
    ax_overview.set_xlim(extent_overview[0], extent_overview[2])
    ax_overview.set_ylim(extent_overview[1], extent_overview[3])

    try:
        ctx.add_basemap(ax_overview, crs="EPSG:3857",
                        source=ctx.providers.CartoDB.Positron, alpha=0.5)
    except Exception:
        pass

    target_states_3857.boundary.plot(ax=ax_overview, color="gray", linewidth=0.8, alpha=0.5)
    for grp in ["Illinois", "Iowa", "Nebraska"]:
        subset = fields_3857[fields_3857["grower"] == grp]
        subset.plot(ax=ax_overview, color=colors[grp], edgecolor="white",
                    linewidth=0.3, alpha=0.7, label=grp)

    # State labels on overview
    for _, row in target_states_3857.iterrows():
        centroid = row.geometry.centroid
        ax_overview.text(centroid.x, centroid.y, row["state_name"],
                         fontsize=9, ha="center", va="center", alpha=0.6,
                         style="italic")

    ax_overview.set_title("Regional Context", fontsize=10, fontweight="bold")
    ax_overview.set_xlabel("")
    ax_overview.set_ylabel("")
    ax_overview.legend(loc="lower right", fontsize=8)

    fig.suptitle("Field Locations Across the Corn Belt Transect",
                 fontsize=14, fontweight="bold")
    fig.subplots_adjust(left=0.02, right=0.98, bottom=0.02, top=0.92, hspace=0.08, wspace=0.05)
    path = out_dir / "field_location_map.png"
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return path


def run_geometry(data_root: Path) -> list[Path]:
    out_dir = _output_dir(data_root, "geometry")
    print("Loading field boundaries...")
    geo_df = load_geometry(data_root)
    if geo_df.empty:
        print("  No geometry data loaded, skipping.")
        return []

    print(f"  Loaded {len(geo_df)} fields across {geo_df['grower'].nunique()} growers")
    print(geo_df.groupby("grower")[["area_acres", "compactness"]].describe().round(3).to_string())

    paths = []
    print("  Plotting area histogram...")
    paths.append(plot_area_histogram(geo_df, out_dir))
    print("  Plotting compactness boxplot...")
    paths.append(plot_compactness_boxplot(geo_df, out_dir))
    print("  Plotting area vs perimeter scatter...")
    paths.append(plot_area_vs_perimeter(geo_df, out_dir))
    print("  Plotting field location map...")
    paths.append(plot_field_location_map(data_root, out_dir))

    return paths


# ── Category 2: CDL Crop Rotation ────────────────────────────────────

def load_rotation(data_root: Path) -> pd.DataFrame:
    records = []
    for g in GROWERS:
        path = farm_cdl_rotation_path(g["slug"], g["farm"])
        if not path.exists():
            print(f"  Skipping {g['label']}: {path} not found")
            continue
        df = pd.read_csv(path)
        df["grower"] = g["label"]
        records.append(df)
    return pd.concat(records, ignore_index=True)


def plot_rotation_diversity(rot_df: pd.DataFrame, out_dir: Path) -> Path:
    counts = rot_df.groupby(["grower", "crop_diversity"]).size().reset_index(name="count")
    order = ["Illinois", "Iowa", "Nebraska"]
    palette = {1: "#E74C3C", 2: "#F39C12", 3: "#27AE60"}

    fig, ax = plt.subplots(figsize=(8, 5))
    sns.barplot(data=counts, x="grower", y="count", hue="crop_diversity",
                palette=palette, ax=ax, order=order)
    ax.set_title("Crop Rotation Diversity by Grower", fontsize=13, fontweight="bold")
    ax.set_xlabel("")
    ax.set_ylabel("Number of Fields")
    ax.legend(title="Crop Diversity",
              labels=["1 crop (continuous)", "2 crops", "3+ crops"])
    plt.tight_layout()
    path = out_dir / "rotation_diversity_bar.png"
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_corn_soy_stacked(rot_df: pd.DataFrame, out_dir: Path) -> Path:
    plot_df = rot_df.copy()
    plot_df["other_years"] = 5 - plot_df["corn_years"] - plot_df["soybean_years"]
    plot_df["field_label"] = plot_df["grower"] + " — " + plot_df["field_id"].str[-8:]
    plot_df = plot_df.sort_values(["grower", "corn_years"], ascending=[True, False])

    fig, ax = plt.subplots(figsize=(9, 8))
    y_pos = range(len(plot_df))
    bar_h = 0.6

    ax.barh(y_pos, plot_df["corn_years"], bar_h, label="Corn", color="#F39C12")
    left = plot_df["corn_years"].values.copy()
    ax.barh(y_pos, plot_df["soybean_years"], bar_h, left=left,
            label="Soybeans", color="#27AE60")
    left += plot_df["soybean_years"].values
    other_mask = plot_df["other_years"] > 0
    if other_mask.any():
        ax.barh(np.array(y_pos)[other_mask], plot_df.loc[other_mask, "other_years"],
                bar_h, left=left[other_mask], label="Other", color="#8E44AD")

    ax.set_yticks(y_pos)
    ax.set_yticklabels(plot_df["field_label"], fontsize=7)
    ax.set_xlabel("Years (2021-2025)")
    ax.set_title("Corn vs Soybean Years per Field", fontsize=13, fontweight="bold")
    ax.legend()

    prev = None
    for i, row in enumerate(plot_df.itertuples()):
        if prev is not None and row.grower != prev:
            ax.axhline(i - 0.5, color="gray", linewidth=0.8, linestyle="--", alpha=0.5)
        prev = row.grower

    plt.tight_layout()
    path = out_dir / "corn_soy_stacked_bar.png"
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_rotation_transition(rot_df: pd.DataFrame, out_dir: Path) -> Path:
    from collections import Counter

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    order = ["Illinois", "Iowa", "Nebraska"]

    for ax, grp in zip(axes, order):
        subset = rot_df[rot_df["grower"] == grp]
        counter = Counter()
        for patterns in subset["rotation_patterns"]:
            for pair in patterns.split("; "):
                counter[pair] += 1

        if not counter:
            ax.set_title(f"{grp} — no data")
            continue

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

    fig.suptitle("Crop Rotation Transition Matrices", fontsize=13, fontweight="bold")
    plt.tight_layout()
    path = out_dir / "rotation_transition_heatmap.png"
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return path


def run_rotation(data_root: Path) -> list[Path]:
    out_dir = _output_dir(data_root, "rotation")
    print("Loading crop rotation data...")
    rot_df = load_rotation(data_root)
    if rot_df.empty:
        print("  No rotation data loaded, skipping.")
        return []

    print(f"  Loaded {len(rot_df)} fields across {rot_df['grower'].nunique()} growers")
    print(rot_df.groupby("grower")["crop_diversity"].value_counts().to_string())

    paths = []
    print("  Plotting rotation diversity...")
    paths.append(plot_rotation_diversity(rot_df, out_dir))
    print("  Plotting corn vs soy stacked bar...")
    paths.append(plot_corn_soy_stacked(rot_df, out_dir))
    print("  Plotting rotation transition matrix...")
    paths.append(plot_rotation_transition(rot_df, out_dir))

    return paths


# ── Category 3: Weather ──────────────────────────────────────────────

def load_weather(data_root: Path) -> pd.DataFrame:
    records = []
    for g in GROWERS:
        farm_root = farm_boundary_path(g["slug"], g["farm"]).parent.parent
        fields_dir = farm_root / "fields"
        weather_files = sorted(fields_dir.glob("*/weather/daily_weather.csv"))
        loaded = 0
        for wf in weather_files:
            df = pd.read_csv(wf)
            if len(df) == 0:
                continue
            df["date"] = pd.to_datetime(df["date"])
            df["grower"] = g["label"]
            records.append(df)
            loaded += 1
        print(f"  Loaded {loaded} fields for {g['label']}")
    return pd.concat(records, ignore_index=True)


def plot_growing_season_precip(weather_df: pd.DataFrame, out_dir: Path) -> Path:
    w = weather_df.copy()
    w["year"] = w["date"].dt.year
    w["month"] = w["date"].dt.month
    gs = w[w["month"].between(4, 9)]
    gs_total = gs.groupby(["grower", "year", "field_id"])["PRECTOTCORR"].sum().reset_index()

    fig, ax = plt.subplots(figsize=(10, 6))
    order = ["Illinois", "Iowa", "Nebraska"]
    palette = {2021: "#D6EAF8", 2022: "#85C1E9", 2023: "#3498DB",
               2024: "#2E86C1", 2025: "#1A5276"}
    sns.boxplot(data=gs_total, x="grower", y="PRECTOTCORR", hue="year",
                palette=palette, ax=ax, order=order)
    ax.set_title("Growing Season Total Precipitation (Apr-Sep)", fontsize=13, fontweight="bold")
    ax.set_xlabel("")
    ax.set_ylabel("Total Precipitation (mm)")
    ax.legend(title="Year")
    plt.tight_layout()
    path = out_dir / "growing_season_precip.png"
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_growing_season_gdd(weather_df: pd.DataFrame, out_dir: Path) -> Path:
    w = weather_df.copy()
    w["year"] = w["date"].dt.year
    w["month"] = w["date"].dt.month
    w["gdd"] = ((w["T2M_MAX"] + w["T2M_MIN"]) / 2 - 10).clip(lower=0)
    gs = w[w["month"].between(4, 9)]
    gs_gdd = gs.groupby(["grower", "year", "field_id"])["gdd"].sum().reset_index()

    fig, ax = plt.subplots(figsize=(10, 6))
    order = ["Illinois", "Iowa", "Nebraska"]
    palette = {2021: "#FDEBD0", 2022: "#F5B041", 2023: "#EB984E",
               2024: "#E67E22", 2025: "#CA6F1E"}
    sns.boxplot(data=gs_gdd, x="grower", y="gdd", hue="year",
                palette=palette, ax=ax, order=order)
    ax.set_title("Growing Season GDD (Base 10°C, Apr-Sep)", fontsize=13, fontweight="bold")
    ax.set_xlabel("")
    ax.set_ylabel("GDD (°C-days)")
    ax.legend(title="Year")
    plt.tight_layout()
    path = out_dir / "growing_season_gdd.png"
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_monthly_precip_climatology(weather_df: pd.DataFrame, out_dir: Path) -> Path:
    w = weather_df.copy()
    w["month"] = w["date"].dt.month
    monthly_total = w.groupby(["grower", "field_id", "month"])["PRECTOTCORR"].sum().reset_index()
    clim = monthly_total.groupby(["grower", "month"]).agg(
        mean_precip=("PRECTOTCORR", "mean"),
        std_precip=("PRECTOTCORR", "std"),
    ).reset_index()

    fig, ax = plt.subplots(figsize=(10, 6))
    colors = {"Illinois": "#27AE60", "Iowa": "#F39C12", "Nebraska": "#2980B9"}
    order = ["Illinois", "Iowa", "Nebraska"]

    for grp in order:
        sub = clim[clim["grower"] == grp]
        ax.plot(sub["month"], sub["mean_precip"], "o-", color=colors[grp],
                label=grp, linewidth=2)
        ax.fill_between(sub["month"],
                        sub["mean_precip"] - sub["std_precip"],
                        sub["mean_precip"] + sub["std_precip"],
                        color=colors[grp], alpha=0.15)

    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(["Jan","Feb","Mar","Apr","May","Jun",
                        "Jul","Aug","Sep","Oct","Nov","Dec"], rotation=45)
    ax.set_ylabel("Mean Monthly Precipitation (mm)")
    ax.set_title("Monthly Precipitation Climatology (2021-2025)", fontsize=13, fontweight="bold")
    ax.legend()
    plt.tight_layout()
    path = out_dir / "monthly_precip_climatology.png"
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return path


def run_weather(data_root: Path) -> list[Path]:
    out_dir = _output_dir(data_root, "weather")
    print("Loading per-field weather data...")
    weather_df = load_weather(data_root)
    if weather_df.empty:
        print("  No weather data loaded, skipping.")
        return []

    fields_per_grower = weather_df.groupby("grower")["field_id"].nunique()
    years = weather_df["date"].dt.year.nunique()
    print(f"  Loaded {len(weather_df)} rows, {fields_per_grower.to_dict()}, {years} years")

    paths = []
    print("  Plotting growing season precipitation...")
    paths.append(plot_growing_season_precip(weather_df, out_dir))
    print("  Plotting growing season GDD...")
    paths.append(plot_growing_season_gdd(weather_df, out_dir))
    print("  Plotting monthly precipitation climatology...")
    paths.append(plot_monthly_precip_climatology(weather_df, out_dir))

    return paths


# ── Main ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Field-level EDA for Assignment 2")
    parser.add_argument(
        "--data-root",
        default=None,
        help="Override DATA_PIPELINE_DATA_ROOT (default: use env var)",
    )
    parser.add_argument(
        "--categories",
        nargs="+",
        choices=["geometry", "rotation", "weather"],
        default=["geometry", "rotation", "weather"],
        help="Categories to run (default: all)",
    )
    args = parser.parse_args()

    data_root = _resolve_data_root(args.data_root)
    print(f"Data root: {data_root}")

    all_paths: list[Path] = []
    category_runners = {
        "geometry": run_geometry,
        "rotation": run_rotation,
        "weather": run_weather,
    }

    for cat in args.categories:
        print(f"\n── Category: {cat} {'─' * 40}")
        paths = category_runners[cat](data_root)
        all_paths.extend(paths)

    print(f"\n{'=' * 60}")
    print(f"Done — {len(all_paths)} output(s) generated:")
    for p in all_paths:
        print(f"  ✓ {p}")


if __name__ == "__main__":
    main()
