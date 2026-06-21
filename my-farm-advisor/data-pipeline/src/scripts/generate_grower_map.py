#!/usr/bin/env python3
"""Generate a self-contained Leaflet HTML map for a grower's fields."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_LOCAL_LIB = Path(__file__).resolve().parent / "lib"
sys.path.insert(0, str(_LOCAL_LIB))

from runtime_paths import resolve_runtime_paths  # noqa: E402

_RUNTIME_PATHS = resolve_runtime_paths()
_REPO = _RUNTIME_PATHS.runtime_base
_GROWERS_DIR = _REPO / "growers"

FIELD_COLORS = [
    "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231",
    "#911eb4", "#42d4f4", "#f032e6", "#bfef45", "#fabed4",
    "#469990", "#dcbeff", "#9a6324", "#800000", "#aaffc3",
    "#808000", "#ffd8b1", "#000075", "#a9a9a9", "#e6beff",
]


def _load_grower_data(grower_slug: str) -> list[dict]:
    grower_dir = _GROWERS_DIR / grower_slug
    if not grower_dir.is_dir():
        print(f"Error: grower directory not found: {grower_dir}", file=sys.stderr)
        sys.exit(1)

    grower_json = grower_dir / "grower.json"
    grower_meta = {}
    if grower_json.exists():
        grower_meta = json.loads(grower_json.read_text(encoding="utf-8"))

    farms_dir = grower_dir / "farms"
    if not farms_dir.is_dir():
        print(f"Error: no farms directory for grower: {grower_slug}", file=sys.stderr)
        sys.exit(1)

    fields_data = []
    for farm_dir in sorted(farms_dir.iterdir()):
        if not farm_dir.is_dir():
            continue
        farm_json_path = farm_dir / "farm.json"
        farm_meta = {}
        if farm_json_path.exists():
            farm_meta = json.loads(farm_json_path.read_text(encoding="utf-8"))

        fields_path = farm_dir / "fields"
        if not fields_path.is_dir():
            continue

        for field_dir in sorted(fields_path.iterdir()):
            if not field_dir.is_dir():
                continue

            field_json_path = field_dir / "field.json"
            if not field_json_path.exists():
                continue
            field_meta = json.loads(field_json_path.read_text(encoding="utf-8"))

            boundary_path = field_dir / "boundary" / "field_boundary.geojson"
            if not boundary_path.exists():
                continue

            boundary = json.loads(boundary_path.read_text(encoding="utf-8"))

            fields_data.append({
                "grower_slug": grower_slug,
                "grower_display": grower_meta.get("display_name", grower_slug),
                "farm_slug": farm_meta.get("farm_slug", farm_dir.name),
                "farm_display": farm_meta.get("display_name", farm_dir.name),
                "field_slug": field_meta.get("field_slug", field_dir.name),
                "field_display": field_meta.get("display_name", field_dir.name),
                "field_id": field_meta.get("field_id", ""),
                "boundary": boundary,
                "props": boundary.get("features", [{}])[0].get("properties", {}),
            })

    return fields_data


def _html_safe(val: object) -> str:
    return str(val).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _fields_to_geojson_feature_collection(fields_data: list[dict]) -> str:
    features = []
    for fd in fields_data:
        feat = fd["boundary"]["features"][0]
        feat["properties"]["_grower"] = fd["grower_display"]
        feat["properties"]["_farm"] = fd["farm_display"]
        feat["properties"]["_field"] = fd["field_display"]
        feat["properties"]["_color"] = FIELD_COLORS[len(features) % len(FIELD_COLORS)]
        features.append(feat)
    fc = {"type": "FeatureCollection", "features": features}
    return json.dumps(fc)


def generate_map(grower_slug: str) -> str:
    fields_data = _load_grower_data(grower_slug)
    if not fields_data:
        print(f"Error: no fields found for grower: {grower_slug}", file=sys.stderr)
        sys.exit(1)

    geojson_str = _fields_to_geojson_feature_collection(fields_data)

    field_items_html = ""
    for i, fd in enumerate(fields_data):
        acres = fd["props"].get("area_acres", "?")
        color = FIELD_COLORS[i % len(FIELD_COLORS)]
        field_items_html += (
            f'<li><a href="#" class="field-link" data-index="{i}" '
            f'style="border-left:4px solid {color}">'
            f'<b>{_html_safe(fd["field_display"])}</b> '
            f'<span class="meta">{_html_safe(fd["farm_display"])} &middot; {acres:.1f} ac</span>'
            f'</a></li>\n'
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html_safe(grower_slug)} — Field Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ height: 100%; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; }}
  #wrapper {{ display: flex; height: 100%; }}
  #sidebar {{ width: 300px; min-width: 300px; background: #f8fafc; border-right: 1px solid #e2e8f0; display: flex; flex-direction: column; overflow: hidden; }}
  #sidebar h2 {{ padding: 12px 16px; font-size: 1rem; background: #1e3a5f; color: white; margin: 0; }}
  #sidebar .subtitle {{ padding: 6px 16px; font-size: 0.78rem; color: #64748b; background: #f1f5f9; border-bottom: 1px solid #e2e8f0; }}
  #field-list {{ flex: 1; overflow-y: auto; list-style: none; padding: 0; }}
  #field-list li {{ border-bottom: 1px solid #e2e8f0; }}
  .field-link {{ display: block; padding: 10px 16px; text-decoration: none; color: #1e293b; transition: background 0.15s; }}
  .field-link:hover {{ background: #e2e8f0; }}
  .field-link .meta {{ display: block; font-size: 0.78rem; color: #64748b; margin-top: 2px; }}
  #map {{ flex: 1; height: 100%; }}
  .field-popup-table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
  .field-popup-table td {{ padding: 3px 6px; }}
  .field-popup-table td:first-child {{ font-weight: 600; color: #475569; white-space: nowrap; }}
  @media (max-width: 640px) {{ #sidebar {{ width: 200px; min-width: 200px; }} }}
</style>
</head>
<body>
<div id="wrapper">
  <div id="sidebar">
    <h2>{_html_safe(grower_slug)}</h2>
    <div class="subtitle">{len(fields_data)} field(s) &middot; Click to zoom</div>
    <ul id="field-list">{field_items_html}</ul>
  </div>
  <div id="map"></div>
</div>
<script>
var geojsonData = {geojson_str};

var map = L.map('map', {{ zoomControl: true }}).setView([39.8, -98.6], 4);

L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
  attribution: '&copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
  maxZoom: 19,
}}).addTo(map);

var bounds = [];
var fieldLayers = [];

geojsonData.features.forEach(function(feat, i) {{
  var layer = L.geoJSON(feat, {{
    style: {{
      color: feat.properties._color,
      weight: 2,
      fillColor: feat.properties._color,
      fillOpacity: 0.2,
    }},
    onEachFeature: function(f, l) {{
      var p = f.properties;
      var area = p.area_acres != null ? parseFloat(p.area_acres).toFixed(1) + ' ac' : '—';
      var popupHtml = '<table class="field-popup-table">' +
        '<tr><td>Grower</td><td>' + escapeHtml(p._grower) + '</td></tr>' +
        '<tr><td>Farm</td><td>' + escapeHtml(p._farm) + '</td></tr>' +
        '<tr><td>Field</td><td>' + escapeHtml(p._field) + '</td></tr>' +
        '<tr><td>Area</td><td>' + area + '</td></tr>' +
        (p.county_name ? '<tr><td>County</td><td>' + escapeHtml(p.county_name) + '</td></tr>' : '') +
        '</table>';
      l.bindPopup(popupHtml);
      l.on('mouseover', function() {{ l.setStyle({{ fillOpacity: 0.4, weight: 3 }}); }});
      l.on('mouseout', function() {{ l.setStyle({{ fillOpacity: 0.2, weight: 2 }}); }});
    }}
  }}).addTo(map);
  fieldLayers.push(layer);
  bounds.push(layer.getBounds());
}});

if (bounds.length > 0) {{
  var allBounds = bounds[0];
  for (var i = 1; i < bounds.length; i++) {{
    allBounds.extend(bounds[i]);
  }}
  map.fitBounds(allBounds, {{ padding: [20, 20] }});
}}

document.querySelectorAll('.field-link').forEach(function(link) {{
  link.addEventListener('click', function(e) {{
    e.preventDefault();
    var idx = parseInt(this.getAttribute('data-index'));
    var layer = fieldLayers[idx];
    if (layer) {{
      map.fitBounds(layer.getBounds(), {{ padding: [20, 20] }});
      layer.openPopup();
    }}
  }});
}});

function escapeHtml(str) {{
  var div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}}
</script>
</body>
</html>"""

    return html


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a Leaflet web map for a grower")
    parser.add_argument("--grower-slug", required=True, help="Grower slug (directory name under growers/)")
    args = parser.parse_args()

    html = generate_map(args.grower_slug)

    output_dir = _GROWERS_DIR / args.grower_slug
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "grower_map.html"
    output_path.write_text(html, encoding="utf-8")

    size_kb = output_path.stat().st_size / 1024
    print(f"Map generated: {output_path} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
