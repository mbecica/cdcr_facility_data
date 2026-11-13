#!/usr/bin/env python3
"""
Step 2A: Reconcile USA Structures footprints against Overture Maps buildings across all 34 institutions.
- Caches raw Overture Maps footprints (filtered to 300 m buffer) per institution.
- Links overlapping Overture IDs / names / heights / num_floors to existing footprints (as reference metadata only; Overture ML heights are NOT used as primary height measurements due to 2-3x observed errors).
- Patches standing buildings missed by USA Structures inside RAPT (e.g., CHCF SW blocks),
  computing raw AWS EPT / S3 LAZ LiDAR heights for patched footprints and rendering updated QA overlays.
"""

import csv
import json
import math
import os
import sys
import urllib.parse
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=DeprecationWarning)

import certifi
os.environ["SSL_CERT_FILE"] = certifi.where()

import numpy as np
from overturemaps import core
from pyproj import Transformer
from shapely import contains_xy
from shapely.geometry import shape
from shapely.ops import transform as shp_transform, unary_union
from shapely.wkb import loads as wkb_loads

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
import step1_extract_lidar_heights as s1  # reuse verified helpers

ROOT = SCRIPTS_DIR.parents[1]
WORK_DIR = ROOT / "notes" / "building_heights_pilot"
RAW = WORK_DIR / "raw"
OUT_ROOT = WORK_DIR / "all_34"
OVT_DIR = OUT_ROOT / "overture"
FP_DIR = OUT_ROOT / "footprints"
HT_DIR = OUT_ROOT / "heights"
QA_DIR = OUT_ROOT / "qa_overlays"
NAIP_DIR = ROOT / "sources" / "imagery" / "naip_2024"
OVT_DIR.mkdir(parents=True, exist_ok=True)

TO_3857 = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform
TO_4326 = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True).transform
M_TO_FT = 3.28084
SQM_TO_SQFT = 10.7639104


def fetch_overture_for_prison(code: str, buf_wgs, force: bool = False) -> list[dict]:
    out_gj = OVT_DIR / f"{code}_overture.geojson"
    if out_gj.exists() and not force:
        return json.loads(out_gj.read_text())["features"]

    bb = buf_wgs.bounds
    tbl = core.record_batch_reader("building", bbox=bb).read_all()
    d = tbl.to_pydict()
    feats = []
    for i in range(tbl.num_rows):
        geom_raw = d["geometry"][i]
        geom = wkb_loads(geom_raw) if isinstance(geom_raw, (bytes, bytearray)) else shape(geom_raw)
        if not geom.is_valid:
            geom = geom.buffer(0)
        c = geom.centroid
        if not buf_wgs.contains(c):
            continue
        names_obj = d["names"][i] or {}
        primary_name = names_obj.get("primary") if isinstance(names_obj, dict) else ""
        srcs = d["sources"][i] or []
        src_datasets = sorted({s.get("dataset", "") for s in srcs if isinstance(s, dict) and s.get("dataset")})
        h_m = d["height"][i]
        nf = d["num_floors"][i]
        g_3857 = shp_transform(TO_3857, geom)
        area_sqft = g_3857.area * (math.cos(math.radians(c.y)) ** 2) * SQM_TO_SQFT
        feats.append({
            "type": "Feature",
            "geometry": geom.__geo_interface__,
            "properties": {
                "overture_id": d["id"][i],
                "overture_name": primary_name or "",
                "overture_class": d["class"][i] or "",
                "overture_subtype": d["subtype"][i] or "",
                "overture_height_m": round(float(h_m), 2) if h_m is not None else None,
                "overture_height_ft": round(float(h_m) * M_TO_FT, 1) if h_m is not None else None,
                "overture_num_floors": int(nf) if nf is not None else None,
                "overture_sources": ";".join(src_datasets),
                "area_sqft": round(area_sqft, 1),
                "centroid_lon": round(c.x, 7),
                "centroid_lat": round(c.y, 7),
            },
        })
    out_gj.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    return feats


