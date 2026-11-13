#!/usr/bin/env python3
"""
Step 2B: LiDAR + 4-band NAIP NDVI residual scan for missed standing buildings inside RAPT.

Modes:
  Default (candidate scan):
    - Reads cached USGS 3DEP LAZ chunks from tmp_ept/ (0 network calls).
    - Builds a 1 m ground DTM from class == 2 points (Laplace-filled under buildings).
    - Flags 1 m cells inside RAPT with rel_z >= 2.2 m (<= 45 m), outside existing
      {CODE}_reconciled.geojson footprints (+1.5 m buffer), and 2024 NAIP NDVI < 0.20.
    - Morphologically cleans & polygonizes contiguous clusters >= 2,000 sqft.
    - Saves candidate GeoJSON/CSV + visual QA PNGs to all_34/step2b_candidates/ for review.

  --accept-file <json_or_all>:
    - Commits approved candidate IDs (or all candidates if 'all') into
      {CODE}_reconciled.geojson, {CODE}_reconciled.csv, and {CODE}_qa.png.
"""

import argparse
import csv
import json
import math
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=DeprecationWarning)

import laspy
import numpy as np
import rasterio
from PIL import Image, ImageDraw, ImageFilter
from pyproj import Transformer
from rasterio.features import rasterize, shapes
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject
from shapely import contains_xy
from shapely.geometry import Polygon, mapping, shape
from shapely.ops import transform as shp_transform, unary_union

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
import step1_extract_lidar_heights as s1

ROOT = SCRIPTS_DIR.parents[1]
WORK_DIR = ROOT / "notes" / "building_heights_pilot"
RAW = WORK_DIR / "raw"
OUT_ROOT = WORK_DIR / "all_34"
FP_DIR = OUT_ROOT / "footprints"
HT_DIR = OUT_ROOT / "heights"
QA_DIR = OUT_ROOT / "qa_overlays"
CAND_DIR = OUT_ROOT / "step2b_candidates"
NAIP_DIR = ROOT / "sources" / "imagery" / "naip_2024"
EPT_CACHE = WORK_DIR / "tmp_ept"

CAND_DIR.mkdir(parents=True, exist_ok=True)

TO_3857 = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform
TO_4326 = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True).transform
M_TO_FT = 3.28084
SQM_TO_SQFT = 10.7639104


def load_local_laz_points(code: str, proj: str, bounds_3857: tuple[float, float, float, float]):
    pdir = EPT_CACHE / ("CA_NorthernCA_6_B22_PBSP" if code == "PBSP" else proj)
    bx0, by0, bx1, by1 = bounds_3857
    xs, ys, zs, cls = [], [], [], []
    for lp in sorted(pdir.glob("*.laz")):
        with laspy.open(lp) as f:
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
                xs.append(x[m])
                ys.append(y[m])
                zs.append(z[m])
                cls.append(c[m])
    if not xs:
        return np.array([]), np.array([]), np.array([]), np.array([])
    return np.concatenate(xs), np.concatenate(ys), np.concatenate(zs), np.concatenate(cls)


def harmonic_fill_nan(grid: np.ndarray, iters: int = 80) -> np.ndarray:
    """Fill NaN cells smoothly from known ground pixels via iterative neighbor averaging."""
    out = grid.copy()
    valid = ~np.isnan(out)
    if valid.all() or not valid.any():
        return out
    # Seed remaining NaNs quickly by multi-scale block/dilation first so large footprints converge fast
    known = valid.copy()
    for _ in range(iters):
        nan_mask = ~valid
        if not nan_mask.any():
            break
        # 4-neighbor + 4-diagonal average for NaNs (and relax interior filled cells)
        padded = np.pad(out, 1, mode="edge")
        cnt = np.zeros_like(out)
        acc = np.zeros_like(out)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                sub = padded[1 + dy : 1 + dy + out.shape[0], 1 + dx : 1 + dx + out.shape[1]]
                m = ~np.isnan(sub)
                acc[m] += sub[m]
                cnt[m] += 1.0
        upd = (~known) & (cnt > 0)
        out[upd] = acc[upd] / cnt[upd]
        valid = ~np.isnan(out)
    if np.isnan(out).any():
        out[np.isnan(out)] = float(np.nanmedian(grid))
    return out


