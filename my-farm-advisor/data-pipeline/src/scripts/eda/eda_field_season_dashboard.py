#!/usr/bin/env python3
"""Aligned field-season mini-dashboard: NDVI, weather, CDL for one field-year."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

import geopandas as gpd
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from matplotlib.patches import FancyBboxPatch
from rasterio.mask import mask as rio_mask
from shapely.geometry import mapping

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))
from paths import (  # pyright: ignore[reportMissingImports]
    DATA_ROOT,
    farm_cdl_full_composition_path,
    farm_cdl_rotation_path,
    farm_weather_path,
    field_boundary_path,
    field_dir,
)

# ── Colour palette ──────────────────────────────────────────
C_NDVI = "#27AE60"
C_PRECIP = "#2980B9"
C_TEMP = "#E67E22"
C_TEMP_HOT = "#C0392B"
C_TEMP_COLD = "#3498DB"
C_GDD = "#F39C12"
C_CROP = "#8E44AD"
C_BG = "#FAFAF5"
C_GRID = "#E0E0D8"
C_ANNOT = "#2C3E50"

# Growing-degree day base temperature (celsius)
GDD_BASE = 10.0

# Typical growth-stage GDD thresholds for corn (base 10C)
CORN_STAGES = [
    ("Planting", 0, "#A8D5BA"),
    ("Emergence", 120, "#7ABE90"),
    ("V6", 400, "#5DAF6B"),
    ("V12", 700, "#3FA04A"),
    ("Silking", 1400, "#F1C40F"),
    ("Blister", 1700, "#E67E22"),
    ("Dough", 2000, "#D35400"),
    ("Dent", 2400, "#A04000"),
    ("Maturity", 2700, "#6C3483"),
]

# Typical growth-stage GDD thresholds for soybeans (base 10C)
SOYBEAN_STAGES = [
    ("Planting", 0, "#A8D5BA"),
    ("Emergence", 130, "#7ABE90"),
    ("V6", 350, "#5DAF6B"),
    ("R1 (Bloom)", 700, "#F1C40F"),
    ("R3 (Pod)", 1100, "#E67E22"),
    ("R5 (Seed)", 1600, "#D35400"),
    ("R7 (Maturity)", 2350, "#6C3483"),
]

WHEAT_STAGES = [
    ("Planting (fall)", 0, "#A8D5BA"),
    ("Emergence", 150, "#7ABE90"),
    ("Tillering", 400, "#5DAF6B"),
    ("Stem Elongation", 800, "#3FA04A"),
    ("Heading", 1200, "#F1C40F"),
    ("Flowering", 1500, "#E67E22"),
    ("Grain Fill", 1900, "#D35400"),
    ("Maturity", 2200, "#6C3483"),
]


def _stage_lookup(crop_name: str) -> list[tuple[str, int, str]]:
    lookup = crop_name.lower()
    if "corn" in lookup:
        return CORN_STAGES
    if "soybean" in lookup or "soy" in lookup:
        return SOYBEAN_STAGES
    if "wheat" in lookup:
        return WHEAT_STAGES
    return CORN_STAGES


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Field-season aligned mini-dashboard")
    p.add_argument("--grower-slug", default="nebraska-grower")
    p.add_argument("--farm-slug", default="nebraska-grower-nebraska")
    p.add_argument("--field-slug", default="osm-1352429400")
    p.add_argument("--year", type=int, default=2025)
    p.add_argument("--output-dir", default=None)
    return p.parse_args()


def _load_field_boundary(grower: str, farm: str, field: str) -> gpd.GeoSeries:
    path = field_boundary_path(grower, farm, field)
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf.set_crs("EPSG:4326", inplace=True)
    geom = gdf.geometry.iloc[0]
    return gpd.GeoSeries([geom], crs=gdf.crs)


def _ndvi_time_series(grower: str, farm: str, field: str, year: int, boundary: gpd.GeoSeries) -> pd.DataFrame:
    sentinel_dir = field_dir(grower, farm, field) / "satellite" / "sentinel" / str(year)
    if not sentinel_dir.exists():
        return pd.DataFrame()

    records = []
    geom = mapping(boundary.iloc[0])
    for scene_dir in sorted(sentinel_dir.iterdir()):
        if not scene_dir.is_dir():
            continue
        ndvi_path = scene_dir / f"{scene_dir.name}_ndvi.tif"
        if not ndvi_path.exists():
            continue
        scene_date = datetime.strptime(scene_dir.name, "sentinel_%Y%m%d")
        with rasterio.open(ndvi_path) as src:
            out_image, _ = rio_mask(src, [geom], crop=True, all_touched=True, nodata=np.nan)
            data = out_image[0]
            valid = data[~np.isnan(data)]
            if len(valid) > 0:
                records.append({
                    "date": scene_date,
                    "mean_ndvi": float(np.mean(valid)),
                    "std_ndvi": float(np.std(valid)),
                    "p25": float(np.percentile(valid, 25)),
                    "p75": float(np.percentile(valid, 75)),
                    "n_valid": int(len(valid)),
                })
    return pd.DataFrame(records)


def _weather_data(grower: str, farm: str, field: str, year: int) -> pd.DataFrame:
    wpath = farm_weather_path(grower, farm)
    df = pd.read_csv(wpath, parse_dates=["date"])
    df = df[df["field_id"] == field].copy()
    df = df[(df["date"] >= f"{year}-01-01") & (df["date"] <= f"{year}-12-31")].copy()
    if df.empty:
        return df
    df["gdd"] = ((df["T2M_MAX"] + df["T2M_MIN"]) / 2 - GDD_BASE).clip(lower=0)
    df["cum_precip"] = df["PRECTOTCORR"].cumsum()
    df["cum_gdd"] = df["gdd"].cumsum()
    return df


def _crop_for_year(grower: str, farm: str, field: str, year: int) -> str | None:
    cpath = farm_cdl_full_composition_path(grower, farm)
    if not cpath.exists():
        return None
    df = pd.read_csv(cpath)
    sub = df[(df["field_id"] == field) & (df["year"] == year)]
    if sub.empty:
        return None
    top = sub.sort_values("pct", ascending=False).iloc[0]
    return top["crop_name"]


def _build_dashboard(args: argparse.Namespace) -> str:
    grower = args.grower_slug
    farm = args.farm_slug
    field = args.field_slug
    year = args.year

    # Load data
    boundary = _load_field_boundary(grower, farm, field)
    ndvi_df = _ndvi_time_series(grower, farm, field, year, boundary)
    weather_df = _weather_data(grower, farm, field, year)
    crop_name = _crop_for_year(grower, farm, field, year) or "Unknown"

    # ── Build figure ────────────────────────────────────────
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.size": 9,
        "axes.facecolor": C_BG,
        "figure.facecolor": "white",
        "axes.grid": True,
        "grid.alpha": 0.3,
        "grid.color": C_GRID,
    })

    fig = plt.figure(figsize=(14, 11))
    # Layout: crop_stage (0.3) + ndvi (1) + precip (0.8) + temp (0.8) + gdd (0.8)
    gs = fig.add_gridspec(5, 1, height_ratios=[0.25, 1, 0.8, 0.8, 0.8], hspace=0.08, left=0.09, right=0.95, top=0.94, bottom=0.06)

    # ── Panel 0: Title + Crop label ─────────────────────────
    fig.suptitle(
        f"Field {field} — {year} Growing Season",
        fontsize=14, fontweight="bold", color=C_ANNOT, x=0.5, y=0.97
    )

    # ── Panel 1: Crop Stage Bar ─────────────────────────────
    ax_stage = fig.add_subplot(gs[0])
    ax_stage.set_xlim(0, 1)
    ax_stage.set_ylim(0, 1)
    ax_stage.axis("off")

    stages = _stage_lookup(crop_name)
    total_gdd_max = stages[-1][1] if stages else 2700
    if not weather_df.empty:
        total_gdd = weather_df["cum_gdd"].iloc[-1]
    else:
        total_gdd = 0
    frac = min(total_gdd / total_gdd_max, 1.0)

    # Draw GDD progress bar
    bar_y = 0.3
    bar_h = 0.3
    for i, (name_, start_gdd, color) in enumerate(stages):
        end_gdd = stages[i + 1][1] if i + 1 < len(stages) else total_gdd_max
        x0 = start_gdd / total_gdd_max
        x1 = end_gdd / total_gdd_max
        w = x1 - x0
        ax_stage.add_patch(mpatches.Rectangle((x0, bar_y), w, bar_h, facecolor=color, edgecolor="none", alpha=0.7))
        if w > 0.04:
            ax_stage.text(x0 + w / 2, bar_y + bar_h / 2, name_, ha="center", va="center", fontsize=6.5, color="#333")

    # Season progress arrow
    ax_stage.axvline(frac, 0, 1, color="#C0392B", linewidth=2, linestyle="-", alpha=0.8)
    ax_stage.text(frac, 0.85, f"Season {frac * 100:.0f}%", ha="center", fontsize=8, color="#C0392B", fontweight="bold")

    ax_stage.text(
        0.01, 0.75, f"CDL {year}: {crop_name}",
        transform=ax_stage.transAxes, fontsize=10, color=C_CROP, fontweight="bold", va="center"
    )
    if not weather_df.empty:
        ax_stage.text(
            0.99, 0.75, f"Total GDD: {total_gdd:.0f} °C·day",
            transform=ax_stage.transAxes, fontsize=9, color=C_GDD, fontweight="bold", ha="right", va="center"
        )

    # ── Panel 2: NDVI ──────────────────────────────────────
    ax_ndvi = fig.add_subplot(gs[1])
    if not ndvi_df.empty:
        ax_ndvi.fill_between(ndvi_df["date"], ndvi_df["p25"], ndvi_df["p75"], alpha=0.25, color=C_NDVI)
        ax_ndvi.plot(ndvi_df["date"], ndvi_df["mean_ndvi"], color=C_NDVI, linewidth=2, marker="o", markersize=5, label="Mean NDVI")
        ax_ndvi.errorbar(ndvi_df["date"], ndvi_df["mean_ndvi"], yerr=ndvi_df["std_ndvi"], fmt="none", ecolor=C_NDVI, alpha=0.4, capsize=3)

        peak = ndvi_df.loc[ndvi_df["mean_ndvi"].idxmax()]
        ax_ndvi.annotate(
            f"Peak NDVI: {peak['mean_ndvi']:.2f}",
            xy=(peak["date"], peak["mean_ndvi"]),
            xytext=(10, 20), textcoords="offset points",
            fontsize=8, color=C_NDVI, fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=C_NDVI, lw=1.2),
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=C_NDVI, alpha=0.8),
        )

    ax_ndvi.set_ylabel("NDVI")
    ax_ndvi.set_ylim(-0.05, 1.0)
    ax_ndvi.legend(loc="upper left", fontsize=8)
    ax_ndvi.tick_params(labelbottom=False)

    # ── Panel 3: Precipitation ──────────────────────────────
    ax_precip = fig.add_subplot(gs[2])
    if not weather_df.empty:
        ax_precip.bar(weather_df["date"], weather_df["PRECTOTCORR"], width=0.8, color=C_PRECIP, alpha=0.6, label="Daily precip (mm)")
        ax_precip_2 = ax_precip.twinx()
        ax_precip_2.plot(weather_df["date"], weather_df["cum_precip"], color=C_PRECIP, linewidth=2, linestyle="--", label="Cumulative")
        ax_precip_2.set_ylabel("Cumulative (mm)", color=C_PRECIP, fontsize=8)
        ax_precip_2.tick_params(axis="y", colors=C_PRECIP, labelsize=7)

        total_precip = weather_df["PRECTOTCORR"].sum()
        ax_precip.text(
            0.98, 0.95, f"Total: {total_precip:.0f} mm",
            transform=ax_precip.transAxes, fontsize=8, color=C_PRECIP, fontweight="bold",
            ha="right", va="top",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=C_PRECIP, alpha=0.8),
        )

    ax_precip.set_ylabel("Precip (mm)")
    ax_precip.legend(loc="upper left", fontsize=8)
    ax_precip.tick_params(labelbottom=False)

    # ── Panel 4: Temperature ────────────────────────────────
    ax_temp = fig.add_subplot(gs[3])
    if not weather_df.empty:
        ax_temp.fill_between(weather_df["date"], weather_df["T2M_MIN"], weather_df["T2M_MAX"], alpha=0.3, color=C_TEMP, label="Daily range")
        ax_temp.plot(weather_df["date"], weather_df["T2M_MAX"], color=C_TEMP_HOT, linewidth=1.2, label="Tmax")
        ax_temp.plot(weather_df["date"], weather_df["T2M_MIN"], color=C_TEMP_COLD, linewidth=1.2, label="Tmin")
        ax_temp.axhline(0, color="#333", linewidth=0.8, linestyle=":", alpha=0.6)

        # Annotate extremes
        max_row = weather_df.loc[weather_df["T2M_MAX"].idxmax()]
        min_row = weather_df.loc[weather_df["T2M_MIN"].idxmin()]
        ax_temp.annotate(
            f"Max {max_row['T2M_MAX']:.0f}°C",
            xy=(max_row["date"], max_row["T2M_MAX"]),
            xytext=(10, 10), textcoords="offset points",
            fontsize=7, color=C_TEMP_HOT, fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=C_TEMP_HOT, lw=0.8),
        )
        ax_temp.annotate(
            f"Min {min_row['T2M_MIN']:.0f}°C",
            xy=(min_row["date"], min_row["T2M_MIN"]),
            xytext=(10, -12), textcoords="offset points",
            fontsize=7, color=C_TEMP_COLD, fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=C_TEMP_COLD, lw=0.8),
        )

    ax_temp.set_ylabel("Temp (°C)")
    ax_temp.legend(loc="upper left", fontsize=8, ncol=3)
    ax_temp.tick_params(labelbottom=False)

    # ── Panel 5: Cumulative GDD ─────────────────────────────
    ax_gdd = fig.add_subplot(gs[4])
    if not weather_df.empty:
        ax_gdd.plot(weather_df["date"], weather_df["cum_gdd"], color=C_GDD, linewidth=2, label="Cumulative GDD")

        # Stage thresholds
        stage_label_y = weather_df["cum_gdd"].max() * 0.15
        for stage_name, stage_gdd, color in stages[1:]:
            ax_gdd.axhline(stage_gdd, color=color, linewidth=0.8, linestyle="--", alpha=0.6)
            ax_gdd.text(
                weather_df["date"].iloc[len(weather_df) // 5], stage_gdd + 30,
                stage_name, fontsize=6.5, color=color, fontweight="bold",
            )

        total_gdd = weather_df["cum_gdd"].iloc[-1]
        ax_gdd.text(
            0.98, 0.05, f"Total: {total_gdd:.0f} °C·day",
            transform=ax_gdd.transAxes, fontsize=8, color=C_GDD, fontweight="bold",
            ha="right", va="bottom",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=C_GDD, alpha=0.8),
        )

    ax_gdd.set_ylabel("GDD (°C·day)")
    ax_gdd.set_xlabel("Date")
    ax_gdd.legend(loc="upper left", fontsize=8)

    # ── Shared x-axis formatting ────────────────────────────
    for ax in [ax_ndvi, ax_precip, ax_temp, ax_gdd]:
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
        ax.tick_params(axis="x", labelsize=8)
        ax.set_xlim(date(year, 1, 15), date(year, 12, 15))

    # Caption
    parts = []
    parts.append(f"CDL {year}: {crop_name}.")
    if not ndvi_df.empty:
        peak = ndvi_df.loc[ndvi_df["mean_ndvi"].idxmax()]
        parts.append(f"Peak NDVI {peak['mean_ndvi']:.2f} on {peak['date']:%b %d}.")
    if not weather_df.empty:
        total_p = weather_df["PRECTOTCORR"].sum()
        total_g = weather_df["cum_gdd"].iloc[-1]
        max_t = weather_df["T2M_MAX"].max()
        min_t = weather_df["T2M_MIN"].min()
        parts.append(f"Total precip {total_p:.0f} mm, GDD {total_g:.0f} °C·day.")
        parts.append(f"Temperature range {min_t:.0f}–{max_t:.0f} °C.")
    caption = " ".join(parts)

    fig.text(0.5, 0.01, caption, ha="center", fontsize=8, color=C_ANNOT, fontstyle="italic",
             bbox=dict(boxstyle="round,pad=0.4", facecolor="#F0F0EA", edgecolor="none", alpha=0.7))

    # ── Save ────────────────────────────────────────────────
    output_dir = Path(args.output_dir) if args.output_dir else DATA_ROOT / "eda" / "field-season-dashboard" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{field}_{year}_dashboard.png"
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return str(out_path)


if __name__ == "__main__":
    args = _parse_args()
    path = _build_dashboard(args)
    print(f"Dashboard saved: {path}")
