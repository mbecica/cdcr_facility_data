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
import math
from pathlib import Path
from typing import Any

from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform as shp_transform, unary_union

from classify_stories import run_classify
from common import (
    ALL34_DIR, DATA_BUILDINGS, FP_DIR, HOUSING_QA_DIR, HT_DIR, ROOT, TO_3857,
    compute_footprint_height_rows, load_local_laz_points,
)
from fetch_sources import run_fetch
from reconcile_footprints import reconcile_overture, scan_lidar_residuals, triage_zero_roof

OUT_CSV = DATA_BUILDINGS / "building_heights.csv"
MERGES_PATH = Path(__file__).with_name("footprint_merges.json")
REDRAWS_PATH = Path(__file__).with_name("footprint_redraws.geojson")
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


def apply_footprint_merges() -> None:
    """Fold pieces listed in footprint_merges.json into their main footprint in the cached tables (idempotent).

    merge: union the two outlines, close the gap, and recompute roof heights from cached LiDAR.
    sliver: drop the piece; the main outline stays as it is.
    """
    specs = json.loads(MERGES_PATH.read_text())
    feat_csv = HOUSING_QA_DIR / "building_features.csv"
    with open(feat_csv) as f:
        reader = csv.DictReader(f)
        feat_cols, feat_rows = list(reader.fieldnames or []), list(reader)
    feats_changed = False
    for code in sorted({k.split("-")[0] for k in specs}):
        gj_path, tri_path = FP_DIR / f"{code}_reconciled.geojson", HT_DIR / f"{code}_triaged.csv"
        gj = json.loads(gj_path.read_text())
        geo = {ft["properties"]["footprint_id"]: ft for ft in gj["features"]}
        with open(tri_path) as f:
            reader = csv.DictReader(f)
            cols, rows = list(reader.fieldnames or []), list(reader)
        by_id = {r["footprint_id"]: r for r in rows}
        for piece, spec in specs.items():
            if not piece.startswith(f"{code}-") or piece not in by_id:
                continue
            into = spec["into"]
            if spec["mode"] == "merge":
                ft, row = geo[into], by_id[into]
                k = 1.0 / math.cos(math.radians(float(row["lat"])))
                g = unary_union([shp_transform(TO_3857, shape(geo[i]["geometry"])) for i in (into, piece)])
                g = g.buffer(3 * k, join_style=2).buffer(-3 * k, join_style=2)
                wgs = shp_transform(Transformer.from_crs(3857, 4326, always_xy=True).transform, g)
                c = wgs.centroid
                ft["geometry"] = mapping(wgs)
                ft["properties"].update(
                    SQFEET=g.area / k**2 * 10.7639, centroid_lat=round(c.y, 7), centroid_lon=round(c.x, 7)
                )
                ring = g.buffer(20 * k).bounds
                px, py, pz, pc = load_local_laz_points(code, row["lidar_project"], ring)
                new = compute_footprint_height_rows(code, row["lidar_project"], [ft], px, py, pz, pc, row["ept_depth"])[0]
                keep = {"usa_structures_build_id", "occ_cls", "prim_occ", "footprint_source"}
                row.update({c: str(v) for c, v in new.items() if c in cols and c not in keep})
                x, y = g.minimum_rotated_rectangle.exterior.coords.xy
                a, b = sorted(math.hypot(x[i + 1] - x[i], y[i + 1] - y[i]) / k for i in (0, 1))
                for fr in feat_rows:
                    if fr["footprint_id"] == into:
                        fr.update({c: row[c] for c in feat_cols if c.startswith("roof_")})
                        fr.update(footprint_sqft=row["footprint_sqft"], multi_tier_flag=row["multi_tier_flag"],
                                  solidity=f"{g.area / g.convex_hull.area:.3f}", aspect_ratio=f"{b / a:.2f}",
                                  short_m=f"{a:.1f}", long_m=f"{b:.1f}", sub_tier_heights_ft="")
            rows = [r for r in rows if r["footprint_id"] != piece]
            gj["features"] = [ft for ft in gj["features"] if ft["properties"]["footprint_id"] != piece]
            feat_rows = [r for r in feat_rows if r["footprint_id"] != piece]
            feats_changed = True
            print(f"{spec['mode']:6s} {piece} -> {into}")
        with open(tri_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        gj_path.write_text(json.dumps(gj))
    if feats_changed:
        with open(feat_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=feat_cols)
            w.writeheader()
            w.writerows(feat_rows)


def apply_footprint_redraws() -> None:
    """Replace outlines listed in footprint_redraws.geojson with LiDAR-traced ones in the cached tables (idempotent)."""
    spec = json.loads(REDRAWS_PATH.read_text())
    feat_csv = HOUSING_QA_DIR / "building_features.csv"
    with open(feat_csv) as f:
        reader = csv.DictReader(f)
        feat_cols, feat_rows = list(reader.fieldnames or []), list(reader)
    for code in sorted({ft["properties"]["cdcr_code"] for ft in spec["features"]}):
        gj_path, tri_path = FP_DIR / f"{code}_reconciled.geojson", HT_DIR / f"{code}_triaged.csv"
        gj = json.loads(gj_path.read_text())
        with open(tri_path) as f:
            reader = csv.DictReader(f)
            cols, rows = list(reader.fieldnames or []), list(reader)
        new = [ft for ft in spec["features"] if ft["properties"]["cdcr_code"] == code]
        new_ids = {ft["properties"]["footprint_id"] for ft in new}
        drop = {i for i in spec["drop"] if i.startswith(f"{code}-")}
        have = {r["footprint_id"] for r in rows}
        if new_ids <= have and not drop & have:
            continue
        base = next(r for r in rows if r["triage_status"] == "valid_standing" and r["in_rapt_boundary"] == "yes")
        rows = [r for r in rows if r["footprint_id"] not in drop | new_ids]
        gj["features"] = [f for f in gj["features"] if f["properties"]["footprint_id"] not in drop | new_ids]
        feat_rows = [r for r in feat_rows if r["footprint_id"] not in drop | new_ids]
        for ft in new:
            fid = ft["properties"]["footprint_id"]
            g = shp_transform(TO_3857, shape(ft["geometry"]))
            c = shape(ft["geometry"]).centroid
            k = 1.0 / math.cos(math.radians(c.y))
            props = {
                "footprint_id": fid, "in_rapt_boundary": "yes", "other_rapt_code": "", "dist_to_rapt_m": 0.0,
                "BUILD_ID": "", "OCC_CLS": "", "PRIM_OCC": "", "SQFEET": g.area / k**2 * 10.7639,
                "centroid_lon": round(c.x, 7), "centroid_lat": round(c.y, 7), "footprint_source": "lidar_naip_patch",
            }
            feat = {"type": "Feature", "properties": props, "geometry": ft["geometry"]}
            pts = load_local_laz_points(code, base["lidar_project"], g.buffer(20 * k).bounds)
            hr = compute_footprint_height_rows(code, base["lidar_project"], [feat], *pts, base["ept_depth"], "lidar_naip_patch")[0]
            row = {c: "" for c in cols}
            row.update({c: base[c] for c in ("perimeter_status", "is_closed_facility", "cond_roofs_2026",
                                             "mpar_last_roof_year", "post_lidar_roof_project_flag") if c in cols})
            row.update({c: str(v) for c, v in hr.items() if c in cols})
            row.update(triage_status="valid_standing", building_category="standing_unclassified")
            rows.append(row)
            gj["features"].append(feat)
            x, y = g.minimum_rotated_rectangle.exterior.coords.xy
            a, b = sorted(math.hypot(x[i + 1] - x[i], y[i + 1] - y[i]) / k for i in (0, 1))
            fr = {c: row.get(c, "") for c in feat_cols}
            fr.update(solidity=f"{g.area / g.convex_hull.area:.3f}", aspect_ratio=f"{b / a:.2f}",
                      short_m=f"{a:.1f}", long_m=f"{b:.1f}", sub_tier_heights_ft="")
            feat_rows.append(fr)
        print(f"redraw {code}: dropped {len(drop)}, added {len(new)}")
        with open(tri_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        gj_path.write_text(json.dumps(gj))
        with open(feat_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=feat_cols)
            w.writeheader()
            w.writerows(feat_rows)


def export_deliverables() -> None:
    """Export final standing buildings and shade canopies into data/buildings/."""
    with open(ROOT / "data" / "institutions.csv") as f:
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

    apply_footprint_merges()
    apply_footprint_redraws()
    run_classify(qa_png=args.qa_png, codes=args.only)
    export_deliverables()


if __name__ == "__main__":
    main()