def morph_clean(mask: np.ndarray) -> np.ndarray:
    """Close small 1m roof gaps/skylights then open to strip 1-2m fences/poles/edges."""
    im = Image.fromarray((mask.astype(np.uint8)) * 255, mode="L")
    # Close 3x3: dilate then erode (bridges 1-2 m interior roof vents/gaps)
    im = im.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    # Open 3x3: erode then dilate (removes 1-2 m narrow fences, light poles, wall edges)
    im = im.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    return np.asarray(im) > 127


def compute_height_rows_from_pts(
    code: str,
    proj: str,
    feats: list[dict],
    px: np.ndarray,
    py: np.ndarray,
    pz: np.ndarray,
    pcls: np.ndarray,
) -> list[dict]:
    if not feats:
        return []
    mean_lat = sum(f["properties"]["centroid_lat"] for f in feats) / len(feats)
    m_to_3857 = 1.0 / math.cos(math.radians(mean_lat))
    ring_15 = 15.0 * m_to_3857
    ring_3 = 3.0 * m_to_3857
    erode_1 = 1.0 * m_to_3857

    rows = []
    for feat in feats:
        p = feat["properties"]
        poly = shp_transform(TO_3857, shape(feat["geometry"]))
        bx0, by0, bx1, by1 = poly.bounds
        bmask = (px >= bx0 - ring_15) & (px <= bx1 + ring_15) & (py >= by0 - ring_15) & (py <= by1 + ring_15)
        lx, ly, lz, lcls = px[bmask], py[bmask], pz[bmask], pcls[bmask]

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
            "usa_structures_build_id": "",
            "occ_cls": "",
            "prim_occ": "",
            "lat": p["centroid_lat"],
            "lon": p["centroid_lon"],
            "footprint_sqft": p["SQFEET"],
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
            "ept_depth": 12,
            "footprint_source": "lidar_naip_patch",
            "height_source": f"usgs_3dep_ept:{proj}",
            "overture_id": "",
            "overture_name": "",
            "overture_class": "",
            "overture_height_ft": "",
            "overture_num_floors": "",
        })
    return rows


def render_candidate_qa(
    code: str,
    inst_name: str,
    tif_path: Path,
    rapt_wgs,
    existing_feats: list[dict],
    cand_feats: list[dict],
    cand_rows: list[dict],
    out_png: Path,
) -> None:
    with rasterio.open(tif_path) as src:
        rgb = np.transpose(src.read([1, 2, 3]), (1, 2, 0))
        transform = src.transform
        h, w = rgb.shape[:2]

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

    draw_poly_outline(rapt_wgs, (255, 235, 0, 255), width=3)
    for f in existing_feats:
        if f["properties"]["in_rapt_boundary"] == "yes":
            draw_poly_outline(shape(f["geometry"]), (0, 220, 100, 180), width=1)

    row_by_id = {r["footprint_id"]: r for r in cand_rows}
    for f in cand_feats:
        p = f["properties"]
        fid = p["footprint_id"]
        r = row_by_id.get(fid, {})
        g = shape(f["geometry"])
        draw_poly_outline(g, (0, 240, 255, 255), width=3)
        cx, cy = to_px(p["centroid_lon"], p["centroid_lat"])
        lbl = f"L{fid.split('-')[-1]} ({r.get('roof_p50_ft','')}ft)"
        draw.text((cx - 20, cy - 6), lbl, fill=(0, 255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0, 255))

    banner = (
        f"{code} Step 2B Candidates ({len(cand_feats)}) - {inst_name}\n"
        f"Yellow=RAPT | Green=existing reconciled | Cyan=Step 2B LiDAR+NAIP candidates (>=2000 sqft, NDVI<0.20)"
    )
    draw.rectangle([(0, 0), (new_w, 34)], fill=(0, 0, 0, 195))
    draw.text((8, 5), banner, fill=(255, 255, 255, 255))
    img.save(out_png)


