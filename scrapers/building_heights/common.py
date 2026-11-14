"""
Shared constants, geometry/HTTP helpers, NAIP canvas renderer, and unified USGS 3DEP
LiDAR roof-height measurement utilities for scrapers/building_heights/.
"""
from __future__ import annotations

import csv
import json
import math
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import laspy
import numpy as np
import rasterio
from PIL import Image, ImageDraw, ImageFont
from pyproj import Transformer
from shapely import contains_xy
from shapely.geometry import box, shape
from shapely.ops import transform as shp_transform, unary_union

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parents[1]
WORK_DIR = ROOT / "notes" / "building_heights_pilot"
RAW_DIR = WORK_DIR / "raw"
EPT_CACHE = WORK_DIR / "tmp_ept"
ALL34_DIR = WORK_DIR / "all_34"
FP_DIR = ALL34_DIR / "footprints"
HT_DIR = ALL34_DIR / "heights"
OVT_DIR = ALL34_DIR / "overture"
QA_DIR = ALL34_DIR / "qa_overlays"
CAND_DIR = ALL34_DIR / "step2b_candidates"
TRIAGE_DIR = ALL34_DIR / "step2c_triage"
HOUSING_QA_DIR = ALL34_DIR / "step2d_housing"
NAIP_DIR = ROOT / "sources" / "imagery" / "naip_2024"
NAIP_RGB_DIR = ROOT / "sources" / "imagery" / "naip_2024_rgb"
QA_IMAGES_DIR = SCRIPTS_DIR / "qa_images"
DATA_BUILDINGS = ROOT / "data" / "buildings"

TO_3857 = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform
TO_4326 = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True).transform
M_TO_FT = 3.28084
SQM_TO_SQFT = 10.7639104
CLOSED_CODES = {"CAC", "CVSP", "FWF"}

TRIAGE_OVERRIDES_PATH = SCRIPTS_DIR / "triage_overrides.json"
HOUSING_OVERRIDES_PATH = SCRIPTS_DIR / "housing_overrides.json"


def ensure_work_dirs() -> None:
    """Create cached workspace directories when needed."""
    for d in (
        RAW_DIR,
        EPT_CACHE,
        ALL34_DIR,
        FP_DIR,
        HT_DIR,
        OVT_DIR,
        QA_DIR,
        CAND_DIR,
        TRIAGE_DIR,
        HOUSING_QA_DIR,
        NAIP_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)


def fnum(value: Any, default: float = 0.0) -> float:
    """Parse float defensively, returning default for blank/invalid values."""
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def curl_bytes(
    url: str, headers: list[str] | None = None, data: str | None = None, timeout: int = 45
) -> bytes:
    """Fetch binary response via curl with optional headers and POST body."""
    cmd = ["curl", "-sS", "--fail", "--max-time", str(timeout), "-L", "-A", "cdcr-facility-data/1.0"]
    for h in headers or []:
        cmd += ["-H", h]
    if data is not None:
        cmd += ["-X", "POST", "--data-raw", data]
    cmd.append(url)
    return subprocess.run(cmd, capture_output=True, check=True).stdout


def curl_json(
    url: str, headers: list[str] | None = None, data: str | None = None, timeout: int = 45
) -> dict[str, Any]:
    """Fetch JSON object via curl."""
    return json.loads(curl_bytes(url, headers=headers, data=data, timeout=timeout))


def parse_ept_year(name: str) -> int:
    """Infer collection year from USGS EPT dataset name."""
    years = [int(y) for y in re.findall(r"(?:19|20)\d{2}", name)]
    if years:
        return max(years)
    match = re.search(r"_[A-Z](\d{2})$", name)
    return 2000 + int(match.group(1)) if match else 0


def select_ept_project(rapt_geom_wgs: Any, ept_feats: list[tuple[str, int, Any]]) -> tuple[str | None, float, int]:
    """Select the highest-coverage, newest USGS EPT collection intersecting a facility."""
    candidates = []
    for name, cnt, geom in ept_feats:
        if geom.intersects(rapt_geom_wgs):
            frac = geom.intersection(rapt_geom_wgs).area / rapt_geom_wgs.area
            if frac > 0.05:
                candidates.append((frac >= 0.98, round(frac, 3), parse_ept_year(name), cnt or 0, name))
    if not candidates:
        return None, 0.0, 0
    candidates.sort(reverse=True)
    _, frac, yr, _, name = candidates[0]
    return name, frac, yr


