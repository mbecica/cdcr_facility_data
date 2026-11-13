#!/usr/bin/env python3
"""
Step 1 pipeline across all 34 CDCR institutions:
1. Fetch/cache USA Structures footprints within Prison_Boundaries_RAPT + 300 m buffer,
   tagging in_rapt_boundary, dist_to_rapt_m, and neighboring prison overlaps (other_rapt_code).
2. Download & mosaic lossless Deflate-compressed 4-band RGB+NIR 2024 NAIP GeoTIFFs
   into sources/imagery/naip_2024/ (gitignored) for boundary QA and future ML reuse.
3. Extract raw building roof heights via AWS EPT (usgs-lidar-public) using per-building
   3-15 m surrounding ground ring calibration and 1 m eroded roof interiors.
4. Render labeled boundary QA overlay PNGs and cross-check against SPI structure counts.
"""

import argparse
import csv
import json
import math
import re
import subprocess
import urllib.parse
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

warnings.filterwarnings("ignore", category=DeprecationWarning)
from pathlib import Path

import laspy
import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.warp import Resampling, reproject
from PIL import Image, ImageDraw
from pyproj import Transformer
from shapely import contains_xy
from shapely.geometry import box, shape
from shapely.ops import transform as shp_transform, unary_union

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = Path(__file__).resolve().parent
WORK_DIR = ROOT / "notes" / "building_heights_pilot"
RAW = WORK_DIR / "raw"
EPT_CACHE = WORK_DIR / "tmp_ept"
OUT_ROOT = WORK_DIR / "all_34"
FP_DIR = OUT_ROOT / "footprints"
HT_DIR = OUT_ROOT / "heights"
QA_DIR = OUT_ROOT / "qa_overlays"
NAIP_DIR = ROOT / "sources" / "imagery" / "naip_2024"

for d in (RAW, EPT_CACHE, OUT_ROOT, FP_DIR, HT_DIR, QA_DIR, NAIP_DIR):
    d.mkdir(parents=True, exist_ok=True)

TO_3857 = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform
TO_4326 = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True).transform
M_TO_FT = 3.28084
CLOSED_CODES = {"CAC", "CVSP", "FWF"}


def curl_bytes(url: str, headers: list[str] | None = None, data: str | None = None, timeout: int = 45) -> bytes:
    cmd = ["curl", "-sS", "--fail", "--max-time", str(timeout), "-L", "-A", "cdcr-facility-data/1.0"]
    for h in (headers or []):
        cmd += ["-H", h]
    if data is not None:
        cmd += ["-X", "POST", "--data-raw", data]
    cmd.append(url)
    res = subprocess.run(cmd, capture_output=True, check=True)
    return res.stdout


def curl_json(url: str, headers: list[str] | None = None, data: str | None = None, timeout: int = 45) -> dict:
    return json.loads(curl_bytes(url, headers=headers, data=data, timeout=timeout).decode("utf-8"))


def parse_ept_year(name: str) -> int:
    m = re.search(r"(?:19|20)\d{2}", name)
    years = [int(y) for y in re.findall(r"(?:19|20)\d{2}", name)]
    if years:
        return max(years)
    m2 = re.search(r"_[A-Z](\d{2})$", name)
    if m2:
        return 2000 + int(m2.group(1))
    return 0


def select_ept_project(rapt_geom_wgs, ept_feats: list[dict]) -> tuple[str | None, float, int]:
    candidates = []
    for name, cnt, eg in ept_feats:
        if eg.intersects(rapt_geom_wgs):
            frac = eg.intersection(rapt_geom_wgs).area / rapt_geom_wgs.area
            if frac > 0.05:
                yr = parse_ept_year(name)
                candidates.append((frac >= 0.98, round(frac, 3), yr, cnt or 0, name))
    if not candidates:
        return None, 0.0, 0
    candidates.sort(reverse=True)
    _, frac, yr, _, name = candidates[0]
    return name, frac, yr


