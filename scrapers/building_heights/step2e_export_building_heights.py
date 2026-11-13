#!/usr/bin/env python3
"""
Step 2E: Export clean CDCR building heights & footprints deliverables into data/buildings/.

Reads Step 2D per-institution classifications and reconciled GeoJSON polygons from
notes/building_heights_pilot/all_34/, keeps strictly standing buildings and shade canopies
inside CDCR institution boundaries (omitting non-building source polygons and excluded
utility aprons), strips internal LiDAR/QA/crosswalk clutter, and writes:
  - data/buildings/building_heights.csv
  - data/buildings/building_footprints.geojson
"""
from __future__ import annotations

import collections
import csv
import json
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parents[1]
WORK_DIR = ROOT / "notes" / "building_heights_pilot" / "all_34"
HEIGHTS_DIR = WORK_DIR / "heights"
FP_DIR = WORK_DIR / "footprints"

OUT_CSV = ROOT / "data" / "buildings" / "building_heights.csv"
OUT_GEOJSON = ROOT / "data" / "buildings" / "building_footprints.geojson"

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
    """Convert CSV string row fields to clean JSON scalar types."""
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


def main() -> None:
    with open(ROOT / "crosswalk" / "institutions.csv") as f:
        codes = sorted(r["cdcr_code"] for r in csv.DictReader(f))
    with open(WORK_DIR / "all_34_summary.csv") as f:
        lidar_year_by_code = {r["cdcr_code"]: r["lidar_year"] for r in csv.DictReader(f)}

    out_rows: list[dict[str, str]] = []
    geojson_features: list[dict[str, Any]] = []

    for code in codes:
        step2d_csv = HEIGHTS_DIR / f"{code}_step2d.csv"
        reconciled_gj = FP_DIR / f"{code}_reconciled.geojson"

        with open(step2d_csv) as f:
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
            # Clear height_source="none" if no LiDAR roof heights exist -> keep explicit "none"
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

    OUT_GEOJSON.write_text(
        json.dumps({"type": "FeatureCollection", "features": geojson_features})
    )

    cats = collections.Counter(r["building_category"] for r in out_rows)
    h_rows = [r for r in out_rows if r["is_housing"] == "yes"]
    conf = collections.Counter(r["story_confidence"] for r in out_rows)
    print(f"Institutions exported : {len({r['cdcr_code'] for r in out_rows})} / {len(codes)}")
    print(f"Total buildings/canopies: {len(out_rows)}")
    print(f"Categories            : {dict(sorted(cats.items()))}")
    print(f"Housing units         : {len(h_rows)} (stories filled={sum(1 for r in h_rows if r['stories'])})")
    print(f"Story confidence      : {dict(sorted(conf.items()))}")
    print(f"Wrote {OUT_CSV.relative_to(ROOT)}")
    print(f"Wrote {OUT_GEOJSON.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