def scan_prison(code: str, inst_name: str, rapt_wgs, proj: str) -> tuple[list[dict], list[dict], dict]:
    tif_matches = sorted(NAIP_DIR.glob(f"{code}_naip_*.tif"))
    if not tif_matches:
        return [], [], {}
    tif_path = tif_matches[-1]

    rec_gj = FP_DIR / f"{code}_reconciled.geojson"
    existing_feats = json.loads(rec_gj.read_text())["features"]
    rapt_3857 = shp_transform(TO_3857, rapt_wgs)
    mean_lat = rapt_wgs.centroid.y
    m_to_3857 = 1.0 / math.cos(math.radians(mean_lat))

    # Build 1 m EPSG:3857 grid covering RAPT + 20 m padding
    pad_3857 = 20.0 * m_to_3857
    rx0, ry0, rx1, ry1 = rapt_3857.bounds
    gx0 = math.floor(rx0 - pad_3857)
    gy0 = math.floor(ry0 - pad_3857)
    gx1 = math.ceil(rx1 + pad_3857)
    gy1 = math.ceil(ry1 + pad_3857)

    res = 1.0 * m_to_3857
    ncols = int(math.ceil((gx1 - gx0) / res))
    nrows = int(math.ceil((gy1 - gy0) / res))
    grid_transform = from_origin(gx0, gy1, res, res)

    px, py, pz, pcls = load_local_laz_points(code, proj, (gx0, gy0, gx1, gy1))
    if len(px) == 0:
        return [], [], {}

    # Compute pixel coords
    cols = np.floor((px - gx0) / res).astype(np.int32)
    rows = np.floor((gy1 - py) / res).astype(np.int32)
    in_grid = (cols >= 0) & (cols < ncols) & (rows >= 0) & (rows < nrows)
    px, py, pz, pcls = px[in_grid], py[in_grid], pz[in_grid], pcls[in_grid]
    cols, rows = cols[in_grid], rows[in_grid]
    lin_idx = rows * ncols + cols

    # Ground DTM from class == 2 points (fall back to 15th percentile if sparse)
    gmask = pcls == 2
    dtm = np.full(nrows * ncols, np.nan, dtype=np.float64)
    if gmask.sum() >= 50:
        g_idx = lin_idx[gmask]
        g_z = pz[gmask]
        order = np.argsort(g_idx)
        s_idx = g_idx[order]
        s_z = g_z[order]
        uniq, starts, counts = np.unique(s_idx, return_index=True, return_counts=True)
        # Fast median/min-ish per cell: for 1m cells, mean or median of class 2 is nearly identical
        for u, st, cnt in zip(uniq, starts, counts):
            dtm[u] = float(np.median(s_z[st : st + cnt]))
    dtm_2d = harmonic_fill_nan(dtm.reshape(nrows, ncols), iters=85)

    # Surface height per 1 m cell (75th percentile of points in cell to capture roofs cleanly)
    dsm = np.full(nrows * ncols, np.nan, dtype=np.float64)
    order = np.argsort(lin_idx)
    s_idx = lin_idx[order]
    s_z = pz[order]
    uniq, starts, counts = np.unique(s_idx, return_index=True, return_counts=True)
    for u, st, cnt in zip(uniq, starts, counts):
        if cnt == 1:
            dsm[u] = float(s_z[st])
        else:
            dsm[u] = float(np.percentile(s_z[st : st + cnt], 75))
    dsm_2d = dsm.reshape(nrows, ncols)
    rel_z = dsm_2d - dtm_2d

    # Mask: inside RAPT, outside existing footprints (+1.5 m buffer)
    rapt_mask = rasterize([(rapt_3857, 1)], out_shape=(nrows, ncols), transform=grid_transform, fill=0, dtype=np.uint8) > 0
    buf_3857 = 1.5 * m_to_3857
    existing_geoms_3857 = []
    for f in existing_feats:
        if f["properties"]["in_rapt_boundary"] == "yes":
            g = shp_transform(TO_3857, shape(f["geometry"]))
            if not g.is_valid:
                g = g.buffer(0)
            existing_geoms_3857.append(g.buffer(buf_3857))
    if existing_geoms_3857:
        existing_mask = rasterize(
            [(g, 1) for g in existing_geoms_3857],
            out_shape=(nrows, ncols),
            transform=grid_transform,
            fill=0,
            all_touched=True,
            dtype=np.uint8,
        ) > 0
    else:
        existing_mask = np.zeros((nrows, ncols), dtype=bool)

    # Reproject 2024 NAIP Red (band 1) & NIR (band 4) onto 1 m EPSG:3857 grid
    naip_r = np.zeros((nrows, ncols), dtype=np.float32)
    naip_g = np.zeros((nrows, ncols), dtype=np.float32)
    naip_b = np.zeros((nrows, ncols), dtype=np.float32)
    naip_nir = np.zeros((nrows, ncols), dtype=np.float32)
    with rasterio.open(tif_path) as src:
        for b_idx, dst in ((1, naip_r), (2, naip_g), (3, naip_b), (4, naip_nir)):
            reproject(
                source=rasterio.band(src, b_idx),
                destination=dst,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=grid_transform,
                dst_crs="EPSG:3857",
                resampling=Resampling.bilinear,
            )
    ndvi = (naip_nir - naip_r) / (naip_nir + naip_r + 1e-5)

    raw_cand = (
        rapt_mask
        & (~existing_mask)
        & (~np.isnan(rel_z))
        & (rel_z >= 2.2)
        & (rel_z <= 45.0)
        & (ndvi < 0.20)
    )
    cleaned = morph_clean(raw_cand)

    # Polygonize contiguous components >= 2,000 sqft (185.806 m^2)
    min_area_3857 = (2000.0 / SQM_TO_SQFT) * (m_to_3857 ** 2)
    cand_polys_3857 = []
    for geom_dict, val in shapes(cleaned.astype(np.uint8), mask=cleaned, transform=grid_transform, connectivity=4):
        if val != 1:
            continue
        poly = shape(geom_dict)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.area < min_area_3857:
            continue
        # Fill interior holes < 50 m^2 and simplify 0.6 m so footprints aren't jagged 1m staircases
        if isinstance(poly, Polygon) and poly.interiors:
            keep_holes = [ring for ring in poly.interiors if Polygon(ring).area >= 50.0 * (m_to_3857 ** 2)]
            poly = Polygon(poly.exterior, keep_holes)
        poly = poly.simplify(0.6 * m_to_3857, preserve_topology=True)
        # Re-check against existing footprints and clip strictly to RAPT
        poly = poly.intersection(rapt_3857)
        if poly.is_empty or poly.area < min_area_3857:
            continue
        cand_polys_3857.append(poly)

    cand_feats = []
    for idx, poly3 in enumerate(
        sorted(cand_polys_3857, key=lambda g: (g.centroid.y, g.centroid.x)),
        1,
    ):
        poly_wgs = shp_transform(TO_4326, poly3)
        c_wgs = poly_wgs.centroid
        area_sqft = round(poly3.area * (math.cos(math.radians(c_wgs.y)) ** 2) * SQM_TO_SQFT, 1)

        # Sample NAIP stats inside candidate for triage hints (brightness & NDVI)
        cmask = rasterize([(poly3, 1)], out_shape=(nrows, ncols), transform=grid_transform, fill=0, dtype=np.uint8) > 0
        mean_ndvi = round(float(np.mean(ndvi[cmask])), 3) if cmask.any() else None
        mean_r = round(float(np.mean(naip_r[cmask])), 1) if cmask.any() else None
        mean_g = round(float(np.mean(naip_g[cmask])), 1) if cmask.any() else None
        mean_b = round(float(np.mean(naip_b[cmask])), 1) if cmask.any() else None
        blue_excess = round((mean_b - mean_r), 1) if (mean_b is not None and mean_r is not None) else None

        cand_feats.append({
            "type": "Feature",
            "geometry": mapping(poly_wgs),
            "properties": {
                "footprint_id": f"{code}-lid-{idx:03d}",
                "in_rapt_boundary": "yes",
                "other_rapt_code": "",
                "dist_to_rapt_m": 0.0,
                "BUILD_ID": "",
                "OCC_CLS": "",
                "PRIM_OCC": "",
                "SQFEET": area_sqft,
                "centroid_lon": round(c_wgs.x, 7),
                "centroid_lat": round(c_wgs.y, 7),
                "footprint_source": "lidar_naip_patch",
                "cand_mean_ndvi": mean_ndvi,
                "cand_mean_rgb": f"{mean_r}/{mean_g}/{mean_b}",
                "cand_blue_minus_red": blue_excess,
            },
        })

    cand_rows = compute_height_rows_from_pts(code, proj, cand_feats, px, py, pz, pcls)
    # Keep only valid standing candidates (roof_pts >= 5 and roof_p50_ft >= 6.5)
    valid_feats, valid_rows = [], []
    for cf, cr in zip(cand_feats, cand_rows):
        if cr["roof_p50_ft"] != "" and float(cr["roof_p50_ft"]) >= 6.5:
            valid_feats.append(cf)
            valid_rows.append(cr)

    # Renumber sequentially
    for idx, (cf, cr) in enumerate(zip(valid_feats, valid_rows), 1):
        new_id = f"{code}-lid-{idx:03d}"
        cf["properties"]["footprint_id"] = new_id
        cr["footprint_id"] = new_id

    if valid_feats:
        render_candidate_qa(
            code,
            inst_name,
            tif_path,
            rapt_wgs,
            existing_feats,
            valid_feats,
            valid_rows,
            CAND_DIR / f"{code}_candidates_qa.png",
        )
        (CAND_DIR / f"{code}_candidates.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": valid_feats})
        )

    meta = {
        "cdcr_code": code,
        "lidar_project": proj,
        "pts_loaded": int(len(px)),
        "ground_pts_cls2": int(gmask.sum()),
        "candidates": len(valid_feats),
        "total_cand_sqft": round(sum(float(r["footprint_sqft"]) for r in valid_rows), 1),
    }
    return valid_feats, valid_rows, meta


