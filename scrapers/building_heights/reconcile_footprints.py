#!/usr/bin/env python3
"""
Footprint reconciliation and zero-roof triage across all 34 CDCR institutions:
1. Overture Maps reconciliation: match existing USA Structures polygons against Overture
   building IDs/metadata and patch missed standing buildings inside RAPT verified by LiDAR.
2. LiDAR + 2024 NAIP residual scanner: detect remaining unmapped non-vegetation structures
   (>= 2,000 sqft, rel_z >= 2.2 m, NDVI < 0.20) for visual review & commit.
3. Zero-roof triage: inspect zero-roof in-RAPT polygons against NAIP RGB/NIR signatures,
   LiDAR-void indicators, manual visual overrides (triage_overrides.json), and MPAR/condition
   roof QA context, writing {CODE}_triaged.csv.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import warnings
from pathlib import Path
from typing import Any

warnings.filterwarnings("ignore", category=DeprecationWarning)

import numpy as np
import rasterio
from PIL import Image, ImageDraw, ImageFilter
from rasterio.features import rasterize, shapes
from rasterio.warp import Resampling, reproject
from rasterio.windows import from_bounds
from shapely.geometry import Polygon, mapping, shape
from shapely.ops import transform as shp_transform
from shapely.wkb import loads as wkb_loads

from common import (
    ALL34_DIR,
    CAND_DIR,
    CLOSED_CODES,
    DATA_BUILDINGS,
    EPT_CACHE,
    FP_DIR,
    HT_DIR,
    M_TO_FT,
    NAIP_DIR,
    OVT_DIR,
    RAW_DIR,
    SQM_TO_SQFT,
    TO_3857,
    TO_4326,
    TRIAGE_DIR,
    TRIAGE_OVERRIDES_PATH,
    compute_footprint_height_rows,
    draw_wgs_outline,
    ensure_work_dirs,
    load_ept_points_for_features,
    load_institutions_and_rapt,
    load_local_laz_points,
    make_wgs_to_px,
    open_naip_rgb_canvas,
    select_ept_project,
)
from fetch_sources import render_qa_overlay


# ---------------------------------------------------------------------------
# Stage 1: Overture Maps reconciliation
# ---------------------------------------------------------------------------

def fetch_overture_for_prison(code: str, buf_wgs: Any, force: bool = False) -> list[dict[str, Any]]:
    """Fetch and cache Overture Maps building footprints within the 300 m buffer."""
    out_gj = OVT_DIR / f"{code}_overture.geojson"
    if out_gj.exists() and not force:
        return json.loads(out_gj.read_text())["features"]

    import certifi
    os.environ["SSL_CERT_FILE"] = certifi.where()
    from overturemaps import core

    tbl = core.record_batch_reader("building", bbox=buf_wgs.bounds).read_all()
    d = tbl.to_pydict()
    feats: list[dict[str, Any]] = []
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
        area_sqft = shp_transform(TO_3857, geom).area * (math.cos(math.radians(c.y)) ** 2) * SQM_TO_SQFT
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


def _no_ept_patch_row(code: str, props: dict[str, Any]) -> dict[str, Any]:
    return {
        "cdcr_code": code,
        "footprint_id": props["footprint_id"],
        "in_rapt_boundary": "yes",
        "other_rapt_code": "",
        "dist_to_rapt_m": 0.0,
        "usa_structures_build_id": "",
        "occ_cls": "",
        "prim_occ": "",
        "lat": props["centroid_lat"],
        "lon": props["centroid_lon"],
        "footprint_sqft": props["area_sqft"],
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
    }


def reconcile_overture(only: list[str] | None = None) -> None:
    """Link Overture metadata onto USA Structures rows and patch missed LiDAR-verified buildings."""
    ensure_work_dirs()
    insts, rapt_by_code = load_institutions_and_rapt()
    ept_raw = json.loads((RAW_DIR / "usgs_lidar_resources.geojson").read_text())["features"]
    ept_feats = [(f["properties"]["name"], f["properties"].get("count", 0), shape(f["geometry"])) for f in ept_raw]
    sum_by_code = (
        {r["cdcr_code"]: r for r in csv.DictReader(open(ALL34_DIR / "all_34_summary.csv"))}
        if (ALL34_DIR / "all_34_summary.csv").exists()
        else {}
    )

    total_patched = 0
    for inst in insts:
        code = inst["cdcr_code"]
        if only and code not in only:
            continue
        rapt_wgs = rapt_by_code[code]
        other_rapt = {k: v for k, v in rapt_by_code.items() if k != code}
        buf_wgs = shp_transform(
            TO_4326,
            shp_transform(TO_3857, rapt_wgs).buffer(300.0 / math.cos(math.radians(rapt_wgs.centroid.y))),
        )

        ovt_feats = fetch_overture_for_prison(code, buf_wgs)
        usa_feats = json.loads((FP_DIR / f"{code}_footprints.geojson").read_text())["features"]
        usa_polys = [(g if (g := shape(f["geometry"])).is_valid else g.buffer(0)) for f in usa_feats]
        with open(HT_DIR / f"{code}_heights.csv") as f:
            h_rows = list(csv.DictReader(f))

        ovt_matches_by_usa: dict[str, list[dict[str, Any]]] = {f["properties"]["footprint_id"]: [] for f in usa_feats}
        unmatched_ovt_in_rapt: list[dict[str, Any]] = []
        for of in ovt_feats:
            og = shape(of["geometry"])
            if not og.is_valid:
                og = og.buffer(0)
            best_frac = 0.0
            for uf, up in zip(usa_feats, usa_polys):
                if not og.intersects(up):
                    continue
                min_a = min(og.area, up.area)
                frac = og.intersection(up).area / min_a if min_a > 0 else 0.0
                if frac >= 0.25:
                    ovt_matches_by_usa[uf["properties"]["footprint_id"]].append(of)
                best_frac = max(best_frac, frac)
            if rapt_wgs.contains(og.centroid) and best_frac < 0.20 and of["properties"]["area_sqft"] >= 400.0:
                unmatched_ovt_in_rapt.append(of)

        proj, _, _ = select_ept_project(rapt_wgs, ept_feats)
        if not proj and code == "PBSP" and (EPT_CACHE / "CA_NorthernCA_6_B22_PBSP").exists():
            proj = "CA_NorthernCA_6_B22"

        patched_feats, patched_rows = [], []
        if unmatched_ovt_in_rapt:
            cand_feats = []
            for idx, of in enumerate(
                sorted(unmatched_ovt_in_rapt, key=lambda x: (x["properties"]["centroid_lat"], x["properties"]["centroid_lon"])),
                1,
            ):
                op = of["properties"]
                cand_feats.append({
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
                })

            if proj:
                px, py, pz, pcls, used_depth = load_ept_points_for_features(code, proj, cand_feats, allow_remote=True)
                cand_rows = compute_footprint_height_rows(
                    code, proj, cand_feats, px, py, pz, pcls, used_depth=used_depth, footprint_source="overture_patch"
                )
                keep_idx = 0
                for nf, cr in zip(cand_feats, cand_rows):
                    if cr["roof_p50_ft"] != "" and float(cr["roof_p50_ft"]) >= 6.5:
                        keep_idx += 1
                        new_id = f"{code}-ovt-{keep_idx:03d}"
                        nf["properties"]["footprint_id"] = new_id
                        cr["footprint_id"] = new_id
                        cr["height_source"] = f"usgs_3dep_ept:{proj}"
                        patched_feats.append(nf)
                        patched_rows.append(cr)
            else:
                for nf in cand_feats:
                    patched_feats.append(nf)
                    patched_rows.append(_no_ept_patch_row(code, nf["properties"]))

        enriched_rows: list[dict[str, Any]] = []
        for r in h_rows:
            matches = ovt_matches_by_usa.get(r["footprint_id"], [])
            ovt_hs = [m["properties"]["overture_height_ft"] for m in matches if m["properties"]["overture_height_ft"] is not None]
            ovt_floors = [m["properties"]["overture_num_floors"] for m in matches if m["properties"]["overture_num_floors"] is not None]
            r2 = dict(r)
            r2.setdefault("footprint_source", "usa_structures")
            r2["height_source"] = (
                f"usgs_3dep_ept:{r2['lidar_project']}"
                if r2["roof_p50_ft"] != "" and r2.get("lidar_project")
                else "none"
            )
            r2["overture_id"] = ";".join(m["properties"]["overture_id"] for m in matches)
            r2["overture_name"] = ";".join(sorted({m["properties"]["overture_name"] for m in matches if m["properties"]["overture_name"]}))
            r2["overture_class"] = ";".join(sorted({m["properties"]["overture_class"] for m in matches if m["properties"]["overture_class"]}))
            r2["overture_height_ft"] = max(ovt_hs) if ovt_hs else ""
            r2["overture_num_floors"] = max(ovt_floors) if ovt_floors else ""
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

        combined_feats = usa_feats + patched_feats
        (FP_DIR / f"{code}_reconciled.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": combined_feats})
        )
        with open(HT_DIR / f"{code}_reconciled.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(enriched_rows[0].keys()))
            w.writeheader()
            w.writerows(enriched_rows)

        if patched_feats or code == "PBSP":
            tif_matches = sorted(NAIP_DIR.glob(f"{code}_naip_*.tif"))
            if tif_matches:
                sr = sum_by_code.get(code, {})
                render_qa_overlay(
                    code, inst["institution_name"], tif_matches[-1], rapt_wgs, buf_wgs, other_rapt,
                    combined_feats, enriched_rows, int(sr.get("spi_structures") or 0),
                    sr.get("naip_date") or "2024", proj or "NONE", force=True,
                )

        total_patched += len(patched_feats)
        pbsp_h = sum(1 for r in enriched_rows if r["in_rapt_boundary"] == "yes" and r["roof_p50_ft"] != "")
        print(
            f"[{code:4s}] Overture={len(ovt_feats):3d} | RAPT_unmatched={len(unmatched_ovt_in_rapt):2d} "
            f"-> patched={len(patched_feats):2d} | RAPT_with_h={pbsp_h}",
            flush=True,
        )
    print(f"\nDone Overture reconciliation. Total RAPT footprints patched: {total_patched}")


# ---------------------------------------------------------------------------
# Stage 2: LiDAR + NAIP residual structure detection
# ---------------------------------------------------------------------------

def harmonic_fill_nan(grid: np.ndarray, iters: int = 85) -> np.ndarray:
    """Fill NaN cells smoothly from known ground pixels via iterative neighbor averaging."""
    out = grid.copy()
    valid = ~np.isnan(out)
    if valid.all() or not valid.any():
        return out
    known = valid.copy()
    for _ in range(iters):
        if valid.all():
            break
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
    """Close 1 m roof gaps then open to strip narrow fences, poles, and walls."""
    im = Image.fromarray((mask.astype(np.uint8)) * 255, mode="L")
    im = im.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    im = im.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    return np.asarray(im) > 127


def render_candidate_qa(
    code: str,
    inst_name: str,
    tif_path: Path,
    rapt_wgs: Any,
    existing_feats: list[dict[str, Any]],
    cand_feats: list[dict[str, Any]],
    cand_rows: list[dict[str, Any]],
    out_png: Path,
) -> None:
    """Render LiDAR+NAIP residual candidate overlay PNG for manual review."""
    img, transform, scale = open_naip_rgb_canvas(tif_path, max_dim=1800)
    new_w, _ = img.size
    draw = ImageDraw.Draw(img, "RGBA")
    to_px = make_wgs_to_px(transform, scale)

    draw_wgs_outline(draw, rapt_wgs, to_px, (255, 235, 0, 255), width=3)
    for feat in existing_feats:
        if feat["properties"]["in_rapt_boundary"] == "yes":
            draw_wgs_outline(draw, shape(feat["geometry"]), to_px, (0, 220, 100, 180), width=1)

    row_by_id = {r["footprint_id"]: r for r in cand_rows}
    for feat in cand_feats:
        p = feat["properties"]
        fid = p["footprint_id"]
        r = row_by_id.get(fid, {})
        draw_wgs_outline(draw, shape(feat["geometry"]), to_px, (0, 240, 255, 255), width=3)
        cx, cy = to_px(p["centroid_lon"], p["centroid_lat"])
        lbl = f"L{fid.split('-')[-1]} ({r.get('roof_p50_ft', '')}ft)"
        draw.text((cx - 20, cy - 6), lbl, fill=(0, 255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0, 255))

    banner = (
        f"{code} LiDAR+NAIP Residual Candidates ({len(cand_feats)}) - {inst_name}\n"
        f"Yellow=RAPT | Green=existing reconciled | Cyan=residual candidates (>=2000 sqft, NDVI<0.20)"
    )
    draw.rectangle([(0, 0), (new_w, 34)], fill=(0, 0, 0, 195))
    draw.text((8, 5), banner, fill=(255, 255, 255, 255))
    img.save(out_png)


def _cell_stat_grid(lin_idx: np.ndarray, values: np.ndarray, n_cells: int, pct: float) -> np.ndarray:
    grid = np.full(n_cells, np.nan, dtype=np.float64)
    if len(lin_idx) == 0:
        return grid
    order = np.argsort(lin_idx)
    s_idx = lin_idx[order]
    s_val = values[order]
    uniq, starts, counts = np.unique(s_idx, return_index=True, return_counts=True)
    for u, st, cnt in zip(uniq, starts, counts):
        seg = s_val[st : st + cnt]
        grid[u] = float(seg[0]) if cnt == 1 else float(np.percentile(seg, pct))
    return grid


def scan_prison_residuals(
    code: str, inst_name: str, rapt_wgs: Any, proj: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Scan local cached LAZ + 2024 NAIP for unmapped elevated non-vegetation structures."""
    tif_matches = sorted(NAIP_DIR.glob(f"{code}_naip_*.tif"))
    if not tif_matches:
        return [], [], {}
    tif_path = tif_matches[-1]

    existing_feats = json.loads((FP_DIR / f"{code}_reconciled.geojson").read_text())["features"]
    rapt_3857 = shp_transform(TO_3857, rapt_wgs)
    m_to_3857 = 1.0 / math.cos(math.radians(rapt_wgs.centroid.y))
    pad_3857 = 20.0 * m_to_3857

    rx0, ry0, rx1, ry1 = rapt_3857.bounds
    gx0, gy0 = math.floor(rx0 - pad_3857), math.floor(ry0 - pad_3857)
    gx1, gy1 = math.ceil(rx1 + pad_3857), math.ceil(ry1 + pad_3857)
    res = 1.0 * m_to_3857
    ncols = int(math.ceil((gx1 - gx0) / res))
    nrows = int(math.ceil((gy1 - gy0) / res))
    grid_transform = rasterio.transform.from_origin(gx0, gy1, res, res)

    px, py, pz, pcls = load_local_laz_points(code, proj, (gx0, gy0, gx1, gy1))
    if len(px) == 0:
        return [], [], {}

    cols = np.floor((px - gx0) / res).astype(np.int32)
    rows = np.floor((gy1 - py) / res).astype(np.int32)
    in_grid = (cols >= 0) & (cols < ncols) & (rows >= 0) & (rows < nrows)
    px, py, pz, pcls = px[in_grid], py[in_grid], pz[in_grid], pcls[in_grid]
    lin_idx = rows[in_grid] * ncols + cols[in_grid]

    gmask = pcls == 2
    dtm = (
        _cell_stat_grid(lin_idx[gmask], pz[gmask], nrows * ncols, 50.0)
        if gmask.sum() >= 50
        else np.full(nrows * ncols, np.nan, dtype=np.float64)
    )
    dtm_2d = harmonic_fill_nan(dtm.reshape(nrows, ncols), iters=85)
    dsm_2d = _cell_stat_grid(lin_idx, pz, nrows * ncols, 75.0).reshape(nrows, ncols)
    rel_z = dsm_2d - dtm_2d

    rapt_mask = rasterize([(rapt_3857, 1)], out_shape=(nrows, ncols), transform=grid_transform, fill=0, dtype=np.uint8) > 0
    buf_3857 = 1.5 * m_to_3857
    existing_geoms_3857 = [
        (g if (g := shp_transform(TO_3857, shape(f["geometry"]))).is_valid else g.buffer(0)).buffer(buf_3857)
        for f in existing_feats
        if f["properties"]["in_rapt_boundary"] == "yes"
    ]
    existing_mask = (
        rasterize([(g, 1) for g in existing_geoms_3857], out_shape=(nrows, ncols), transform=grid_transform, fill=0, all_touched=True, dtype=np.uint8) > 0
        if existing_geoms_3857
        else np.zeros((nrows, ncols), dtype=bool)
    )

    naip_bands = [np.zeros((nrows, ncols), dtype=np.float32) for _ in range(4)]
    with rasterio.open(tif_path) as src:
        for b_idx, dst in enumerate(naip_bands, 1):
            reproject(
                source=rasterio.band(src, b_idx),
                destination=dst,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=grid_transform,
                dst_crs="EPSG:3857",
                resampling=Resampling.bilinear,
            )
    naip_r, naip_g, naip_b, naip_nir = naip_bands
    ndvi = (naip_nir - naip_r) / (naip_nir + naip_r + 1e-5)

    raw_cand = rapt_mask & (~existing_mask) & (~np.isnan(rel_z)) & (rel_z >= 2.2) & (rel_z <= 45.0) & (ndvi < 0.20)
    cleaned = morph_clean(raw_cand)

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
        if isinstance(poly, Polygon) and poly.interiors:
            keep_holes = [ring for ring in poly.interiors if Polygon(ring).area >= 50.0 * (m_to_3857 ** 2)]
            poly = Polygon(poly.exterior, keep_holes)
        poly = poly.simplify(0.6 * m_to_3857, preserve_topology=True).intersection(rapt_3857)
        if not poly.is_empty and poly.area >= min_area_3857:
            cand_polys_3857.append(poly)

    cand_feats = []
    for idx, poly3 in enumerate(sorted(cand_polys_3857, key=lambda g: (g.centroid.y, g.centroid.x)), 1):
        poly_wgs = shp_transform(TO_4326, poly3)
        c_wgs = poly_wgs.centroid
        area_sqft = round(poly3.area * (math.cos(math.radians(c_wgs.y)) ** 2) * SQM_TO_SQFT, 1)
        cmask = rasterize([(poly3, 1)], out_shape=(nrows, ncols), transform=grid_transform, fill=0, dtype=np.uint8) > 0
        mean_ndvi = round(float(np.mean(ndvi[cmask])), 3) if cmask.any() else None
        mean_r = round(float(np.mean(naip_r[cmask])), 1) if cmask.any() else None
        mean_g = round(float(np.mean(naip_g[cmask])), 1) if cmask.any() else None
        mean_b = round(float(np.mean(naip_b[cmask])), 1) if cmask.any() else None
        blue_excess = round(mean_b - mean_r, 1) if (mean_b is not None and mean_r is not None) else None
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

    cand_rows = compute_footprint_height_rows(
        code, proj, cand_feats, px, py, pz, pcls, used_depth=12, footprint_source="lidar_naip_patch"
    )
    valid_feats, valid_rows = [], []
    for cf, cr in zip(cand_feats, cand_rows):
        if cr["roof_p50_ft"] != "" and float(cr["roof_p50_ft"]) >= 6.5:
            valid_feats.append(cf)
            valid_rows.append(cr)

    for idx, (cf, cr) in enumerate(zip(valid_feats, valid_rows), 1):
        new_id = f"{code}-lid-{idx:03d}"
        cf["properties"]["footprint_id"] = new_id
        cr["footprint_id"] = new_id

    if valid_feats:
        render_candidate_qa(code, inst_name, tif_path, rapt_wgs, existing_feats, valid_feats, valid_rows, CAND_DIR / f"{code}_candidates_qa.png")
        (CAND_DIR / f"{code}_candidates.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": valid_feats}))

    meta = {
        "cdcr_code": code,
        "lidar_project": proj,
        "pts_loaded": int(len(px)),
        "ground_pts_cls2": int(gmask.sum()),
        "candidates": len(valid_feats),
        "total_cand_sqft": round(sum(float(r["footprint_sqft"]) for r in valid_rows), 1),
    }
    return valid_feats, valid_rows, meta