def load_institutions_and_rapt() -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Load crosswalk institutions and map cdcr_code to RAPT boundary polygons."""
    rapt_raw = json.loads((RAW_DIR / "Prison_Boundaries_RAPT.geojson").read_text())["features"]
    rapt_by_fid = {
        str(f["properties"]["FACILITYID"]).strip(): shape(f["geometry"])
        for f in rapt_raw
        if f["properties"].get("FACILITYID")
    }
    insts = list(csv.DictReader(open(ROOT / "crosswalk" / "institutions.csv")))
    rapt_by_code = {r["cdcr_code"]: rapt_by_fid[r["fema_facilityid"].strip()] for r in insts}
    return insts, rapt_by_code


def load_font(size: int) -> ImageFont.ImageFont:
    """Load a crisp TrueType font for QA overlays with Pillow default fallback."""
    for fp in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSMono.ttf",
        "/Library/Fonts/Arial.ttf",
    ):
        if Path(fp).exists():
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                pass
    return ImageFont.load_default()


def open_naip_rgb_canvas(
    tif_path: Path, max_dim: int = 1800
) -> tuple[Image.Image, Any, float]:
    """Open 2024 NAIP GeoTIFF as RGB Pillow image scaled to max_dim, returning (img, transform, scale)."""
    with rasterio.open(tif_path) as src:
        rgb = np.transpose(src.read([1, 2, 3]), (1, 2, 0))
        transform = src.transform
        h, w = rgb.shape[:2]
    if rgb.dtype != np.uint8:
        rgb = np.clip(rgb, 0, 255).astype(np.uint8)
    scale = min(1.0, float(max_dim) / max(h, w))
    img = Image.fromarray(rgb, mode="RGB")
    if scale < 1.0:
        img = img.resize((int(round(w * scale)), int(round(h * scale))), Image.Resampling.BILINEAR)
    return img, transform, scale


def make_wgs_to_px(transform: Any, scale: float):
    """Return a WGS84 (lon, lat) -> canvas pixel (x, y) projection function."""
    inv = ~transform

    def to_px(lon: float, lat: float) -> tuple[float, float]:
        col, row = inv * (lon, lat)
        return col * scale, row * scale

    return to_px


def draw_wgs_outline(
    draw: ImageDraw.ImageDraw,
    geom: Any,
    to_px: Any,
    color: tuple[int, ...],
    width: int = 2,
) -> None:
    """Draw a Shapely Polygon or MultiPolygon exterior outline in canvas coordinates."""
    geoms = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    for poly in geoms:
        pts = [to_px(x, y) for x, y in poly.exterior.coords]
        if len(pts) >= 2:
            draw.line(pts, fill=color, width=width)


def _child_box(b: list[float], dx: int, dy: int, dz: int) -> list[float]:
    mx, my, mz = (b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2
    return [
        mx if dx else b[0], my if dy else b[1], mz if dz else b[2],
        b[3] if dx else mx, b[4] if dy else my, b[5] if dz else mz,
    ]


def _collect_ept_chunks_adaptive(
    base_url: str, ept: dict[str, Any], target_geom_3857: Any, max_pts: int = 18_000_000
) -> tuple[list[tuple[str, int]], int]:
    eb = ept["bounds"]
    all_nodes: list[tuple[int, str, int]] = []

    def walk_hier(root_key: str, root_box: list[float]) -> None:
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
                                stack.append((ck, _child_box(nb, dx, dy, dz)))

    walk_hier("0-0-0-0", eb)
    chosen_depth = 13
    for d_try in (13, 12, 11):
        if sum(cnt for d, _, cnt in all_nodes if d <= d_try) <= max_pts or d_try == 11:
            chosen_depth = d_try
            break
    return [(k, cnt) for d, k, cnt in all_nodes if d <= chosen_depth], chosen_depth


def load_local_laz_points(
    code: str, proj: str, bounds_3857: tuple[float, float, float, float]
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Load cached EPSG:3857 LAZ points intersecting bounds_3857 without network calls."""
    pdir = EPT_CACHE / ("CA_NorthernCA_6_B22_PBSP" if code == "PBSP" else proj)
    if not pdir.exists():
        empty = np.array([], dtype=np.float64)
        return empty, empty, empty, np.array([], dtype=np.uint8)
    bx0, by0, bx1, by1 = bounds_3857
    xs, ys, zs, cls = [], [], [], []
    for lp in sorted(pdir.glob("*.laz")):
        with laspy.open(lp) as fp:
            h = fp.header
            if h.maxs[0] < bx0 or h.mins[0] > bx1 or h.maxs[1] < by0 or h.mins[1] > by1:
                continue
            las = fp.read()
            x, y = np.asarray(las.x), np.asarray(las.y)
            m = (x >= bx0) & (x <= bx1) & (y >= by0) & (y <= by1)
            if m.any():
                xs.append(x[m])
                ys.append(y[m])
                zs.append(np.asarray(las.z)[m])
                cls.append(np.asarray(las.classification)[m])
    if not xs:
        empty = np.array([], dtype=np.float64)
        return empty, empty, empty, np.array([], dtype=np.uint8)
    return np.concatenate(xs), np.concatenate(ys), np.concatenate(zs), np.concatenate(cls)


