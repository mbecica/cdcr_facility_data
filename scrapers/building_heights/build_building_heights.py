#!/usr/bin/env python3
"""
Build and export final CDCR building heights & footprints deliverables into data/buildings/.

By default, runs the fast local classification pass (classify_stories.run_classify) using
cached intermediate tables in notes/building_heights_pilot/all_34/ and exports:
  - data/buildings/building_heights.csv
  - data/buildings/building_footprints.geojson

Pass --fetch, --reconcile, or --triage to re-run upstream imagery/LiDAR/footprint stages
before classifying and exporting.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
from typing import Any

from classify_stories import run_classify
from common import ALL34_DIR, DATA_BUILDINGS, FP_DIR, HT_DIR, ROOT
from fetch_sources import run_fetch
from reconcile_footprints import reconcile_overture, scan_lidar_residuals, triage_zero_roof

OUT_CSV = DATA_BUILDINGS / "building_heights.csv"
OUT_GEOJSON = DATA_BUILDINGS / "building_footprints.geojson"

OUTPUT_COLUMNS = [
    "cdcr_code",
    "footprint_id",
    "usa_structures_build_id",
    "overture_id",
    "lat",
    "lon",
    "footprint_sqft",
    "solidity",
    "footprint_source",
    "building_category",
    "is_housing",
    "housing_prototype",
    "stories",
    "stories_range",
    "story_confidence",
    "story_method",
    "roof_p10_ft",
    "roof_p25_ft",
    "roof_p50_ft",
    "roof_p75_ft",
    "roof_p90_ft",
    "roof_p98_ft",
    "roof_spread_ft",
    "multi_tier_flag",
    "sub_tier_heights_ft",
    "ground_slope_ft",
    "height_source",
    "lidar_project",
    "lidar_year",
]

INT_FIELDS = {"stories", "lidar_year"}
FLOAT_FIELDS = {
    "lat",
    "lon",
    "footprint_sqft",
    "solidity",
    "roof_p10_ft",
    "roof_p25_ft",
    "roof_p50_ft",
    "roof_p75_ft",
    "roof_p90_ft",
    "roof_p98_ft",
    "roof_spread_ft",
    "ground_slope_ft",
}


def typed_geojson_props(row: dict[str, str]) -> dict[str, Any]:
    """Convert CSV string row fields into typed JSON scalar values."""
    props: dict[str, Any] = {}
    for col in OUTPUT_COLUMNS:
        val = row.get(col, "")
        if val == "":
            props[col] = None
        elif col in INT_FIELDS:
            props[col] = int(round(float(val)))
        elif col in FLOAT_FIELDS:
            props[col] = round(float(val), 6) if col in {"lat", "lon"} else float(val)
        else:
            props[col] = val
    return props


def export_deliverables() -> None:
    """Export final standing buildings and shade canopies into data/buildings/."""
    with open(ROOT / "crosswalk" / "institutions.csv") as f:
        codes = sorted(r["cdcr_code"] for r in csv.DictReader(f))
    with open(ALL34_DIR / "all_34_summary.csv") as f:
        lidar_year_by_code = {r["cdcr_code"]: r["lidar_year"] for r in csv.DictReader(f)}

    out_rows: list[dict[str, str]] = []
    geojson_features: list[dict[str, Any]] = []

    for code in codes:
        classified_csv = HT_DIR / f"{code}_classified.csv"
        if not classified_csv.exists():
            classified_csv = HT_DIR / f"{code}_step2d.csv"
        reconciled_gj = FP_DIR / f"{code}_reconciled.geojson"

        with open(classified_csv) as f:
            standing_rows = [
                r
                for r in csv.DictReader(f)
                if r["in_rapt_boundary"] == "yes"
                and r["triage_status"] in ("valid_standing", "new_post_lidar_bldg")
            ]

        geom_by_id = {
            ft["properties"]["footprint_id"]: ft["geometry"]
            for ft in json.loads(reconciled_gj.read_text())["features"]
        }

        lidar_yr = lidar_year_by_code.get(code, "")
        for r in standing_rows:
            fid = r["footprint_id"]
            if fid not in geom_by_id:
                raise KeyError(f"Missing reconciled GeoJSON geometry for {fid}")
            merged = dict(r)
            merged["lidar_year"] = lidar_yr
            clean_row = {col: merged.get(col, "") for col in OUTPUT_COLUMNS}
            out_rows.append(clean_row)
            geojson_features.append({
                "type": "Feature",
                "properties": typed_geojson_props(clean_row),
                "geometry": geom_by_id[fid],
            })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        w.writeheader()
        w.writerows(out_rows)

    OUT_GEOJSON.write_text(json.dumps({"type": "FeatureCollection", "features": geojson_features}))

    cats = collections.Counter(r["building_category"] for r in out_rows)
    h_rows = [r for r in out_rows if r["is_housing"] == "yes"]
    conf = collections.Counter(r["story_confidence"] for r in out_rows)
    print(f"\nInstitutions exported : {len({r['cdcr_code'] for r in out_rows})} / {len(codes)}")
    print(f"Total buildings/canopies: {len(out_rows)}")
    print(f"Categories            : {dict(sorted(cats.items()))}")
    print(f"Housing units         : {len(h_rows)} (stories filled={sum(1 for r in h_rows if r['stories'])})")
    print(f"Story confidence      : {dict(sorted(conf.items()))}")
    print(f"Wrote {OUT_CSV.relative_to(ROOT)}")
    print(f"Wrote {OUT_GEOJSON.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build CDCR building heights CSV and footprints GeoJSON.")
    parser.add_argument("--fetch", action="store_true", help="Re-run source fetching & raw EPT extraction")
    parser.add_argument("--reconcile", action="store_true", help="Re-run Overture reconciliation & residual LiDAR scan")
    parser.add_argument("--triage", action="store_true", help="Re-run zero-roof triage before classification")
    parser.add_argument("--qa-png", action="store_true", help="Render housing QA overlay PNGs during classification")
    parser.add_argument("--only", nargs="*", help="Limit upstream --fetch/--reconcile/--qa-png stages to specific codes")
    args = parser.parse_args()

    if args.fetch:
        run_fetch(only=args.only)
    if args.reconcile:
        reconcile_overture(only=args.only)
        scan_lidar_residuals(only=args.only)
    if args.triage:
        triage_zero_roof(render_sheets=args.qa_png)

    run_classify(qa_png=args.qa_png, codes=args.only)
    export_deliverables()


if __name__ == "__main__":
    main()