def scan_lidar_residuals(only: list[str] | None = None) -> None:
    """Scan local cached LAZ + NAIP residuals across institutions."""
    ensure_work_dirs()
    insts, rapt_by_code = load_institutions_and_rapt()
    sum_by_code = {r["cdcr_code"]: r for r in csv.DictReader(open(ALL34_DIR / "all_34_summary.csv"))}

    all_cand_rows, summary_rows = [], []
    for inst in insts:
        code = inst["cdcr_code"]
        if only and code not in only:
            continue
        proj = sum_by_code[code]["lidar_project"]
        v_feats, v_rows, meta = scan_prison_residuals(code, inst["institution_name"], rapt_by_code[code], proj)
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
            f"[{code:4s}] pts={meta.get('pts_loaded', 0):8d} | cls2={meta.get('ground_pts_cls2', 0):7d} "
            f"| cands={meta.get('candidates', 0):2d} ({meta.get('total_cand_sqft', 0):8.0f} sqft)",
            flush=True,
        )

    if not only:
        if all_cand_rows:
            with open(CAND_DIR / "candidates_detail.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(all_cand_rows[0].keys()))
                w.writeheader()
                w.writerows(all_cand_rows)
        if summary_rows:
            with open(CAND_DIR / "candidates_summary.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
                w.writeheader()
                w.writerows(summary_rows)
        print(f"\nTotal LiDAR+NAIP residual candidates: {len(all_cand_rows)}")


def commit_lidar_candidates(accepted_spec: str) -> None:
    """Commit approved LiDAR+NAIP residual footprints into {CODE}_reconciled.* and re-render QA PNGs."""
    ensure_work_dirs()
    insts, rapt_by_code = load_institutions_and_rapt()
    inst_by_code = {r["cdcr_code"]: r for r in insts}
    sum_by_code = {r["cdcr_code"]: r for r in csv.DictReader(open(ALL34_DIR / "all_34_summary.csv"))}
    accepted_by_code: dict[str, list[str]] | str = (
        "all" if accepted_spec == "all" else json.loads(Path(accepted_spec).read_text())
    )

    for c_gj in sorted(CAND_DIR.glob("*_candidates.geojson")):
        code = c_gj.stem.split("_")[0]
        c_feats = json.loads(c_gj.read_text())["features"]
        if isinstance(accepted_by_code, dict):
            allow = set(accepted_by_code.get(code, []))
            c_feats = [f for f in c_feats if f["properties"]["footprint_id"] in allow]
        if not c_feats:
            continue

        proj = sum_by_code[code]["lidar_project"]
        rapt_wgs = rapt_by_code[code]
        rapt_3857 = shp_transform(TO_3857, rapt_wgs)
        pad_3857 = 25.0 / math.cos(math.radians(rapt_wgs.centroid.y))
        bx0, by0, bx1, by1 = rapt_3857.bounds
        px, py, pz, pcls = load_local_laz_points(code, proj, (bx0 - pad_3857, by0 - pad_3857, bx1 + pad_3857, by1 + pad_3857))

        for i, feat in enumerate(c_feats, 1):
            feat["properties"]["footprint_id"] = f"{code}-lid-{i:03d}"
        c_rows = compute_footprint_height_rows(
            code, proj, c_feats, px, py, pz, pcls, used_depth=12, footprint_source="lidar_naip_patch"
        )

        rec_gj = FP_DIR / f"{code}_reconciled.geojson"
        rec_csv = HT_DIR / f"{code}_reconciled.csv"
        existing_feats = [f for f in json.loads(rec_gj.read_text())["features"] if f["properties"].get("footprint_source") != "lidar_naip_patch"]
        existing_rows = [r for r in csv.DictReader(open(rec_csv)) if r.get("footprint_source") != "lidar_naip_patch"]

        clean_c_feats = [{**f, "properties": {k: v for k, v in f["properties"].items() if not k.startswith("cand_")}} for f in c_feats]
        all_feats = existing_feats + clean_c_feats
        all_rows = existing_rows + c_rows
        rec_gj.write_text(json.dumps({"type": "FeatureCollection", "features": all_feats}))
        with open(rec_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(existing_rows[0].keys()))
            w.writeheader()
            w.writerows(all_rows)

        tif_matches = sorted(NAIP_DIR.glob(f"{code}_naip_*.tif"))
        if tif_matches:
            other_rapt = {k: v for k, v in rapt_by_code.items() if k != code}
            buf_wgs = shp_transform(TO_4326, rapt_3857.buffer(300.0 / math.cos(math.radians(rapt_wgs.centroid.y))))
            sr = sum_by_code.get(code, {})
            render_qa_overlay(
                code, inst_by_code[code]["institution_name"], tif_matches[-1], rapt_wgs, buf_wgs, other_rapt,
                all_feats, all_rows, int(sr.get("spi_structures") or 0), sr.get("naip_date") or "2024", proj, force=True,
            )
        print(f"[{code:4s}] Committed {len(c_feats)} lidar_naip_patch footprints -> total RAPT={sum(1 for r in all_rows if r['in_rapt_boundary'] == 'yes')}")


# ---------------------------------------------------------------------------
# Stage 3: Zero-roof triage & facility roof QA cross-check
# ---------------------------------------------------------------------------

def load_facility_roof_qa() -> dict[str, dict[str, Any]]:
    """Aggregate facility-level roof condition and MPAR project context per CDCR institution."""
    with open(ALL34_DIR.parents[1].parent / "crosswalk" / "institutions.csv") as f:
        insts = list(csv.DictReader(f))
    aliases_by_code = {
        r["cdcr_code"]: [r["cdcr_code"]] + [a.strip() for a in (r.get("alias_codes") or "").split(";") if a.strip()]
        for r in insts
    }

    cond_by_inst = {}
    with open(DATA_BUILDINGS / "condition_assessment_2026.csv") as f:
        for r in csv.DictReader(f):
            if r["system"] == "Roofs":
                cond_by_inst[r["institution"]] = r["rating"]

    env_by_inst = {}
    with open(DATA_BUILDINGS / "mpar_envelope_last_completed.csv") as f:
        for r in csv.DictReader(f):
            env_by_inst[r["institution"]] = r

    mpar_roofs_by_inst: dict[str, list[dict[str, str]]] = {}
    with open(DATA_BUILDINGS / "mpar_projects.csv") as f:
        for r in csv.DictReader(f):
            if "roof" in (r["title"] + " " + r["scope"]).lower():
                mpar_roofs_by_inst.setdefault(r["institution"], []).append(r)

    mentions_roof_by_code: dict[str, int] = {}
    with open(DATA_BUILDINGS / "building_mentions.csv") as f:
        for r in csv.DictReader(f):
            if "roof" in (r["quote"] or "").lower():
                mentions_roof_by_code[r["cdcr_code"]] = mentions_roof_by_code.get(r["cdcr_code"], 0) + 1

    sum_by_code = {r["cdcr_code"]: r for r in csv.DictReader(open(ALL34_DIR / "all_34_summary.csv"))}
    qa: dict[str, dict[str, Any]] = {}
    for c, aliases in aliases_by_code.items():
        cond = next((cond_by_inst[a] for a in aliases if a in cond_by_inst), "")
        env = next((env_by_inst[a] for a in aliases if a in env_by_inst), {})
        last_yr = env.get("last_envelope_year", "")
        last_pid = env.get("project_id", "")

        mpar_rows = []
        for a in aliases:
            mpar_rows.extend(mpar_roofs_by_inst.get(a, []))
        active_pids = sorted({r["project_id"] for r in mpar_rows if r["status"] in ("active", "complete") and "roof" in r["title"].lower()})
        lidar_yr = int(sum_by_code[c]["lidar_year"]) if sum_by_code.get(c, {}).get("lidar_year") else None

        post_flag = "no"
        if last_yr and lidar_yr and int(last_yr) >= lidar_yr:
            post_flag = "yes"
        elif active_pids and any(r["status"] == "active" for r in mpar_rows):
            post_flag = "active_mpar_roof"

        qa[c] = {
            "cond_roofs_2026": cond,
            "mpar_last_roof_year": last_yr,
            "mpar_last_roof_pid": last_pid,
            "mpar_roof_projects_2022_2025": ";".join(active_pids),
            "mpar_roof_mention_count": mentions_roof_by_code.get(c, 0),
            "post_lidar_roof_project_flag": post_flag,
        }
    return qa


def sample_naip_stats(src: rasterio.DatasetReader, geom: Any) -> tuple[float, float, float, float, float, float, float]:
    """Compute mean R/G/B/NIR, NDVI, brightness, and blue-minus-red within a polygon."""
    arr = src.read()
    m = rasterize([(geom, 1)], out_shape=(src.height, src.width), transform=src.transform, fill=0, all_touched=True) > 0
    if not m.any():
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
    r = float(np.mean(arr[0][m]))
    g = float(np.mean(arr[1][m]))
    b = float(np.mean(arr[2][m]))
    n = float(np.mean(arr[3][m]))
    ndvi = (n - r) / (n + r + 1e-5)
    bright = (r + g + b) / 3.0
    return round(r, 1), round(g, 1), round(b, 1), round(n, 1), round(ndvi, 3), round(bright, 1), round(b - r, 1)


def render_zero_roof_contact_sheets(zero_items: list[dict[str, Any]]) -> None:
    """Render contact sheets of zero-roof in-RAPT polygons on 2024 NAIP for visual QA."""
    if not zero_items:
        return
    cols, cell_w, cell_h, per_page = 6, 220, 235, 30
    for page_idx in range(0, len(zero_items), per_page):
        batch = zero_items[page_idx : page_idx + per_page]
        nrows = math.ceil(len(batch) / cols)
        sheet = Image.new("RGB", (cols * cell_w, nrows * cell_h), (20, 20, 20))
        draw = ImageDraw.Draw(sheet)

        for i, item in enumerate(batch):
            r_idx, c_idx = divmod(i, cols)
            x0, y0 = c_idx * cell_w, r_idx * cell_h
            geom = item["geom"]
            cx, cy = geom.centroid.x, geom.centroid.y
            minx, miny, maxx, maxy = geom.bounds
            pad = max(0.00035, (maxx - minx) * 0.8, (maxy - miny) * 0.8)
            with rasterio.open(item["tif_path"]) as src:
                win = from_bounds(cx - pad, cy - pad, cx + pad, cy + pad, src.transform)
                arr = src.read([1, 2, 3], window=win, boundless=True, fill_value=0)
                w_tr = src.window_transform(win)
                crop = Image.fromarray(np.transpose(arr, (1, 2, 0)), mode="RGB").resize((210, 195), Image.Resampling.BILINEAR)
                cdraw = ImageDraw.Draw(crop)
                sx, sy = 210.0 / max(1, arr.shape[2]), 195.0 / max(1, arr.shape[1])
                to_px = make_wgs_to_px(w_tr, 1.0)
                draw_wgs_outline(cdraw, geom, lambda lon, lat: (to_px(lon, lat)[0] * sx, to_px(lon, lat)[1] * sy), (255, 60, 60), width=2)
            sheet.paste(crop, (x0 + 5, y0 + 5))
            draw.text((x0 + 6, y0 + 202), f"{item['fid']} ({item['sqft']:.0f}sf)", fill=(255, 255, 255))
            draw.text((x0 + 6, y0 + 216), f"pts={item['pts']} {item['status'][:14]}", fill=(255, 210, 100))

        out_png = TRIAGE_DIR / f"zero_roof_sheet_{page_idx // per_page + 1}.png"
        sheet.save(out_png)
        print(f"Saved {out_png} ({len(batch)} polygons)")


def triage_zero_roof(render_sheets: bool = True) -> None:
    """Classify zero-roof in-RAPT polygons and attach perimeter/roof-QA columns into {CODE}_triaged.csv."""
    ensure_work_dirs()
    overrides = json.loads(TRIAGE_OVERRIDES_PATH.read_text()) if TRIAGE_OVERRIDES_PATH.exists() else {}
    roof_qa = load_facility_roof_qa()
    insts, _ = load_institutions_and_rapt()

    zero_items_for_sheets, triage_summary_rows, zero_detail_rows = [], [], []
    for inst in insts:
        code = inst["cdcr_code"]
        is_closed = "yes" if code in CLOSED_CODES else "no"
        feats = json.loads((FP_DIR / f"{code}_reconciled.geojson").read_text())["features"]
        geom_by_fid = {f["properties"]["footprint_id"]: shape(f["geometry"]) for f in feats}
        with open(HT_DIR / f"{code}_reconciled.csv") as f:
            rows = list(csv.DictReader(f))
        tifs = sorted(NAIP_DIR.glob(f"{code}_naip_*.tif"))
        tif_path = tifs[-1] if tifs else None
        fqa = roof_qa[code]

        triaged_rows = []
        counts = {
            "inside_valid_standing": 0,
            "inside_demolished_or_pad": 0,
            "inside_solar_carport_or_array": 0,
            "inside_new_post_lidar_bldg": 0,
            "buffer_300m_outside": 0,
            "adjacent_prison_rapt": 0,
        }

        with rasterio.open(tif_path) as src:
            for r in rows:
                fid = r["footprint_id"]
                in_rapt = r["in_rapt_boundary"] == "yes"
                perim = "inside_fence_rapt" if in_rapt else ("adjacent_prison_rapt" if r.get("other_rapt_code") else "buffer_300m_outside")
                pts_in = int(r["pts_inside"] or 0)
                sqft = float(r["footprint_sqft"] or 0)
                zero_flag = r["zero_roof_flag"] == "yes"

                triage_status, triage_note = "valid_standing", ""
                if not in_rapt:
                    triage_status = "outside_rapt_unverified" if zero_flag else "valid_standing"
                    counts[perim] += 1
                elif not zero_flag:
                    counts["inside_valid_standing"] += 1
                else:
                    g = geom_by_fid[fid]
                    mr, mg, mb, mn, ndvi, bright, b_r = sample_naip_stats(src, g)
                    if fid in overrides:
                        triage_status = overrides[fid]["triage_status"]
                        triage_note = overrides[fid].get("note", "visual_override")
                    elif pts_in == 0 and sqft >= 4000:
                        triage_status = "valid_standing"
                        triage_note = "lidar_void_standing_confirmed_naip"
                    elif b_r >= 10.0 and bright < 145.0:
                        triage_status = "solar_carport_or_array"
                        triage_note = f"blue_solar_sig(b-r={b_r},br={bright})"
                    else:
                        triage_status = "demolished_or_pad"
                        triage_note = f"ground_only_lidar(pts={pts_in},br={bright},ndvi={ndvi})"

                    counts[f"inside_{triage_status}"] = counts.get(f"inside_{triage_status}", 0) + 1
                    zero_detail_rows.append({
                        "cdcr_code": code,
                        "is_closed_facility": is_closed,
                        "footprint_id": fid,
                        "footprint_sqft": sqft,
                        "pts_inside": pts_in,
                        "ground_pts": r["ground_pts"],
                        "prim_occ": r["prim_occ"],
                        "mean_rgb": f"{mr}/{mg}/{mb}",
                        "brightness": bright,
                        "blue_minus_red": b_r,
                        "mean_ndvi": ndvi,
                        "triage_status": triage_status,
                        "triage_note": triage_note,
                        "lat": r["lat"],
                        "lon": r["lon"],
                    })
                    zero_items_for_sheets.append({
                        "code": code, "fid": fid, "sqft": sqft, "pts": pts_in,
                        "status": triage_status, "geom": g, "tif_path": tif_path,
                    })

                if perim != "inside_fence_rapt":
                    bcat = "buffer_unclassified"
                elif triage_status == "demolished_or_pad":
                    bcat = "demolished_or_pad"
                elif triage_status == "solar_carport_or_array":
                    bcat = "solar_array"
                else:
                    bcat = "standing_unclassified"

                triaged_rows.append({
                    **r,
                    "perimeter_status": perim,
                    "is_closed_facility": is_closed,
                    "triage_status": triage_status,
                    "triage_note": triage_note,
                    "building_category": bcat,
                    "cond_roofs_2026": fqa["cond_roofs_2026"],
                    "mpar_last_roof_year": fqa["mpar_last_roof_year"],
                    "post_lidar_roof_project_flag": fqa["post_lidar_roof_project_flag"],
                })

        with open(HT_DIR / f"{code}_triaged.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(triaged_rows[0].keys()))
            w.writeheader()
            w.writerows(triaged_rows)
        triage_summary_rows.append({"cdcr_code": code, "is_closed_facility": is_closed, **counts, **fqa})

    if zero_detail_rows:
        with open(TRIAGE_DIR / "zero_roof_triage_detail.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(zero_detail_rows[0].keys()))
            w.writeheader()
            w.writerows(zero_detail_rows)
    with open(TRIAGE_DIR / "facility_triage_and_roof_qa.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(triage_summary_rows[0].keys()))
        w.writeheader()
        w.writerows(triage_summary_rows)
    if render_sheets:
        render_zero_roof_contact_sheets(zero_items_for_sheets)
    print(f"Triaged {len(triage_summary_rows)} prisons: zero_roof_in_RAPT={len(zero_detail_rows)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile footprints (Overture, LiDAR+NAIP residuals) and triage zero-roof polygons.")
    parser.add_argument("--stage", choices=["overture", "lidar-scan", "lidar-commit", "triage", "all"], default="triage")
    parser.add_argument("--only", nargs="*", help="Only process specified CDCR codes (overture / lidar-scan)")
    parser.add_argument("--commit-spec", default="all", help="JSON path mapping code -> [accepted_ids], or 'all'")
    parser.add_argument("--no-sheets", action="store_true", help="Skip contact sheet rendering during triage")
    args = parser.parse_args()

    if args.stage in ("overture", "all"):
        reconcile_overture(only=args.only)
    if args.stage in ("lidar-scan", "all"):
        scan_lidar_residuals(only=args.only)
    if args.stage == "lidar-commit":
        commit_lidar_candidates(args.commit_spec)
    if args.stage in ("triage", "all"):
        triage_zero_roof(render_sheets=not args.no_sheets)


if __name__ == "__main__":
    main()