def load_ept_points_for_features(
    code: str, proj: str, feats: list[dict[str, Any]], allow_remote: bool = True
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, int]:
    """Load LAZ points covering feats (locally cached first, remote AWS EPT if allowed)."""
    polys_3857 = [shp_transform(TO_3857, shape(f["geometry"])) for f in feats]
    mean_lat = sum(f["properties"]["centroid_lat"] for f in feats) / len(feats)
    ring_15 = 15.0 / math.cos(math.radians(mean_lat))
    union_target = unary_union([g.buffer(ring_15) for g in polys_3857])
    pbsp_local = EPT_CACHE / "CA_NorthernCA_6_B22_PBSP"

    if (proj == "CA_NorthernCA_6_B22" and pbsp_local.exists()) or not allow_remote:
        x, y, z, c = load_local_laz_points(code, proj, union_target.bounds)
        return x, y, z, c, 12

    base_url = f"https://s3-us-west-2.amazonaws.com/usgs-lidar-public/{proj}"
    ept = curl_json(f"{base_url}/ept.json", timeout=30)
    horiz = str((ept.get("srs") or {}).get("horizontal", ""))
    assert horiz == "3857", f"Unexpected EPT SRS horizontal={horiz} for {proj}"
    chunks, used_depth = _collect_ept_chunks_adaptive(base_url, ept, union_target)
    cache_dir = EPT_CACHE / proj
    cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch_one(key: str):
        p = cache_dir / f"{key}.laz"
        if not p.exists() or p.stat().st_size == 0:
            p.write_bytes(curl_bytes(f"{base_url}/ept-data/{key}.laz", timeout=60))
        las = laspy.read(p)
        return np.asarray(las.x), np.asarray(las.y), np.asarray(las.z), np.asarray(las.classification)

    xs, ys, zs, cs = [], [], [], []
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(fetch_one, k) for k, _ in chunks]
        for fut in as_completed(futs):
            x, y, z, c = fut.result()
            xs.append(x)
            ys.append(y)
            zs.append(z)
            cs.append(c)
    if not xs:
        empty = np.array([], dtype=np.float64)
        return empty, empty, empty, np.array([], dtype=np.uint8), used_depth
    return np.concatenate(xs), np.concatenate(ys), np.concatenate(zs), np.concatenate(cs), used_depth


def compute_footprint_height_rows(
    code: str,
    proj: str | None,
    feats: list[dict[str, Any]],
    px: np.ndarray,
    py: np.ndarray,
    pz: np.ndarray,
    pcls: np.ndarray,
    used_depth: int | str = 12,
    footprint_source: str = "usa_structures",
) -> list[dict[str, Any]]:
    """
    Compute per-footprint roof percentiles (ft AGL) from LiDAR arrays using a 3-15 m
    surrounding ground calibration ring and a 1 m eroded roof interior.
    """
    if not feats:
        return []
    mean_lat = sum(f["properties"]["centroid_lat"] for f in feats) / len(feats)
    m_to_3857 = 1.0 / math.cos(math.radians(mean_lat))
    ring_15 = 15.0 * m_to_3857
    ring_3 = 3.0 * m_to_3857
    erode_1 = 1.0 * m_to_3857

    rows: list[dict[str, Any]] = []
    for feat in feats:
        p = feat["properties"]
        if not proj:
            rows.append({
                "cdcr_code": code,
                "footprint_id": p["footprint_id"],
                "in_rapt_boundary": p["in_rapt_boundary"],
                "other_rapt_code": p.get("other_rapt_code", ""),
                "dist_to_rapt_m": p.get("dist_to_rapt_m", 0.0),
                "usa_structures_build_id": p.get("BUILD_ID", ""),
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
                "lidar_project": "",
                "ept_depth": "",
                "footprint_source": p.get("footprint_source", footprint_source),
                "height_source": "none",
            })
            continue

        poly = shp_transform(TO_3857, shape(feat["geometry"]))
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
                ring_gnd = ring_all[ring_all <= np.percentile(ring_all, 15)]
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
            "other_rapt_code": p.get("other_rapt_code", ""),
            "dist_to_rapt_m": p.get("dist_to_rapt_m", 0.0),
            "usa_structures_build_id": p.get("BUILD_ID", ""),
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
            "footprint_source": p.get("footprint_source", footprint_source),
            "height_source": f"usgs_3dep_ept:{proj}" if has_roof else "none",
        })
    return rows