def query_usa_structures(code: str, rapt_wgs, buf_wgs, other_rapt: dict[str, object], force: bool = False) -> list[dict]:
    out_gj_path = FP_DIR / f"{code}_footprints.geojson"
    if out_gj_path.exists() and not force:
        return json.loads(out_gj_path.read_text())["features"]

    minx, miny, maxx, maxy = buf_wgs.bounds
    base = "https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/USA_Structures_View/FeatureServer/0/query"
    features = []
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
        gj = curl_json(f"{base}?{params}", timeout=60)
        batch = gj.get("features", [])
        features.extend(batch)
        if not gj.get("properties", {}).get("exceededTransferLimit") and len(batch) < 1000:
            break
        offset += len(batch)
        if not batch:
            break

    rapt_3857 = shp_transform(TO_3857, rapt_wgs)
    in_list, buf_list = [], []
    seen_ids = set()
    for f in features:
        bid = f["properties"].get("BUILD_ID")
        if bid in seen_ids:
            continue
        seen_ids.add(bid)
        g = shape(f["geometry"])
        pt = g.representative_point() if not rapt_wgs.contains(g.centroid) else g.centroid
        c = g.centroid
        if not buf_wgs.contains(c):
            continue
        in_rapt = rapt_wgs.contains(c)
        other_code = ""
        if not in_rapt:
            for ocode, og in other_rapt.items():
                if og.contains(c):
                    other_code = ocode
                    break
        c_3857 = shp_transform(TO_3857, c)
        dist_m = 0.0 if in_rapt else rapt_3857.distance(c_3857) * math.cos(math.radians(c.y))
        f["properties"]["centroid_lon"] = round(c.x, 7)
        f["properties"]["centroid_lat"] = round(c.y, 7)
        f["properties"]["in_rapt_boundary"] = "yes" if in_rapt else "no"
        f["properties"]["other_rapt_code"] = other_code
        f["properties"]["dist_to_rapt_m"] = round(dist_m, 1)
        (in_list if in_rapt else buf_list).append(f)

    in_list.sort(key=lambda x: (x["properties"]["centroid_lat"], x["properties"]["centroid_lon"]))
    buf_list.sort(key=lambda x: (x["properties"]["dist_to_rapt_m"], x["properties"]["centroid_lat"], x["properties"]["centroid_lon"]))
    for i, f in enumerate(in_list, 1):
        f["properties"]["footprint_id"] = f"{code}-fp-{i:03d}"
    for i, f in enumerate(buf_list, 1):
        f["properties"]["footprint_id"] = f"{code}-buf-{i:03d}"

    all_feats = in_list + buf_list
    out_gj_path.write_text(json.dumps({"type": "FeatureCollection", "features": all_feats}))
    return all_feats


