#!/usr/bin/env python3
"""
Source fetcher and raw LiDAR roof-height extractor across all 34 CDCR institutions:
- Query/cache FEMA/ORNL USA Structures footprints within Prison_Boundaries_RAPT + 300 m buffer.
- Download & mosaic 4-band RGB+NIR 2024 NAIP GeoTIFFs via Microsoft Planetary Computer STAC.
- Extract USGS 3DEP EPT LiDAR roof-height percentiles using shared common.py calibration.
- Render labeled NAIP + LiDAR boundary QA overlay PNGs.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import urllib.parse
import warnings
from pathlib import Path
from typing import Any

warnings.filterwarnings("ignore", category=DeprecationWarning)

import numpy as np
import rasterio
from PIL import ImageDraw
from rasterio.warp import Resampling, reproject
from shapely.geometry import shape
from shapely.ops import transform as shp_transform

from common import (
    ALL34_DIR,
    CLOSED_CODES,
    DATA_BUILDINGS,
    EPT_CACHE,
    FP_DIR,
    HT_DIR,
    NAIP_DIR,
    QA_DIR,
    RAW_DIR,
    TO_3857,
    TO_4326,
    compute_footprint_height_rows,
    curl_bytes,
    curl_json,
    draw_wgs_outline,
    ensure_work_dirs,
    load_ept_points_for_features,
    load_institutions_and_rapt,
    make_wgs_to_px,
    open_naip_rgb_canvas,
    select_ept_project,
)

USA_STRUCTURES_QUERY_URL = (
    "https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/"
    "USA_Structures_View/FeatureServer/0/query"
)
PC_STAC_SEARCH_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/search"


def query_usa_structures(
    code: str,
    rapt_wgs: Any,
    buf_wgs: Any,
    other_rapt: dict[str, Any],
    force: bool = False,
) -> list[dict[str, Any]]:
    """Fetch and cache USA Structures footprints inside the 300 m institutional buffer."""
    out_gj_path = FP_DIR / f"{code}_footprints.geojson"
    if out_gj_path.exists() and not force:
        return json.loads(out_gj_path.read_text())["features"]

    minx, miny, maxx, maxy = buf_wgs.bounds
    features: list[dict[str, Any]] = []
    offset = 0
    while True:
        params = urllib.parse.urlencode({
            "geometry": f"{minx},{miny},{maxx},{maxy}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "BUILD_ID,OCC_CLS,PRIM_OCC,SEC_OCC,HEIGHT,SQFEET,SQMETERS,IMAGE_NAME,IMAGE_DATE",
            "returnGeometry": "true",
            "outSR": "4326",
            "resultRecordCount": "1000",
            "resultOffset": str(offset),
            "f": "geojson",
        })
        gj = curl_json(f"{USA_STRUCTURES_QUERY_URL}?{params}", timeout=60)
        batch = gj.get("features", [])
        features.extend(batch)
        if not gj.get("properties", {}).get("exceededTransferLimit") and len(batch) < 1000:
            break
        offset += len(batch)
        if not batch:
            break

    rapt_3857 = shp_transform(TO_3857, rapt_wgs)
    in_list, buf_list = [], []
    seen_ids: set[Any] = set()
    for feat in features:
        bid = feat["properties"].get("BUILD_ID")
        if bid in seen_ids:
            continue
        seen_ids.add(bid)
        geom = shape(feat["geometry"])
        c = geom.centroid
        if not buf_wgs.contains(c):
            continue
        in_rapt = rapt_wgs.contains(c)
        other_code = ""
        if not in_rapt:
            other_code = next((k for k, og in other_rapt.items() if og.contains(c)), "")
        dist_m = 0.0 if in_rapt else rapt_3857.distance(shp_transform(TO_3857, c)) * math.cos(math.radians(c.y))
        feat["properties"].update({
            "centroid_lon": round(c.x, 7),
            "centroid_lat": round(c.y, 7),
            "in_rapt_boundary": "yes" if in_rapt else "no",
            "other_rapt_code": other_code,
            "dist_to_rapt_m": round(dist_m, 1),
        })
        (in_list if in_rapt else buf_list).append(feat)

    in_list.sort(key=lambda x: (x["properties"]["centroid_lat"], x["properties"]["centroid_lon"]))
    buf_list.sort(key=lambda x: (x["properties"]["dist_to_rapt_m"], x["properties"]["centroid_lat"], x["properties"]["centroid_lon"]))
    for i, feat in enumerate(in_list, 1):
        feat["properties"]["footprint_id"] = f"{code}-fp-{i:03d}"
    for i, feat in enumerate(buf_list, 1):
        feat["properties"]["footprint_id"] = f"{code}-buf-{i:03d}"

    all_feats = in_list + buf_list
    out_gj_path.write_text(json.dumps({"type": "FeatureCollection", "features": all_feats}))
    return all_feats


def fetch_and_save_naip_geotiff(
    code: str, buf_wgs: Any, force: bool = False
) -> tuple[Path | None, str, str, float]:
    """Download and mosaic newest NAIP 4-band RGB+NIR GeoTIFF clipped to the 300 m buffer."""
    existing = sorted(NAIP_DIR.glob(f"{code}_naip_*.tif"))
    if existing and not force:
        tif_path = existing[-1]
        year = tif_path.stem.split("_")[-1]
        with rasterio.open(tif_path) as src:
            tags = src.tags()
        return tif_path, tags.get("naip_date", year), tags.get("naip_items", ""), round(tif_path.stat().st_size / (1024 * 1024), 2)

    minx, miny, maxx, maxy = buf_wgs.bounds
    items = curl_json(
        PC_STAC_SEARCH_URL,
        headers=["Content-Type: application/json"],
        data=json.dumps({"collections": ["naip"], "bbox": [minx, miny, maxx, maxy], "limit": 30}),
        timeout=45,
    ).get("features", [])
    if not items:
        return None, "", "", 0.0

    by_year: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        yr = (item["properties"].get("datetime") or "")[:4]
        by_year.setdefault(yr, []).append(item)
    best_yr = sorted(by_year.keys(), reverse=True)[0]
    pool = sorted(by_year[best_yr], key=lambda x: x["properties"].get("datetime", ""), reverse=True)

    uncovered = buf_wgs
    chosen = []
    for item in pool:
        ig = shape(item["geometry"])
        if ig.intersects(uncovered) and ig.intersection(uncovered).area > 1e-11:
            chosen.append(item)
            uncovered = uncovered.difference(ig)
            if uncovered.area <= 1e-10:
                break
    if not chosen:
        chosen = [pool[0]]

    mosaic = None
    prof = None
    valid_mask = None
    used_ids, dates = [], []
    for idx, item in enumerate(chosen):
        iid = item["id"]
        dt = (item["properties"].get("datetime") or "")[:10]
        url = (
            f"https://planetarycomputer.microsoft.com/api/data/v1/item/bbox/"
            f"{minx:.6f},{miny:.6f},{maxx:.6f},{maxy:.6f}.tif?collection=naip&item={iid}&assets=image"
        )
        tmp_tif = RAW_DIR / f"tmp_{code}_{idx}.tif"
        tmp_tif.write_bytes(curl_bytes(url, timeout=90))
        with rasterio.open(tmp_tif) as src:
            arr = src.read()
            if prof is None:
                prof = src.profile.copy()
                mosaic = np.zeros((4, arr.shape[1], arr.shape[2]), dtype=np.uint8)
                valid_mask = np.zeros((arr.shape[1], arr.shape[2]), dtype=bool)
                alpha = arr[4] if arr.shape[0] >= 5 else (arr[:3].sum(axis=0) > 0)
                fill = alpha > 0
                mosaic[:, fill] = arr[:4, fill]
                valid_mask |= fill
            else:
                nb = min(5, arr.shape[0])
                dst_arr = np.zeros((nb, mosaic.shape[1], mosaic.shape[2]), dtype=np.uint8)
                for b_idx in range(nb):
                    reproject(
                        source=arr[b_idx],
                        destination=dst_arr[b_idx],
                        src_transform=src.transform,
                        src_crs=src.crs,
                        dst_transform=prof["transform"],
                        dst_crs=prof["crs"],
                        resampling=Resampling.nearest,
                    )
                alpha = dst_arr[4] if nb >= 5 else (dst_arr[:3].sum(axis=0) > 0)
                fill = (alpha > 0) & (~valid_mask)
                mosaic[:, fill] = dst_arr[:4, fill]
                valid_mask |= fill
        tmp_tif.unlink(missing_ok=True)
        used_ids.append(iid)
        dates.append(dt)

    out_tif = NAIP_DIR / f"{code}_naip_{best_yr}.tif"
    prof.update(
        count=4, dtype="uint8", tiled=True, blockxsize=256, blockysize=256,
        compress="deflate", predictor=2,
    )
    with rasterio.open(out_tif, "w", **prof) as dst:
        dst.write(mosaic)
        dst.set_band_description(1, "Red")
        dst.set_band_description(2, "Green")
        dst.set_band_description(3, "Blue")
        dst.set_band_description(4, "NIR")
        dst.update_tags(naip_date=";".join(sorted(set(dates))), naip_items=";".join(used_ids), AREA_OR_POINT="Area")

    return out_tif, ";".join(sorted(set(dates))), ";".join(used_ids), round(out_tif.stat().st_size / (1024 * 1024), 2)


def extract_heights(
    code: str, proj: str | None, feats: list[dict[str, Any]], force: bool = False
) -> tuple[list[dict[str, Any]], int]:
    """Compute or load cached raw LiDAR height measurements for a prison's footprints."""
    out_csv = HT_DIR / f"{code}_heights.csv"
    if out_csv.exists() and not force:
        with open(out_csv) as f:
            rows = list(csv.DictReader(f))
        return rows, 0

    px, py, pz, pcls, used_depth = load_ept_points_for_features(code, proj, feats, allow_remote=True)
    rows = compute_footprint_height_rows(
        code, proj, feats, px, py, pz, pcls, used_depth=used_depth or "", footprint_source="usa_structures"
    )
    if rows:
        with open(out_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    return rows, int(len(px))


def render_qa_overlay(
    code: str,
    inst_name: str,
    tif_path: Path | None,
    rapt_wgs: Any,
    buf_wgs: Any,
    other_rapt: dict[str, Any],
    feats: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    spi_count: int,
    naip_date: str,
    proj: str | None,
    force: bool = False,
) -> None:
    """Render footprint & boundary QA overlay on the facility's NAIP imagery."""
    out_png = QA_DIR / f"{code}_qa.png"
    if (out_png.exists() and not force) or tif_path is None or not tif_path.exists():
        return

    img, transform, scale = open_naip_rgb_canvas(tif_path, max_dim=1800)
    new_w, _ = img.size
    draw = ImageDraw.Draw(img, "RGBA")
    to_px = make_wgs_to_px(transform, scale)

    draw_wgs_outline(draw, buf_wgs, to_px, (0, 230, 255, 220), width=2)
    for og in other_rapt.values():
        if og.intersects(buf_wgs):
            draw_wgs_outline(draw, og, to_px, (255, 80, 220, 220), width=3)
    draw_wgs_outline(draw, rapt_wgs, to_px, (255, 235, 0, 255), width=4)

    row_by_id = {r["footprint_id"]: r for r in rows}
    for feat in feats:
        p = feat["properties"]
        fid = p["footprint_id"]
        r = row_by_id.get(fid, {})
        in_rapt = p["in_rapt_boundary"] == "yes"
        zero = r.get("zero_roof_flag") == "yes"
        multi = r.get("multi_tier_flag") == "yes"

        if zero:
            col = (255, 50, 50, 240)
        elif in_rapt:
            col = (0, 255, 110, 230)
        elif p.get("other_rapt_code"):
            col = (210, 120, 255, 200)
        else:
            col = (255, 165, 0, 230)

        draw_wgs_outline(draw, shape(feat["geometry"]), to_px, col, width=3 if multi else 2)
        cx, cy = to_px(p["centroid_lon"], p["centroid_lat"])
        if not in_rapt:
            short_lbl = f"B{fid.split('-')[-1]}"
        elif "-ovt-" in fid:
            short_lbl = f"P{fid.split('-')[-1]}"
        elif "-lid-" in fid:
            short_lbl = f"L{fid.split('-')[-1]}"
        else:
            short_lbl = fid.split("-")[-1]
        if multi:
            short_lbl += "*"
        draw.text((cx - 8, cy - 5), short_lbl, fill=(255, 255, 255, 255), stroke_width=1, stroke_fill=(0, 0, 0, 255))

    in_n = sum(1 for f in feats if f["properties"]["in_rapt_boundary"] == "yes")
    buf_n = sum(1 for f in feats if f["properties"]["in_rapt_boundary"] == "no" and not f["properties"]["other_rapt_code"])
    zero_n = sum(1 for r in rows if r["in_rapt_boundary"] == "yes" and r["zero_roof_flag"] == "yes")
    closed_tag = " [CLOSED]" if code in CLOSED_CODES else ""
    banner = (
        f"{code}{closed_tag} - {inst_name} | NAIP {naip_date} | LiDAR: {proj or 'NONE'}\n"
        f"Yellow=RAPT | Cyan=300m buf | Green=in-RAPT ({in_n}) | Orange=outside-buf ({buf_n}) | Red=0-roof ({zero_n}) | * multi-tier | SPI={spi_count}"
    )
    draw.rectangle([(0, 0), (new_w, 34)], fill=(0, 0, 0, 185))
    draw.text((8, 5), banner, fill=(255, 255, 255, 255))
    img.save(out_png)


def run_fetch(
    only: list[str] | None = None,
    force_footprints: bool = False,
    force_naip: bool = False,
    force_heights: bool = False,
    force_qa: bool = False,
) -> None:
    """Run source fetch, height extraction, and boundary QA rendering across institutions."""
    ensure_work_dirs()
    insts, rapt_by_code = load_institutions_and_rapt()
    ept_raw = json.loads((RAW_DIR / "usgs_lidar_resources.geojson").read_text())["features"]
    ept_feats = [(f["properties"]["name"], f["properties"].get("count", 0), shape(f["geometry"])) for f in ept_raw]

    spi_by_code: dict[str, list[dict[str, str]]] = {}
    with open(DATA_BUILDINGS / "spi_cdcr_structures.csv") as f:
        for r in csv.DictReader(f):
            spi_by_code.setdefault(r["cdcr_code"], []).append(r)

    cond_by_code = {}
    with open(DATA_BUILDINGS / "condition_assessment_2026.csv") as f:
        for r in csv.DictReader(f):
            if r["system"] == "Roofs":
                cond_by_code[r["institution"]] = r["rating"]

    summary_rows = []
    for inst in insts:
        code = inst["cdcr_code"]
        if only and code not in only:
            continue
        aliases = [code] + [a.strip() for a in (inst.get("alias_codes") or "").split(";") if a.strip()]
        rapt_wgs = rapt_by_code[code]
        other_rapt = {k: v for k, v in rapt_by_code.items() if k != code}
        buf_wgs = shp_transform(
            TO_4326,
            shp_transform(TO_3857, rapt_wgs).buffer(300.0 / math.cos(math.radians(rapt_wgs.centroid.y))),
        )

        proj, overlap_frac, lyr = select_ept_project(rapt_wgs, ept_feats)
        if not proj and code == "PBSP" and (EPT_CACHE / "CA_NorthernCA_6_B22_PBSP").exists():
            proj, overlap_frac, lyr = "CA_NorthernCA_6_B22", 1.0, 2022

        feats = query_usa_structures(code, rapt_wgs, buf_wgs, other_rapt, force=force_footprints)
        tif_path, naip_date, _, tif_mb = fetch_and_save_naip_geotiff(code, buf_wgs, force=force_naip)
        rows, pts_loaded = extract_heights(code, proj, feats, force=force_heights)

        spi_list = spi_by_code.get(code, [])
        spi_cnt = len(spi_list)
        spi_housing = sum(
            1 for r in spi_list
            if any(k in r["structure_type"] for k in ("DORM", "HOUS", "CELL", "BARRACK")) or "HOUS" in r["structure_name"]
        )
        spi_sqft = sum(int(float(r["sqft"] or 0)) for r in spi_list)

        render_qa_overlay(
            code, inst["institution_name"], tif_path, rapt_wgs, buf_wgs,
            other_rapt, feats, rows, spi_cnt, naip_date, proj, force=force_qa,
        )

        in_rapt_rows = [r for r in rows if r["in_rapt_boundary"] == "yes"]
        buf_only_rows = [r for r in rows if r["in_rapt_boundary"] == "no" and not r["other_rapt_code"]]
        with_h = sum(1 for r in in_rapt_rows if r["roof_p50_ft"] != "")
        zero_r = sum(1 for r in in_rapt_rows if r["zero_roof_flag"] == "yes")
        multi_n = sum(1 for r in in_rapt_rows if r["multi_tier_flag"] == "yes")
        fp_sqft = sum(float(r["footprint_sqft"] or 0) for r in in_rapt_rows)
        roof_rating = next((cond_by_code[a] for a in aliases if a in cond_by_code), "")

        summary_rows.append({
            "cdcr_code": code,
            "is_closed": "yes" if code in CLOSED_CODES else "no",
            "lidar_project": proj or "",
            "lidar_year": lyr or "",
            "lidar_overlap_frac": overlap_frac,
            "ept_pts_loaded": pts_loaded,
            "naip_date": naip_date,
            "naip_tif_mb": tif_mb,
            "rapt_footprints": len(in_rapt_rows),
            "rapt_with_height": with_h,
            "rapt_zero_roof": zero_r,
            "rapt_multi_tier": multi_n,
            "buf_300m_non_prison_fps": len(buf_only_rows),
            "rapt_footprint_sqft": int(round(fp_sqft)),
            "spi_structures": spi_cnt,
            "spi_housing_rows": spi_housing,
            "spi_total_sqft": spi_sqft,
            "cond_roofs_2026": roof_rating,
        })
        print(
            f"[{code:4s}] RAPT={len(in_rapt_rows):3d} (h={with_h:3d}, zero={zero_r:2d}, multi={multi_n:2d}) | "
            f"buf300={len(buf_only_rows):3d} | SPI={spi_cnt:3d} | NAIP={tif_mb:.1f}MB | LiDAR={proj or 'NONE'}",
            flush=True,
        )

    if not only and summary_rows:
        out_sum = ALL34_DIR / "all_34_summary.csv"
        with open(out_sum, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
            w.writeheader()
            w.writerows(summary_rows)
        print(f"\nWrote {out_sum} ({len(summary_rows)} institutions)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch USA Structures, NAIP 2024 GeoTIFFs, and raw USGS 3DEP EPT LiDAR heights.")
    parser.add_argument("--only", nargs="*", help="Only process specified CDCR codes")
    parser.add_argument("--force-heights", action="store_true")
    parser.add_argument("--force-naip", action="store_true")
    parser.add_argument("--force-footprints", action="store_true")
    parser.add_argument("--force-qa", action="store_true")
    args = parser.parse_args()
    run_fetch(
        only=args.only,
        force_footprints=args.force_footprints,
        force_naip=args.force_naip,
        force_heights=args.force_heights,
        force_qa=args.force_qa,
    )


if __name__ == "__main__":
    main()
