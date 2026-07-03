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
    farm_weather_path,
    field_boundary_path,
    field_dir,
    field_weather_path,
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
C_DRY = "#D4A574"

# Growing-degree day base temperature (celsius)
GDD_BASE = 10.0

# Event detection thresholds
HEAVY_RAIN_MM = 20.0
EXTREME_HEAT_C = 38.0
FREEZE_THRESHOLD_C = 0.0
GREENUP_NDVI_DELTA = 0.30
DIP_NDVI_DELTA = -0.15
DRY_SPELL_DAYS = 14
DRY_SPELL_PRECIP_MM = 1.0
LATE_FREEZE_AFTER_MMDD = (5, 1)

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


# ── Drought context (all available years) ──────────────────

def _load_all_years_weather(grower: str, farm: str, field: str) -> pd.DataFrame:
    wpath = farm_weather_path(grower, farm)
    df = pd.read_csv(wpath, parse_dates=["date"])
    df = df[df["field_id"] == field].copy()
    return df


def _drought_context(all_weather: pd.DataFrame, year: int) -> dict:
    if all_weather.empty or len(all_weather) < 365:
        return {}
    all_weather = all_weather.copy()
    all_weather["y"] = all_weather["date"].dt.year
    yearly = all_weather.groupby("y")["PRECTOTCORR"].sum()
    this_year = yearly.get(year, None)
    mean_all = yearly.mean()
    if this_year is None or mean_all == 0:
        return {}
    anomaly_mm = this_year - mean_all
    anomaly_pct = anomaly_mm / mean_all * 100
    return {
        "year_total_mm": round(this_year, 1),
        "five_year_mean_mm": round(mean_all, 1),
        "anomaly_mm": round(anomaly_mm, 1),
        "anomaly_pct": round(anomaly_pct, 1),
    }


def _drought_label(drought: dict, crop: str) -> str:
    if not drought:
        return ""
    pct = drought["anomaly_pct"]
    if pct > 20:
        label = "Much wetter than normal"
    elif pct > 5:
        label = "Wetter than normal"
    elif pct > -5:
        label = "Near-normal precipitation"
    elif pct > -20:
        label = "Drier than normal"
    else:
        label = "Much drier than normal"
    return (
        f"Drought context: {drought['year_total_mm']:.0f} mm total "
        f"({drought['five_year_mean_mm']:.0f} mm 5-yr mean, "
        f"{drought['anomaly_pct']:+.0f}%)\n"
        f"{label} — {crop}"
    )


# ── Event detection ─────────────────────────────────────────

def _data_quality_report(ndvi_df: pd.DataFrame, weather_df: pd.DataFrame, year: int) -> list[str]:
    issues: list[str] = []
    if not weather_df.empty:
        expected = 366 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 365
        actual = len(weather_df)
        if actual < expected:
            issues.append(f"Weather: {actual}/{expected} days ({expected - actual} missing)")
    if not ndvi_df.empty:
        months = pd.to_datetime(ndvi_df["date"]).dt.month.unique()
        all_months = set(range(1, 13))
        missing_months = sorted(all_months - set(months))
        if missing_months:
            month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            missing_names = [month_names[m - 1] for m in missing_months]
            issues.append(f"NDVI: no scenes in {', '.join(missing_names)}")
        dates = sorted(pd.to_datetime(ndvi_df["date"]))
        for i in range(1, len(dates)):
            gap = (dates[i] - dates[i - 1]).days
            if gap > 60:
                issues.append(f"NDVI gap: {gap} days between {dates[i-1].strftime('%b %d')} and {dates[i].strftime('%b %d')}")
    else:
        issues.append("NDVI: no data available")
    return issues