def fetch_and_save_naip_geotiff(code: str, buf_wgs, force: bool = False) -> tuple[Path | None, str, str, float]:
    # Search existing file matching pattern
    existing = sorted(NAIP_DIR.glob(f"{code}_naip_*.tif"))
    if existing and not force:
        tif_path = existing[-1]
        year = tif_path.stem.split("_")[-1]
        with rasterio.open(tif_path) as src:
            tags = src.tags()
        return tif_path, tags.get("naip_date", year), tags.get("naip_items", ""), round(tif_path.stat().st_size / (1024 * 1024), 2)

    minx, miny, maxx, maxy = buf_wgs.bounds
    items = curl_json(
        "https://planetarycomputer.microsoft.com/api/stac/v1/search",
        headers=["Content-Type: application/json"],
        data=json.dumps({"collections": ["naip"], "bbox": [minx, miny, maxx, maxy], "limit": 30}),
        timeout=45,
    ).get("features", [])
    if not items:
        return None, "", "", 0.0

    # Group by year, pick newest year (usually 2024)
    by_year: dict[str, list[dict]] = {}
    for it in items:
        yr = (it["properties"].get("datetime") or "")[:4]
        by_year.setdefault(yr, []).append(it)
    best_yr = sorted(by_year.keys(), reverse=True)[0]
    pool = sorted(by_year[best_yr], key=lambda x: x["properties"].get("datetime", ""), reverse=True)

    # Greedily cover buf_wgs with minimal NAIP items
    uncovered = buf_wgs
    chosen = []
    for it in pool:
        ig = shape(it["geometry"])
        if ig.intersects(uncovered):
            area_gain = ig.intersection(uncovered).area
            if area_gain > 1e-11:
                chosen.append(it)
                uncovered = uncovered.difference(ig)
                if uncovered.area <= 1e-10:
                    break
    if not chosen:
        chosen = [pool[0]]

    mosaic = None
    prof = None
    used_ids = []
    dates = []
    for idx, it in enumerate(chosen):
        iid = it["id"]
        dt = (it["properties"].get("datetime") or "")[:10]
        url = f"https://planetarycomputer.microsoft.com/api/data/v1/item/bbox/{minx:.6f},{miny:.6f},{maxx:.6f},{maxy:.6f}.tif?collection=naip&item={iid}&assets=image"
        tmp_tif = RAW / f"tmp_{code}_{idx}.tif"
        tmp_tif.write_bytes(curl_bytes(url, timeout=90))
        with rasterio.open(tmp_tif) as src:
            arr = src.read()  # (bands, H, W)
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
        count=4,
        dtype="uint8",
        tiled=True,
        blockxsize=256,
        blockysize=256,
        compress="deflate",
        predictor=2,
    )
    with rasterio.open(out_tif, "w", **prof) as dst:
        dst.write(mosaic)
        dst.set_band_description(1, "Red")
        dst.set_band_description(2, "Green")
        dst.set_band_description(3, "Blue")
        dst.set_band_description(4, "NIR")
        dst.update_tags(naip_date=";".join(sorted(set(dates))), naip_items=";".join(used_ids), AREA_OR_POINT="Area")

    mb = round(out_tif.stat().st_size / (1024 * 1024), 2)
    return out_tif, ";".join(sorted(set(dates))), ";".join(used_ids), mb