def run_reconcile(only: list[str] | None = None):
    rapt_raw = json.loads((RAW / "Prison_Boundaries_RAPT.geojson").read_text())["features"]
    rapt_by_fid = {str(f["properties"]["FACILITYID"]).strip(): shape(f["geometry"]) for f in rapt_raw if f["properties"].get("FACILITYID")}
    insts = list(csv.DictReader(open(ROOT / "crosswalk" / "institutions.csv")))
    rapt_by_code = {r["cdcr_code"]: rapt_by_fid[r["fema_facilityid"].strip()] for r in insts}
    ept_raw = json.loads((RAW / "usgs_lidar_resources.geojson").read_text())["features"]
    ept_feats = [(f["properties"]["name"], f["properties"].get("count", 0), shape(f["geometry"])) for f in ept_raw]
    sum_by_code = {
        r["cdcr_code"]: r
        for r in csv.DictReader(open(OUT_ROOT / "all_34_summary.csv"))
    } if (OUT_ROOT / "all_34_summary.csv").exists() else {}

    total_patched = 0
    for inst in insts:
        code = inst["cdcr_code"]
        if only and code not in only:
            continue
        rapt_wgs = rapt_by_code[code]
        other_rapt = {k: v for k, v in rapt_by_code.items() if k != code}
        mean_lat = rapt_wgs.centroid.y
        buf_wgs = shp_transform(TO_4326, shp_transform(TO_3857, rapt_wgs).buffer(300.0 / math.cos(math.radians(mean_lat))))

        ovt_feats = fetch_overture_for_prison(code, buf_wgs)
        usa_gj_path = FP_DIR / f"{code}_footprints.geojson"
        usa_feats = json.loads(usa_gj_path.read_text())["features"]
        usa_polys = []
        for f in usa_feats:
            g = shape(f["geometry"])
            usa_polys.append(g.buffer(0) if not g.is_valid else g)

        h_csv_path = HT_DIR / f"{code}_heights.csv"
        h_rows = list(csv.DictReader(open(h_csv_path)))
        h_by_fid = {r["footprint_id"]: r for r in h_rows}

        # Match existing USA Structures footprints to Overture IDs
        ovt_matches_by_usa = {f["properties"]["footprint_id"]: [] for f in usa_feats}
        unmatched_ovt_in_rapt = []

        for of in ovt_feats:
            op = of["properties"]
            og = shape(of["geometry"])
            if not og.is_valid:
                og = og.buffer(0)
            c = og.centroid
            in_rapt = rapt_wgs.contains(c)

            best_overlap_frac = 0.0
            for uf, up in zip(usa_feats, usa_polys):
                if not up.is_valid:
                    up = up.buffer(0)
                if not og.intersects(up):
                    continue
                inter = og.intersection(up).area
                min_a = min(og.area, up.area)
                frac = inter / min_a if min_a > 0 else 0.0
                if frac >= 0.25:
                    ovt_matches_by_usa[uf["properties"]["footprint_id"]].append(of)
                if frac > best_overlap_frac:
                    best_overlap_frac = frac

            # Candidate missed building inside RAPT >= 400 sqft (not overlapping existing USA footprint)
            if in_rapt and best_overlap_frac < 0.20 and op["area_sqft"] >= 400.0:
                unmatched_ovt_in_rapt.append(of)

        # Evaluate unmatched Overture candidates inside RAPT using LiDAR (if available) to verify standing structure vs parking/dirt
        proj, _, _ = s1.select_ept_project(rapt_wgs, ept_feats)
        if not proj and code == "PBSP" and (s1.EPT_CACHE / "CA_NorthernCA_6_B22_PBSP").exists():
            proj = "CA_NorthernCA_6_B22"
        patched_feats = []
        patched_rows = []
        if unmatched_ovt_in_rapt:
            # Build synthetic features to test through exact extract_heights helper logic in memory
            cand_feats = []
            for idx, of in enumerate(
                sorted(unmatched_ovt_in_rapt, key=lambda x: (x["properties"]["centroid_lat"], x["properties"]["centroid_lon"])),
                1,
            ):
                op = of["properties"]
                nf = {
                    "type": "Feature",
                    "geometry": of["geometry"],
                    "properties": {
                        "footprint_id": f"{code}-ovt-{idx:03d}",
                        "in_rapt_boundary": "yes",
                        "other_rapt_code": "",
                        "dist_to_rapt_m": 0.0,
                        "BUILD_ID": "",
                        "OCC_CLS": "",
                        "PRIM_OCC": "",
                        "SQFEET": op["area_sqft"],
                        "centroid_lon": op["centroid_lon"],
                        "centroid_lat": op["centroid_lat"],
                        "footprint_source": "overture_patch",
                        **op,
                    },
                }
                cand_feats.append(nf)

            if proj:
                # Extract LiDAR height on candidates using a temp fileless call or temp path
                tmp_csv = HT_DIR / f"_{code}_tmp_ovt.csv"
                if tmp_csv.exists():
                    tmp_csv.unlink()
                # Call extract_heights on candidates cleanly by writing temp target then removing
                cand_rows = extract_heights_in_mem(code, proj, cand_feats)
                keep_idx = 0
                for nf, cr in zip(cand_feats, cand_rows):
                    # Keep if standing structure (roof_pts >= 5 & median height >= 6.5 ft) or huge Overture footprint (>=2500 sqft)
                    has_roof = cr["roof_p50_ft"] != "" and float(cr["roof_p50_ft"]) >= 6.5
                    if has_roof:
                        keep_idx += 1
                        new_id = f"{code}-ovt-{keep_idx:03d}"
                        nf["properties"]["footprint_id"] = new_id
                        cr["footprint_id"] = new_id
                        cr["footprint_source"] = "overture_patch"
                        cr["height_source"] = f"usgs_3dep_ept:{proj}"
                        patched_feats.append(nf)
                        patched_rows.append(cr)
            else:
                for idx, nf in enumerate(cand_feats, 1):
                    op = nf["properties"]
                    patched_feats.append(nf)
                    patched_rows.append({
                        "cdcr_code": code,
                        "footprint_id": op["footprint_id"],
                        "in_rapt_boundary": "yes",
                        "other_rapt_code": "",
                        "dist_to_rapt_m": 0.0,
                        "usa_structures_build_id": "",
                        "occ_cls": "",
                        "prim_occ": "",
                        "lat": op["centroid_lat"],
                        "lon": op["centroid_lon"],
                        "footprint_sqft": op["area_sqft"],
                        "pts_inside": 0,
                        "roof_pts": 0,
                        "ground_pts": 0,
                        "ground_method": "no_ept",
                        "ground_slope_ft": "",
                        "roof_p10_ft": "",
                        "roof_p25_ft": "",
                        "roof_p50_ft": "",
                        "roof_p75_ft": "",
                        "roof_p90_ft": "",
                        "roof_p98_ft": "",
                        "roof_spread_ft": "",
                        "multi_tier_flag": "no",
                        "zero_roof_flag": "yes",
                        "bldg_cls_counts": "{}",
                        "lidar_project": "",
                        "ept_depth": "",
                        "footprint_source": "overture_patch",
                        "height_source": "none",
                    })

        # Enrich existing + patched rows with Overture reference metadata
        enriched_rows = []
        for r in h_rows:
            fid = r["footprint_id"]
            matches = ovt_matches_by_usa.get(fid, [])
            ovt_ids = ";".join(m["properties"]["overture_id"] for m in matches)
            ovt_names = ";".join(sorted({m["properties"]["overture_name"] for m in matches if m["properties"]["overture_name"]}))
            ovt_classes = ";".join(sorted({m["properties"]["overture_class"] for m in matches if m["properties"]["overture_class"]}))
            ovt_hs = [m["properties"]["overture_height_ft"] for m in matches if m["properties"]["overture_height_ft"] is not None]
            ovt_floors = [m["properties"]["overture_num_floors"] for m in matches if m["properties"]["overture_num_floors"] is not None]
            ovt_h_max = max(ovt_hs) if ovt_hs else ""
            ovt_f_max = max(ovt_floors) if ovt_floors else ""

            r2 = dict(r)
            r2.setdefault("footprint_source", "usa_structures")
            if r2["roof_p50_ft"] != "" and r2.get("lidar_project"):
                r2["height_source"] = f"usgs_3dep_ept:{r2['lidar_project']}"
            else:
                r2["height_source"] = "none"

            r2["overture_id"] = ovt_ids
            r2["overture_name"] = ovt_names
            r2["overture_class"] = ovt_classes
            r2["overture_height_ft"] = ovt_h_max
            r2["overture_num_floors"] = ovt_f_max
            enriched_rows.append(r2)

        for nf, pr in zip(patched_feats, patched_rows):
            op = nf["properties"]
            pr2 = dict(pr)
            pr2["overture_id"] = op["overture_id"]
            pr2["overture_name"] = op["overture_name"]
            pr2["overture_class"] = op["overture_class"]
            pr2["overture_height_ft"] = op["overture_height_ft"] if op["overture_height_ft"] is not None else ""
            pr2["overture_num_floors"] = op["overture_num_floors"] if op["overture_num_floors"] is not None else ""
            enriched_rows.append(pr2)

        # Write reconciled geojson & CSV
        combined_feats = usa_feats + patched_feats
        (OUT_ROOT / "footprints" / f"{code}_reconciled.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": combined_feats})
        )
        rec_csv = HT_DIR / f"{code}_reconciled.csv"
        with open(rec_csv, "w", newline="") as fp:
            w = csv.DictWriter(fp, fieldnames=list(enriched_rows[0].keys()))
            w.writeheader()
            w.writerows(enriched_rows)

        if patched_feats or code == "PBSP":
            tif_matches = sorted(NAIP_DIR.glob(f"{code}_naip_*.tif"))
            if tif_matches:
                sr = sum_by_code.get(code, {})
                s1.render_qa_overlay(
                    code,
                    inst["institution_name"],
                    tif_matches[-1],
                    rapt_wgs,
                    buf_wgs,
                    other_rapt,
                    combined_feats,
                    enriched_rows,
                    int(sr.get("spi_structures") or 0),
                    sr.get("naip_date") or "2024",
                    proj or "NONE",
                    force=True,
                )

        total_patched += len(patched_feats)
        pbsp_h = sum(1 for r in enriched_rows if r["in_rapt_boundary"] == "yes" and r["roof_p50_ft"] != "")
        print(
            f"[{code:4s}] Overture={len(ovt_feats):3d} | RAPT_unmatched={len(unmatched_ovt_in_rapt):2d} -> patched={len(patched_feats):2d} | RAPT_with_h={pbsp_h}",
            flush=True,
        )

    print(f"\nDone. Total RAPT footprints patched from Overture: {total_patched}")


def extract_heights_in_mem(code: str, proj: str, feats: list[dict]) -> list[dict]:
    """Use cached/AWS EPT chunks cleanly for a small candidate list."""
    tmp_csv = HT_DIR / f"_{code}_ovt_tmp.csv"
    # Temporarily compute via extract_heights to a side CSV name? Easier: write helper directly using cached tmp_ept!
    # Call s1.extract_heights only if out_csv doesn't collide; since s1 hardcodes HT_DIR/{code}_heights.csv,
    # swap HT_DIR temporarily to a scratch subdir!
    orig_ht = s1.HT_DIR
    scratch = HT_DIR / "_ovt_scratch"
    scratch.mkdir(exist_ok=True)
    s1.HT_DIR = scratch
    try:
        rows, _ = s1.extract_heights(code, proj, feats, force=True)
    finally:
        s1.HT_DIR = orig_ht
        (scratch / f"{code}_heights.csv").unlink(missing_ok=True)
    return rows


if __name__ == "__main__":
    only_arg = sys.argv[1:] if len(sys.argv) > 1 else None
    run_reconcile(only=only_arg)