def _detect_events(ndvi_df: pd.DataFrame, weather_df: pd.DataFrame, year: int) -> dict:
    events: dict[str, list[dict]] = {"ndvi": [], "weather": []}
    if not ndvi_df.empty and len(ndvi_df) >= 2:
        for i in range(1, len(ndvi_df)):
            prev = ndvi_df.iloc[i - 1]
            curr = ndvi_df.iloc[i]
            delta = curr["mean_ndvi"] - prev["mean_ndvi"]
            if delta >= GREENUP_NDVI_DELTA:
                events["ndvi"].append({"type": "greenup", "date": curr["date"], "value": delta, "prev_date": prev["date"]})
            elif delta <= DIP_NDVI_DELTA:
                events["ndvi"].append({"type": "dip", "date": curr["date"], "value": delta, "prev_date": prev["date"]})
    if not weather_df.empty:
        heavy = weather_df[weather_df["PRECTOTCORR"] >= HEAVY_RAIN_MM]
        for _, row in heavy.iterrows():
            events["weather"].append({"type": "heavy_rain", "date": row["date"], "value": row["PRECTOTCORR"]})
        hot = weather_df[weather_df["T2M_MAX"] >= EXTREME_HEAT_C]
        for _, row in hot.iterrows():
            events["weather"].append({"type": "extreme_heat", "date": row["date"], "value": row["T2M_MAX"]})
        freeze_date = datetime(year, LATE_FREEZE_AFTER_MMDD[0], LATE_FREEZE_AFTER_MMDD[1])
        freeze = weather_df[(weather_df["T2M_MIN"] < FREEZE_THRESHOLD_C) & (weather_df["date"] >= freeze_date)]
        for _, row in freeze.iterrows():
            events["weather"].append({"type": "late_freeze", "date": row["date"], "value": row["T2M_MIN"]})
        dry_streak = 0
        dry_start = None
        for _, row in weather_df.iterrows():
            if row["PRECTOTCORR"] < DRY_SPELL_PRECIP_MM:
                if dry_streak == 0:
                    dry_start = row["date"]
                dry_streak += 1
            else:
                if dry_streak >= DRY_SPELL_DAYS:
                    events["weather"].append({"type": "dry_spell", "date": dry_start, "value": dry_streak})
                dry_streak = 0
        if dry_streak >= DRY_SPELL_DAYS:
            events["weather"].append({"type": "dry_spell", "date": dry_start, "value": dry_streak})
    return events


# ── Strategy-sourced annotation helpers ─────────────────────

def _heavy_rain_wording(mm: float, month: int, crop: str) -> str:
    c = crop.lower()
    if "corn" in c and 6 <= month <= 7:
        return f"{mm:.0f} mm — peak water demand window"
    if "soy" in c and 7 <= month <= 8:
        return f"{mm:.0f} mm — pod fill moisture"
    return f"{mm:.0f} mm"


def _heat_wording(temp: float, month: int, crop: str) -> str:
    c = crop.lower()
    if "corn" in c and 6 <= month <= 7:
        return f"{temp:.0f}°C — pollination stress risk"
    if "soy" in c and 7 <= month <= 8:
        return f"{temp:.0f}°C — flower/pod heat stress"
    return f"{temp:.0f}°C"


def _freeze_wording(temp: float, month: int, crop: str) -> str:
    c = crop.lower()
    if "corn" in c and month <= 5:
        return f"{temp:.0f}°C freeze — check emergence"
    if "soy" in c and month <= 5:
        return f"{temp:.0f}°C freeze — stand risk"
    if "wheat" in c and month >= 10:
        return f"{temp:.0f}°C freeze — winter dormancy entry"
    return f"{temp:.0f}°C freeze"


def _greenup_wording(delta: float) -> str:
    return f"+{delta:.2f} green-up"


def _dip_wording(delta: float, month: int, crop: str) -> str:
    c = crop.lower()
    if "corn" in c and 7 <= month <= 8:
        return f"{delta:.2f} dip — grain fill check"
    if "soy" in c and 8 <= month <= 9:
        return f"{delta:.2f} dip — seed fill check"
    return f"{delta:.2f} dip"


def _dry_spell_wording(days: int, crop: str) -> str:
    return f"{days}-day dry spell"


# ── Machine-readable event JSON ────────────────────────────

def _save_events_json(
    events: dict,
    ndvi_df: pd.DataFrame,
    weather_df: pd.DataFrame,
    drought: dict,
    output_dir: Path,
    field: str,
    year: int,
    crop_name: str,
) -> str:
    ndvi_peak = None
    ndvi_peak_date = None
    if not ndvi_df.empty:
        peak_row = ndvi_df.loc[ndvi_df["mean_ndvi"].idxmax()]
        ndvi_peak = round(float(peak_row["mean_ndvi"]), 3)
        ndvi_peak_date = str(peak_row["date"].date())

    temp_min = weather_df["T2M_MIN"].min() if not weather_df.empty else None
    temp_max = weather_df["T2M_MAX"].max() if not weather_df.empty else None
    total_precip = round(float(weather_df["PRECTOTCORR"].sum()), 1) if not weather_df.empty else None
    total_gdd = round(float(weather_df["cum_gdd"].iloc[-1]), 1) if not weather_df.empty else None

    summary = {
        "field": field,
        "year": year,
        "crop": crop_name,
        "ndvi_peak": ndvi_peak,
        "ndvi_peak_date": ndvi_peak_date,
        "total_precip_mm": total_precip,
        "total_gdd_cday": total_gdd,
        "temp_min_c": round(float(temp_min), 1) if temp_min is not None else None,
        "temp_max_c": round(float(temp_max), 1) if temp_max is not None else None,
        "ndvi_event_count": len(events["ndvi"]),
        "weather_event_count": len(events["weather"]),
        "events": events,
        "drought_context": drought,
    }

    out_path = output_dir / f"{field}_{year}_events.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    return str(out_path)