def child_box(b: list[float], dx: int, dy: int, dz: int) -> list[float]:
    mx, my, mz = (b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2
    return [
        mx if dx else b[0], my if dy else b[1], mz if dz else b[2],
        b[3] if dx else mx, b[4] if dy else my, b[5] if dz else mz,
    ]


def collect_ept_chunks_adaptive(base_url: str, ept: dict, target_geom_3857, max_pts: int = 18_000_000) -> tuple[list[tuple[str, int]], int]:
    eb = ept["bounds"]
    all_nodes: list[tuple[int, str, int]] = []

    def walk_hier(root_key: str, root_box: list[float]):
        hier = curl_json(f"{base_url}/ept-hierarchy/{root_key}.json", timeout=30)
        stack = [(root_key, root_box)]
        while stack:
            k, nb = stack.pop()
            cnt = hier.get(k)
            if cnt is None or not target_geom_3857.intersects(box(nb[0], nb[1], nb[3], nb[4])):
                continue
            if cnt == -1:
                walk_hier(k, nb)
                continue
            d, x, y, z = map(int, k.split("-"))
            if d <= 13 and cnt > 0:
                all_nodes.append((d, k, cnt))
            if d < 13:
                for dx in (0, 1):
                    for dy in (0, 1):
                        for dz in (0, 1):
                            ck = f"{d+1}-{2*x+dx}-{2*y+dy}-{2*z+dz}"
                            if ck in hier:
                                stack.append((ck, child_box(nb, dx, dy, dz)))

    walk_hier("0-0-0-0", eb)
    chosen_depth = 13
    for d_try in (13, 12, 11):
        sub_pts = sum(cnt for d, _, cnt in all_nodes if d <= d_try)
        if sub_pts <= max_pts or d_try == 11:
            chosen_depth = d_try
            break
    selected = [(k, cnt) for d, k, cnt in all_nodes if d <= chosen_depth]
    return selected, chosen_depth


def fetch_chunk_points(base_url: str, cache_dir: Path, key: str):
    p = cache_dir / f"{key}.laz"
    if not p.exists() or p.stat().st_size == 0:
        p.write_bytes(curl_bytes(f"{base_url}/ept-data/{key}.laz", timeout=60))
    las = laspy.read(p)
    return (
        np.asarray(las.x),
        np.asarray(las.y),
        np.asarray(las.z),
        np.asarray(las.classification),
    )


def extract_heights(code: str, proj: str | None, feats: list[dict], force: bool = False) -> tuple[list[dict], int]:
    out_csv = HT_DIR / f"{code}_heights.csv"
    if out_csv.exists() and not force:
        with open(out_csv, newline="") as fp:
            rows = list(csv.DictReader(fp))
        return rows, 0

    if not proj or not feats:
        rows = []
        for f in feats:
            p = f["properties"]
            rows.append({
                "cdcr_code": code,
                "footprint_id": p["footprint_id"],
                "in_rapt_boundary": p["in_rapt_boundary"],
                "other_rapt_code": p["other_rapt_code"],
                "dist_to_rapt_m": p["dist_to_rapt_m"],
                "usa_structures_build_id": p["BUILD_ID"],
                "occ_cls": p.get("OCC_CLS", ""),
                "prim_occ": p.get("PRIM_OCC", ""),
                "lat": p["centroid_lat"],
                "lon": p["centroid_lon"],
                "footprint_sqft": round(p["SQFEET"], 1) if p.get("SQFEET") else "",
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
                "lidar_project": proj or "",
                "ept_depth": "",
            })
        if rows:
            with open(out_csv, "w", newline="") as fp:
                w = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
        return rows, 0

    polys_3857 = [shp_transform(TO_3857, shape(f["geometry"])) for f in feats]
    mean_lat = sum(f["properties"]["centroid_lat"] for f in feats) / len(feats)
    m_to_3857 = 1.0 / math.cos(math.radians(mean_lat))
    ring_15 = 15.0 * m_to_3857
    ring_3 = 3.0 * m_to_3857
    erode_1 = 1.0 * m_to_3857

    union_target = unary_union([g.buffer(ring_15) for g in polys_3857])
    pbsp_local = EPT_CACHE / "CA_NorthernCA_6_B22_PBSP"
    if proj == "CA_NorthernCA_6_B22" and pbsp_local.exists():
        # PBSP fallback: use cached raw S3 octree LAZ chunks (catalog ept.json unpublished on rockyweb/S3)
        bx0, by0, bx1, by1 = union_target.bounds
        xs_list, ys_list, zs_list, cls_list = [], [], [], []
        for laz_path in sorted(pbsp_local.glob("*.laz")):
            with laspy.open(laz_path) as f:
                h = f.header
                if h.maxs[0] < bx0 or h.mins[0] > bx1 or h.maxs[1] < by0 or h.mins[1] > by1:
                    continue
                las = f.read()
                x = np.asarray(las.x)
                y = np.asarray(las.y)
                z = np.asarray(las.z)
                c = np.asarray(las.classification)
                m = (x >= bx0) & (x <= bx1) & (y >= by0) & (y <= by1)
                if m.any():
                    xs_list.append(x[m])
                    ys_list.append(y[m])
                    zs_list.append(z[m])
                    cls_list.append(c[m])
        used_depth = 12
    else:
        base_url = f"https://s3-us-west-2.amazonaws.com/usgs-lidar-public/{proj}"
        ept = curl_json(f"{base_url}/ept.json", timeout=30)
        horiz = str((ept.get("srs") or {}).get("horizontal", ""))
        assert horiz == "3857", f"Unexpected EPT SRS horizontal={horiz} for {proj}"

        chunks, used_depth = collect_ept_chunks_adaptive(base_url, ept, union_target)
        cache_dir = EPT_CACHE / proj
        cache_dir.mkdir(parents=True, exist_ok=True)

        xs_list, ys_list, zs_list, cls_list = [], [], [], []
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs = [ex.submit(fetch_chunk_points, base_url, cache_dir, k) for k, _ in chunks]
            for fut in as_completed(futs):
                x, y, z, c = fut.result()
                xs_list.append(x); ys_list.append(y); zs_list.append(z); cls_list.append(c)

    if xs_list:
        px = np.concatenate(xs_list)
        py = np.concatenate(ys_list)
        pz = np.concatenate(zs_list)
        pcls = np.concatenate(cls_list)
    else:
        px = py = pz = pcls = np.array([])

    rows = []
    for feat, poly in zip(feats, polys_3857):
        p = feat["properties"]
        bx0, by0, bx1, by1 = poly.bounds
        if len(px):
            bmask = (px >= bx0 - ring_15) & (px <= bx1 + ring_15) & (py >= by0 - ring_15) & (py <= by1 + ring_15)
            lx, ly, lz, lcls = px[bmask], py[bmask], pz[bmask], pcls[bmask]
        else:
            lx = ly = lz = lcls = np.array([])

        ring = poly.buffer(ring_15).difference(poly.buffer(ring_3))
        in_ring = contains_xy(ring, lx, ly) if len(lx) else np.array([], dtype=bool)
        ring_gnd = lz[in_ring & (lcls == 2)] if len(lx) else np.array([])
        gnd_method = "ring_class2"
        if len(ring_gnd) < 8 and len(lx):
            ring_all = lz[in_ring]
            if len(ring_all) >= 8:
                q15 = np.percentile(ring_all, 15)
                ring_gnd = ring_all[ring_all <= q15]
                gnd_method = "ring_p15"
            else:
                ring_gnd = np.array([])
                gnd_method = "none"

        core = poly.buffer(-erode_1)
        if not core.is_empty and core.area > 0.25 * poly.area and len(lx):
            in_bldg = contains_xy(core, lx, ly)
            if in_bldg.sum() < 12:
                in_bldg = contains_xy(poly, lx, ly)
        elif len(lx):
            in_bldg = contains_xy(poly, lx, ly)
        else:
            in_bldg = np.array([], dtype=bool)

        bz = lz[in_bldg] if len(lx) else np.array([])
        bcls = lcls[in_bldg] if len(lx) else np.array([])

        if len(ring_gnd) > 0 and len(bz) > 0:
            gz = float(np.median(ring_gnd))
            gslope_ft = float((np.percentile(ring_gnd, 90) - np.percentile(ring_gnd, 10)) * M_TO_FT)
            rel_z = bz - gz
            roof = rel_z[(rel_z >= 1.8) & (rel_z <= 45.0)]
        else:
            gslope_ft = None
            roof = np.array([])

        cls_counts = {int(k): int(v) for k, v in zip(*np.unique(bcls, return_counts=True))} if len(bcls) else {}
        has_roof = len(roof) >= 5
        p10 = round(float(np.percentile(roof, 10)) * M_TO_FT, 1) if has_roof else ""
        p25 = round(float(np.percentile(roof, 25)) * M_TO_FT, 1) if has_roof else ""
        p50 = round(float(np.percentile(roof, 50)) * M_TO_FT, 1) if has_roof else ""
        p75 = round(float(np.percentile(roof, 75)) * M_TO_FT, 1) if has_roof else ""
        p90 = round(float(np.percentile(roof, 90)) * M_TO_FT, 1) if has_roof else ""
        p98 = round(float(np.percentile(roof, 98)) * M_TO_FT, 1) if has_roof else ""
        spread = round(p90 - p25, 1) if has_roof else ""

        rows.append({
            "cdcr_code": code,
            "footprint_id": p["footprint_id"],
            "in_rapt_boundary": p["in_rapt_boundary"],
            "other_rapt_code": p["other_rapt_code"],
            "dist_to_rapt_m": p["dist_to_rapt_m"],
            "usa_structures_build_id": p["BUILD_ID"],
            "occ_cls": p.get("OCC_CLS", ""),
            "prim_occ": p.get("PRIM_OCC", ""),
            "lat": p["centroid_lat"],
            "lon": p["centroid_lon"],
            "footprint_sqft": round(p["SQFEET"], 1) if p.get("SQFEET") else "",
            "pts_inside": int(in_bldg.sum()) if len(in_bldg) else 0,
            "roof_pts": int(len(roof)),
            "ground_pts": int(len(ring_gnd)),
            "ground_method": gnd_method,
            "ground_slope_ft": round(gslope_ft, 1) if gslope_ft is not None else "",
            "roof_p10_ft": p10,
            "roof_p25_ft": p25,
            "roof_p50_ft": p50,
            "roof_p75_ft": p75,
            "roof_p90_ft": p90,
            "roof_p98_ft": p98,
            "roof_spread_ft": spread,
            "multi_tier_flag": "yes" if (has_roof and spread >= 4.5) else "no",
            "zero_roof_flag": "no" if has_roof else "yes",
            "bldg_cls_counts": json.dumps(cls_counts),
            "lidar_project": proj,
            "ept_depth": used_depth,
        })

    if rows:
        with open(out_csv, "w", newline="") as fp:
            w = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    return rows, len(px)


def render_qa_overlay(
    code: str,
    inst_name: str,
    tif_path: Path | None,
    rapt_wgs,
    buf_wgs,
    other_rapt: dict[str, object],
    feats: list[dict],
    rows: list[dict],
    spi_count: int,
    naip_date: str,
    proj: str | None,
    force: bool = False,
) -> None:
    out_png = QA_DIR / f"{code}_qa.png"
    if out_png.exists() and not force:
        return
    if tif_path is None or not tif_path.exists():
        return

    with rasterio.open(tif_path) as src:
        rgb = np.transpose(src.read([1, 2, 3]), (1, 2, 0))
        transform = src.transform
        h, w = rgb.shape[:2]

    # Downsample slightly if huge so PNG stays crisp and fast to inspect (~1800 px max dim)
    scale = min(1.0, 1800.0 / max(h, w))
    new_w, new_h = int(w * scale), int(h * scale)
    img = Image.fromarray(rgb, mode="RGB")
    if scale < 1.0:
        img = img.resize((new_w, new_h), Image.Resampling.BILINEAR)
    draw = ImageDraw.Draw(img, "RGBA")

    def to_px(lon: float, lat: float) -> tuple[float, float]:
        col, row = ~transform * (lon, lat)
        return col * scale, row * scale

    def draw_poly_outline(geom, color, width=2):
        geoms = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        for poly in geoms:
            pts = [to_px(x, y) for x, y in poly.exterior.coords]
            if len(pts) >= 2:
                draw.line(pts, fill=color, width=width)

    # Buffer & adjacent prison boundaries
    draw_poly_outline(buf_wgs, (0, 230, 255, 220), width=2)
    for ocode, og in other_rapt.items():
        if og.intersects(buf_wgs):
            draw_poly_outline(og, (255, 80, 220, 220), width=3)
    draw_poly_outline(rapt_wgs, (255, 235, 0, 255), width=4)

    row_by_id = {r["footprint_id"]: r for r in rows}
    for f in feats:
        p = f["properties"]
        fid = p["footprint_id"]
        r = row_by_id.get(fid, {})
        in_rapt = p["in_rapt_boundary"] == "yes"
        zero = r.get("zero_roof_flag") == "yes"
        multi = r.get("multi_tier_flag") == "yes"
        other = bool(p.get("other_rapt_code"))

        if zero:
            col = (255, 50, 50, 240)
        elif in_rapt:
            col = (0, 255, 110, 230)
        elif other:
            col = (210, 120, 255, 200)
        else:
            col = (255, 165, 0, 230)

        g = shape(f["geometry"])
        draw_poly_outline(g, col, width=2 if not multi else 3)

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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", help="Only process specified CDCR codes")
    parser.add_argument("--force-heights", action="store_true")
    parser.add_argument("--force-naip", action="store_true")
    parser.add_argument("--force-footprints", action="store_true")
    parser.add_argument("--force-qa", action="store_true")
    args = parser.parse_args()

    rapt_raw = json.loads((RAW / "Prison_Boundaries_RAPT.geojson").read_text())["features"]
    rapt_by_fid = {str(f["properties"]["FACILITYID"]).strip(): shape(f["geometry"]) for f in rapt_raw if f["properties"].get("FACILITYID")}

    ept_raw = json.loads((RAW / "usgs_lidar_resources.geojson").read_text())["features"]
    ept_feats = [(f["properties"]["name"], f["properties"].get("count", 0), shape(f["geometry"])) for f in ept_raw]

    spi_rows = list(csv.DictReader(open(ROOT / "data" / "buildings" / "spi_cdcr_structures.csv")))
    spi_by_code: dict[str, list[dict]] = {}
    for r in spi_rows:
        spi_by_code.setdefault(r["cdcr_code"], []).append(r)

    cond_by_code = {}
    for r in csv.DictReader(open(ROOT / "data" / "buildings" / "condition_assessment_2026.csv")):
        if r["system"] == "Roofs":
            cond_by_code[r["institution"]] = r["rating"]

    insts = list(csv.DictReader(open(ROOT / "crosswalk" / "institutions.csv")))
    rapt_by_code = {r["cdcr_code"]: rapt_by_fid[r["fema_facilityid"].strip()] for r in insts}

    summary_rows = []
    for inst in insts:
        code = inst["cdcr_code"]
        if args.only and code not in args.only:
            continue
        aliases = [code] + [a.strip() for a in (inst.get("alias_codes") or "").split(";") if a.strip()]
        rapt_wgs = rapt_by_code[code]
        other_rapt = {k: v for k, v in rapt_by_code.items() if k != code}

        mean_lat = rapt_wgs.centroid.y
        buf_300_3857 = shp_transform(TO_3857, rapt_wgs).buffer(300.0 / math.cos(math.radians(mean_lat)))
        buf_wgs = shp_transform(TO_4326, buf_300_3857)

        proj, overlap_frac, lyr = select_ept_project(rapt_wgs, ept_feats)
        if not proj and code == "PBSP" and (EPT_CACHE / "CA_NorthernCA_6_B22_PBSP").exists():
            proj, overlap_frac, lyr = "CA_NorthernCA_6_B22", 1.0, 2022
        feats = query_usa_structures(code, rapt_wgs, buf_wgs, other_rapt, force=args.force_footprints)
        tif_path, naip_date, naip_items, tif_mb = fetch_and_save_naip_geotiff(code, buf_wgs, force=args.force_naip)
        rows, pts_loaded = extract_heights(code, proj, feats, force=args.force_heights)

        spi_list = spi_by_code.get(code, [])
        spi_cnt = len(spi_list)
        spi_housing = sum(1 for r in spi_list if any(k in r["structure_type"] for k in ("DORM", "HOUS", "CELL", "BARRACK")) or "HOUS" in r["structure_name"])
        spi_sqft = sum(int(float(r["sqft"] or 0)) for r in spi_list)

        render_qa_overlay(code, inst["institution_name"], tif_path, rapt_wgs, buf_wgs, other_rapt, feats, rows, spi_cnt, naip_date, proj, force=args.force_qa)

        in_rapt_rows = [r for r in rows if r["in_rapt_boundary"] == "yes"]
        buf_only_rows = [r for r in rows if r["in_rapt_boundary"] == "no" and not r["other_rapt_code"]]
        with_h = sum(1 for r in in_rapt_rows if r["roof_p50_ft"] != "")
        zero_r = sum(1 for r in in_rapt_rows if r["zero_roof_flag"] == "yes")
        multi_n = sum(1 for r in in_rapt_rows if r["multi_tier_flag"] == "yes")
        fp_sqft = sum(float(r["footprint_sqft"] or 0) for r in in_rapt_rows)
        roof_rating = next((cond_by_code[a] for a in aliases if a in cond_by_code), "")

        srow = {
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
        }
        summary_rows.append(srow)
        print(
            f"[{code:4s}] RAPT={len(in_rapt_rows):3d} (h={with_h:3d}, zero={zero_r:2d}, multi={multi_n:2d}) | "
            f"buf300={len(buf_only_rows):3d} | SPI={spi_cnt:3d} | NAIP={tif_mb:.1f}MB | LiDAR={proj or 'NONE'}",
            flush=True,
        )

    if not args.only and summary_rows:
        out_sum = OUT_ROOT / "all_34_summary.csv"
        with open(out_sum, "w", newline="") as fp:
            w = csv.DictWriter(fp, fieldnames=list(summary_rows[0].keys()))
            w.writeheader()
            w.writerows(summary_rows)
        print(f"\nWrote {out_sum} ({len(summary_rows)} institutions)")


if __name__ == "__main__":
    main()