def commit_candidates(
    accepted_by_code: dict[str, list[str]] | str,
    rapt_by_code: dict,
    inst_by_code: dict,
    sum_by_code: dict,
):
    """Append approved candidate footprints & height rows to {CODE}_reconciled.* and re-render QA PNGs."""
    for c_gj in sorted(CAND_DIR.glob("*_candidates.geojson")):
        code = c_gj.stem.split("_")[0]
        c_feats = json.loads(c_gj.read_text())["features"]
        if isinstance(accepted_by_code, dict):
            allow = set(accepted_by_code.get(code, []))
            c_feats = [f for f in c_feats if f["properties"]["footprint_id"] in allow]
        if not c_feats:
            continue

        # Recompute height rows cleanly from local LAZ so rows match reconciled CSV schema
        proj = sum_by_code[code]["lidar_project"]
        rapt_wgs = rapt_by_code[code]
        rapt_3857 = shp_transform(TO_3857, rapt_wgs)
        mean_lat = rapt_wgs.centroid.y
        pad_3857 = 25.0 / math.cos(math.radians(mean_lat))
        bx0, by0, bx1, by1 = rapt_3857.bounds
        px, py, pz, pcls = load_local_laz_points(code, proj, (bx0 - pad_3857, by0 - pad_3857, bx1 + pad_3857, by1 + pad_3857))

        # Renumber sequentially in case some candidates were rejected
        for i, f in enumerate(c_feats, 1):
            f["properties"]["footprint_id"] = f"{code}-lid-{i:03d}"
        c_rows = compute_height_rows_from_pts(code, proj, c_feats, px, py, pz, pcls)

        rec_gj = FP_DIR / f"{code}_reconciled.geojson"
        rec_csv = HT_DIR / f"{code}_reconciled.csv"
        existing_feats = [
            f for f in json.loads(rec_gj.read_text())["features"]
            if f["properties"].get("footprint_source") != "lidar_naip_patch"
        ]
        existing_rows = [
            r for r in csv.DictReader(open(rec_csv))
            if r.get("footprint_source") != "lidar_naip_patch"
        ]

        # Strip candidate-only diagnostic keys before writing final geojson
        clean_c_feats = []
        for f in c_feats:
            f2 = dict(f)
            f2["properties"] = {k: v for k, v in f["properties"].items() if not k.startswith("cand_")}
            clean_c_feats.append(f2)

        all_feats = existing_feats + clean_c_feats
        all_rows = existing_rows + c_rows
        rec_gj.write_text(json.dumps({"type": "FeatureCollection", "features": all_feats}))
        with open(rec_csv, "w", newline="") as fp:
            w = csv.DictWriter(fp, fieldnames=list(existing_rows[0].keys()))
            w.writeheader()
            w.writerows(all_rows)

        # Re-render QA overlay
        tif_matches = sorted(NAIP_DIR.glob(f"{code}_naip_*.tif"))
        if tif_matches:
            other_rapt = {k: v for k, v in rapt_by_code.items() if k != code}
            buf_wgs = shp_transform(TO_4326, rapt_3857.buffer(300.0 / math.cos(math.radians(mean_lat))))
            sr = sum_by_code.get(code, {})
            s1.render_qa_overlay(
                code,
                inst_by_code[code]["institution_name"],
                tif_matches[-1],
                rapt_wgs,
                buf_wgs,
                other_rapt,
                all_feats,
                all_rows,
                int(sr.get("spi_structures") or 0),
                sr.get("naip_date") or "2024",
                proj,
                force=True,
            )
        print(f"[{code:4s}] Committed {len(c_feats)} lidar_naip_patch footprints -> total RAPT={sum(1 for r in all_rows if r['in_rapt_boundary']=='yes')}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", help="Only process specified CDCR codes")
    parser.add_argument("--commit", help="JSON path mapping code -> [accepted_ids], or 'all'")
    args = parser.parse_args()

    rapt_raw = json.loads((RAW / "Prison_Boundaries_RAPT.geojson").read_text())["features"]
    rapt_by_fid = {str(f["properties"]["FACILITYID"]).strip(): shape(f["geometry"]) for f in rapt_raw if f["properties"].get("FACILITYID")}
    insts = list(csv.DictReader(open(ROOT / "crosswalk" / "institutions.csv")))
    inst_by_code = {r["cdcr_code"]: r for r in insts}
    rapt_by_code = {r["cdcr_code"]: rapt_by_fid[r["fema_facilityid"].strip()] for r in insts}
    sum_by_code = {r["cdcr_code"]: r for r in csv.DictReader(open(OUT_ROOT / "all_34_summary.csv"))}

    if args.commit:
        if args.commit == "all":
            commit_candidates("all", rapt_by_code, inst_by_code, sum_by_code)
        else:
            acc = json.loads(Path(args.commit).read_text())
            commit_candidates(acc, rapt_by_code, inst_by_code, sum_by_code)
        return

    all_cand_rows = []
    summary_rows = []
    for inst in insts:
        code = inst["cdcr_code"]
        if args.only and code not in args.only:
            continue
        proj = sum_by_code[code]["lidar_project"]
        v_feats, v_rows, meta = scan_prison(code, inst["institution_name"], rapt_by_code[code], proj)
        if v_rows:
            for cf, cr in zip(v_feats, v_rows):
                p = cf["properties"]
                all_cand_rows.append({
                    "cdcr_code": code,
                    "footprint_id": cr["footprint_id"],
                    "footprint_sqft": cr["footprint_sqft"],
                    "roof_p25_ft": cr["roof_p25_ft"],
                    "roof_p50_ft": cr["roof_p50_ft"],
                    "roof_p75_ft": cr["roof_p75_ft"],
                    "roof_p90_ft": cr["roof_p90_ft"],
                    "roof_pts": cr["roof_pts"],
                    "mean_ndvi": p["cand_mean_ndvi"],
                    "mean_rgb": p["cand_mean_rgb"],
                    "blue_minus_red": p["cand_blue_minus_red"],
                    "lat": cr["lat"],
                    "lon": cr["lon"],
                })
        summary_rows.append(meta)
        print(
            f"[{code:4s}] pts={meta.get('pts_loaded',0):8d} | cls2={meta.get('ground_pts_cls2',0):7d} | cands={meta.get('candidates',0):2d} ({meta.get('total_cand_sqft',0):8.0f} sqft)",
            flush=True,
        )

    if not args.only:
        if all_cand_rows:
            with open(CAND_DIR / "candidates_detail.csv", "w", newline="") as fp:
                w = csv.DictWriter(fp, fieldnames=list(all_cand_rows[0].keys()))
                w.writeheader()
                w.writerows(all_cand_rows)
        if summary_rows:
            with open(CAND_DIR / "candidates_summary.csv", "w", newline="") as fp:
                w = csv.DictWriter(fp, fieldnames=list(summary_rows[0].keys()))
                w.writeheader()
                w.writerows(summary_rows)
        print(f"\nTotal Step 2B candidates across 34 prisons: {len(all_cand_rows)}")


if __name__ == "__main__":
    main()