# ── Dashboard builder ───────────────────────────────────────

def _build_dashboard(args: argparse.Namespace) -> str:
    grower = args.grower_slug
    farm = args.farm_slug
    field = args.field_slug
    year = args.year

    boundary = _load_field_boundary(grower, farm, field)
    ndvi_df = _ndvi_time_series(grower, farm, field, year, boundary)
    weather_df = _weather_data(grower, farm, field, year)
    crop_name = _crop_for_year(grower, farm, field, year) or "Unknown"

    # Drought context (all available years)
    all_weather = _load_all_years_weather(grower, farm, field)
    drought = _drought_context(all_weather, year)

    # Data quality
    issues = _data_quality_report(ndvi_df, weather_df, year)
    for msg in issues:
        print(f"[DATA NOTE] {msg}", file=sys.stderr)

    # Event detection
    events = _detect_events(ndvi_df, weather_df, year)

    # ── Plot setup ──────────────────────────────────────────
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.size": 9,
        "axes.facecolor": C_BG,
        "figure.facecolor": "white",
        "axes.grid": True,
        "grid.alpha": 0.3,
        "grid.color": C_GRID,
    })

    fig = plt.figure(figsize=(14, 11.5))
    gs = fig.add_gridspec(5, 1, height_ratios=[0.2, 1, 0.8, 0.8, 0.8], hspace=0.08, left=0.09, right=0.95, top=0.95, bottom=0.07)

    fig.suptitle(
        f"Field {field} — {year} Growing Season | CDL {year}: {crop_name}",
        fontsize=13, fontweight="bold", color=C_ANNOT, x=0.5, y=0.975
    )

    stages = _stage_lookup(crop_name)
    total_gdd_max = stages[-1][1] if stages else 2700
    total_gdd_val = weather_df["cum_gdd"].iloc[-1] if not weather_df.empty else 0
    frac = min(total_gdd_val / total_gdd_max, 1.0) if total_gdd_max > 0 else 0

    # ── Panel: Crop stage bar ───────────────────────────────
    ax_stage = fig.add_subplot(gs[0])
    ax_stage.set_xlim(0, 1)
    ax_stage.set_ylim(0, 1)
    ax_stage.axis("off")

    bar_y, bar_h = 0.35, 0.35
    for i, (name_, start_gdd, color) in enumerate(stages):
        end_gdd = stages[i + 1][1] if i + 1 < len(stages) else total_gdd_max
        x0_ = start_gdd / total_gdd_max
        x1_ = end_gdd / total_gdd_max
        w = x1_ - x0_
        ax_stage.add_patch(mpatches.Rectangle((x0_, bar_y), w, bar_h, facecolor=color, edgecolor="none", alpha=0.7))
        if w > 0.04:
            ax_stage.text(x0_ + w / 2, bar_y + bar_h / 2, name_, ha="center", va="center", fontsize=6.5, color="#333")

    ax_stage.axvline(frac, 0, 1, color="#C0392B", linewidth=2, linestyle="-", alpha=0.8)
    ax_stage.text(frac, 0.85, f"Season {frac * 100:.0f}%", ha="center", fontsize=8, color="#C0392B", fontweight="bold")
    if not weather_df.empty:
        ax_stage.text(0.99, 0.02, f"Total GDD: {total_gdd_val:.0f} °C·day",
                      transform=ax_stage.transAxes, fontsize=9, color=C_GDD, fontweight="bold", ha="right", va="bottom")

    # ── Panel (A) NDVI ──────────────────────────────────────
    ax_ndvi = fig.add_subplot(gs[1])
    ax_ndvi.text(0.01, 0.97, "(A) NDVI", transform=ax_ndvi.transAxes, fontsize=10, fontweight="bold", color=C_NDVI, va="top")

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

        for ev in events["ndvi"]:
            if ev["type"] == "greenup":
                prev_date = ev["prev_date"]
                curr_date = ev["date"]
                prev_ndvi = ndvi_df[ndvi_df["date"] == prev_date]["mean_ndvi"].iloc[0]
                curr_ndvi = ndvi_df[ndvi_df["date"] == curr_date]["mean_ndvi"].iloc[0]
                mid_date = prev_date + (curr_date - prev_date) / 2
                mid_ndvi = (prev_ndvi + curr_ndvi) / 2
                ax_ndvi.annotate(
                    _greenup_wording(ev["value"]),
                    xy=(curr_date, curr_ndvi),
                    xytext=(mid_date, mid_ndvi + 0.12),
                    fontsize=7, color=C_NDVI, fontweight="bold",
                    ha="center",
                    arrowprops=dict(arrowstyle="->", color=C_NDVI, lw=0.8),
                )
            elif ev["type"] == "dip":
                prev_date = ev["prev_date"]
                curr_date = ev["date"]
                prev_ndvi = ndvi_df[ndvi_df["date"] == prev_date]["mean_ndvi"].iloc[0]
                curr_ndvi = ndvi_df[ndvi_df["date"] == curr_date]["mean_ndvi"].iloc[0]
                mid_date = prev_date + (curr_date - prev_date) / 2
                mid_ndvi = (prev_ndvi + curr_ndvi) / 2
                ax_ndvi.annotate(
                    _dip_wording(ev["value"], curr_date.month, crop_name),
                    xy=(curr_date, curr_ndvi),
                    xytext=(mid_date, mid_ndvi - 0.15),
                    fontsize=7, color=C_TEMP_HOT, fontweight="bold",
                    ha="center",
                    arrowprops=dict(arrowstyle="->", color=C_TEMP_HOT, lw=0.8),
                )

    ax_ndvi.set_ylabel("NDVI (unitless)")
    ax_ndvi.set_ylim(-0.05, 1.0)
    ax_ndvi.legend(loc="upper left", fontsize=8)
    ax_ndvi.tick_params(labelbottom=False)
    ax_ndvi.minorticks_on()
    ax_ndvi.grid(which="minor", alpha=0.1)

    # ── Panel (B) Precipitation ─────────────────────────────
    ax_precip = fig.add_subplot(gs[2])
    ax_precip.text(0.01, 0.97, "(B) Precipitation", transform=ax_precip.transAxes, fontsize=10, fontweight="bold", color=C_PRECIP, va="top")

    if not weather_df.empty:
        ax_precip.bar(weather_df["date"], weather_df["PRECTOTCORR"], width=0.8, color=C_PRECIP, alpha=0.5, label="Daily precip (mm)")
        ax_precip_2 = ax_precip.twinx()
        ax_precip_2.plot(weather_df["date"], weather_df["cum_precip"], color=C_PRECIP, linewidth=2, linestyle="--", label="Cumulative (mm)")
        ax_precip_2.set_ylabel("Cumulative (mm)", color=C_PRECIP, fontsize=8)
        ax_precip_2.tick_params(axis="y", colors=C_PRECIP, labelsize=7)

        total_precip = weather_df["PRECTOTCORR"].sum()
        ax_precip.text(0.98, 0.95, f"Total: {total_precip:.0f} mm",
                       transform=ax_precip.transAxes, fontsize=8, color=C_PRECIP, fontweight="bold",
                       ha="right", va="top",
                       bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=C_PRECIP, alpha=0.8))

        # Drought context callout
        dlab = _drought_label(drought, crop_name)
        if dlab:
            ax_precip.text(
                0.02, 0.02, dlab,
                transform=ax_precip.transAxes, fontsize=6.5, color=C_ANNOT,
                ha="left", va="bottom", fontfamily="monospace",
                bbox=dict(boxstyle="round,pad=0.4", facecolor="#F5F0E0", edgecolor=C_DRY, alpha=0.85),
            )

        # Dry spell bands
        for ev in events["weather"]:
            if ev["type"] == "dry_spell":
                start_d = ev["date"]
                end_d = start_d + pd.Timedelta(days=ev["value"])
                ax_precip.axvspan(start_d, end_d, alpha=0.12, color=C_DRY, zorder=1)
                ax_precip.text(start_d + pd.Timedelta(days=ev["value"] / 2),
                               ax_precip.get_ylim()[1] * 0.75,
                               _dry_spell_wording(ev["value"], crop_name),
                               fontsize=6.5, color="#8B6914", fontweight="bold", ha="center", rotation=90)

        # Heavy rain annotations (top 5)
        rain_events = [ev for ev in events["weather"] if ev["type"] == "heavy_rain"]
        rain_events.sort(key=lambda x: x["value"], reverse=True)
        for ev in rain_events[:5]:
            ax_precip.annotate(
                _heavy_rain_wording(ev["value"], ev["date"].month, crop_name),
                xy=(ev["date"], ev["value"]),
                xytext=(0, 10), textcoords="offset points",
                fontsize=6.5, color=C_PRECIP, fontweight="bold", ha="center",
                arrowprops=dict(arrowstyle="->", color=C_PRECIP, lw=0.6),
            )

    ax_precip.set_ylabel("Precip (mm/day)")
    ax_precip.legend(loc="upper left", fontsize=8)
    ax_precip.tick_params(labelbottom=False)
    ax_precip.minorticks_on()
    ax_precip.grid(which="minor", alpha=0.1)

    # ── Panel (C) Temperature ──────────────────────────────
    ax_temp = fig.add_subplot(gs[3])
    ax_temp.text(0.01, 0.97, "(C) Temperature", transform=ax_temp.transAxes, fontsize=10, fontweight="bold", color=C_TEMP, va="top")

    if not weather_df.empty:
        ax_temp.fill_between(weather_df["date"], weather_df["T2M_MIN"], weather_df["T2M_MAX"], alpha=0.25, color=C_TEMP, label="Daily range")
        ax_temp.plot(weather_df["date"], weather_df["T2M_MAX"], color=C_TEMP_HOT, linewidth=1.2, label="Tmax")
        ax_temp.plot(weather_df["date"], weather_df["T2M_MIN"], color=C_TEMP_COLD, linewidth=1.2, label="Tmin")
        ax_temp.axhline(0, color="#333", linewidth=0.8, linestyle=":", alpha=0.5)

        # Overall extremes
        max_row = weather_df.loc[weather_df["T2M_MAX"].idxmax()]
        min_row = weather_df.loc[weather_df["T2M_MIN"].idxmin()]
        ax_temp.annotate(f"Max {max_row['T2M_MAX']:.0f}°C", xy=(max_row["date"], max_row["T2M_MAX"]),
                         xytext=(10, 10), textcoords="offset points", fontsize=7, color=C_TEMP_HOT, fontweight="bold",
                         arrowprops=dict(arrowstyle="->", color=C_TEMP_HOT, lw=0.8))
        ax_temp.annotate(f"Min {min_row['T2M_MIN']:.0f}°C", xy=(min_row["date"], min_row["T2M_MIN"]),
                         xytext=(10, -12), textcoords="offset points", fontsize=7, color=C_TEMP_COLD, fontweight="bold",
                         arrowprops=dict(arrowstyle="->", color=C_TEMP_COLD, lw=0.8))

        # Heat events (top 3)
        heat_events = [ev for ev in events["weather"] if ev["type"] == "extreme_heat"]
        heat_events.sort(key=lambda x: x["value"], reverse=True)
        for ev in heat_events[:3]:
            ax_temp.annotate(_heat_wording(ev["value"], ev["date"].month, crop_name),
                             xy=(ev["date"], ev["value"]),
                             xytext=(0, 8), textcoords="offset points",
                             fontsize=6.5, color=C_TEMP_HOT, fontweight="bold", ha="center",
                             arrowprops=dict(arrowstyle="->", color=C_TEMP_HOT, lw=0.6))

        # Late freeze events
        freeze_events = [ev for ev in events["weather"] if ev["type"] == "late_freeze"]
        for ev in freeze_events:
            ax_temp.annotate(_freeze_wording(ev["value"], ev["date"].month, crop_name),
                             xy=(ev["date"], ev["value"]),
                             xytext=(0, -10), textcoords="offset points",
                             fontsize=6.5, color=C_TEMP_COLD, fontweight="bold", ha="center",
                             arrowprops=dict(arrowstyle="->", color=C_TEMP_COLD, lw=0.6))

    ax_temp.set_ylabel("Temp (°C)")
    ax_temp.legend(loc="upper left", fontsize=8, ncol=3)
    ax_temp.tick_params(labelbottom=False)
    ax_temp.minorticks_on()
    ax_temp.grid(which="minor", alpha=0.1)

    # ── Panel (D) Cumulative GDD ───────────────────────────
    ax_gdd = fig.add_subplot(gs[4])
    ax_gdd.text(0.01, 0.97, "(D) Cumulative GDD", transform=ax_gdd.transAxes, fontsize=10, fontweight="bold", color=C_GDD, va="top")

    if not weather_df.empty:
        ax_gdd.plot(weather_df["date"], weather_df["cum_gdd"], color=C_GDD, linewidth=2, label="Cumulative GDD (base 10°C)")

        for stage_name, stage_gdd, color in stages[1:]:
            ax_gdd.axhline(stage_gdd, color=color, linewidth=0.8, linestyle="--", alpha=0.5)
            ax_gdd.text(weather_df["date"].iloc[len(weather_df) // 6], stage_gdd + 25,
                        stage_name, fontsize=6.5, color=color, fontweight="bold")

        ax_gdd.text(0.98, 0.05, f"Total: {total_gdd_val:.0f} °C·day",
                    transform=ax_gdd.transAxes, fontsize=8, color=C_GDD, fontweight="bold",
                    ha="right", va="bottom",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=C_GDD, alpha=0.8))

    ax_gdd.set_ylabel("GDD (°C·day)")
    ax_gdd.set_xlabel(f"Date ({year})")
    ax_gdd.legend(loc="upper left", fontsize=8)
    ax_gdd.minorticks_on()
    ax_gdd.grid(which="minor", alpha=0.1)

    # ── Shared x-axis ──────────────────────────────────────
    for ax in [ax_ndvi, ax_precip, ax_temp, ax_gdd]:
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
        ax.tick_params(axis="x", labelsize=8)
        ax.set_xlim(date(year, 1, 15), date(year, 12, 15))

    # ── Caption ─────────────────────────────────────────────
    parts = []
    if not ndvi_df.empty:
        peak = ndvi_df.loc[ndvi_df["mean_ndvi"].idxmax()]
        parts.append(f"NDVI peaked at {peak['mean_ndvi']:.2f} on {peak['date']:%b %d}.")
        n_gups = len([e for e in events["ndvi"] if e["type"] == "greenup"])
        n_dips = len([e for e in events["ndvi"] if e["type"] == "dip"])
        if n_gups:
            parts.append(f"{n_gups} rapid green-up event(s).")
        if n_dips:
            parts.append(f"{n_dips} NDVI dip(s).")
    if not weather_df.empty:
        total_p = weather_df["PRECTOTCORR"].sum()
        parts.append(f"Total precip: {total_p:.0f} mm.")
        n_rain = len([e for e in events["weather"] if e["type"] == "heavy_rain"])
        if n_rain:
            parts.append(f"{n_rain} heavy-rain day(s) (≥{HEAVY_RAIN_MM:.0f} mm).")
        n_hot = len([e for e in events["weather"] if e["type"] == "extreme_heat"])
        if n_hot:
            parts.append(f"{n_hot} extreme-heat day(s) (≥{EXTREME_HEAT_C:.0f}°C).")
        n_freeze = len([e for e in events["weather"] if e["type"] == "late_freeze"])
        if n_freeze:
            parts.append(f"{n_freeze} late freeze event(s) (after May 1).")
        n_dry = len([e for e in events["weather"] if e["type"] == "dry_spell"])
        if n_dry:
            parts.append(f"{n_dry} dry spell(s) (≥{DRY_SPELL_DAYS} days).")
        max_t = weather_df["T2M_MAX"].max()
        min_t = weather_df["T2M_MIN"].min()
        parts.append(f"Temp range: {min_t:.0f}–{max_t:.0f}°C, GDD: {total_gdd_val:.0f} °C·day.")

    caption = " ".join(parts)
    fig.text(0.5, 0.01, caption, ha="center", fontsize=7.5, color=C_ANNOT, fontstyle="italic",
             bbox=dict(boxstyle="round,pad=0.4", facecolor="#F0F0EA", edgecolor="none", alpha=0.7))

    # ── Save ────────────────────────────────────────────────
    output_dir = Path(args.output_dir) if args.output_dir else DATA_ROOT / "eda" / "field-season-dashboard" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{field}_{year}_dashboard.png"
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)

    _save_events_json(events, ndvi_df, weather_df, drought, output_dir, field, year, crop_name)
    return str(out_path)


if __name__ == "__main__":
    args = _parse_args()
    path = _build_dashboard(args)
    field = args.field_slug
    year = args.year
    output_dir = Path(args.output_dir) if args.output_dir else DATA_ROOT / "eda" / "field-season-dashboard" / "output"
    events_path = output_dir / f"{field}_{year}_events.json"
    print(f"Dashboard saved: {path}")
    print(f"Events JSON:   {events_path}")
