#!/usr/bin/env python3
"""
Step 2D: Housing identification, building category refinement, and verified story-count
derivation across all 34 CDCR institutions (2,114 in-RAPT polygons + 2,321 buffer/adjacent).

Inputs:
  - notes/building_heights_pilot/all_34/heights/{CODE}_triaged.csv
  - notes/building_heights_pilot/all_34/step2d_housing/building_features.csv
  - notes/building_heights_pilot/all_34/footprints/{CODE}_reconciled.geojson
  - notes/building_heights_pilot/all_34/all_34_summary.csv
  - notes/building_heights_pilot/all_34/step2d_housing/housing_overrides.json (optional/iterated)
  - data/buildings/spi_cdcr_structures.csv (read-only reference)

Outputs:
  - notes/building_heights_pilot/all_34/heights/{CODE}_step2d.csv
  - notes/building_heights_pilot/all_34/step2d_housing/{CODE}_housing_qa.png
  - notes/building_heights_pilot/all_34/step2d_housing/housing_audit_summary.csv
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import rasterio
from pyproj import Transformer
from shapely.geometry import shape

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parents[1]
PILOT = ROOT / "notes" / "building_heights_pilot"
ALL34 = PILOT / "all_34"
HEIGHTS_DIR = ALL34 / "heights"
FP_DIR = ALL34 / "footprints"
OUT_DIR = ALL34 / "step2d_housing"
NAIP_DIR = ROOT / "sources" / "imagery" / "naip_2024"
OVERRIDES_PATH = SCRIPTS_DIR / "housing_overrides.json"

TO_3857 = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)

# 270 / 180 / Level I-II / Reception / Cross-pod standard prison groups
# Used only as contextual priors alongside per-building geometry & LiDAR height modes.
RADIAL_RC_PRISONS = {"NKSP", "WSP"}
CROSS_POD_1STORY_PRISONS = {"CCWF", "VSP"}
AMBIGUOUS_COMPLEX_PRISONS = {
    "CHCF", "CMC", "CMF", "FOL", "SQ", "CIM", "CIW", "CRC", "CTF", "SOL", "RJD",
    "SCC", "CAC", "CVSP", "FWF",
}


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default


def parse_modes(modes_str: str) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    if not modes_str:
        return out
    for part in modes_str.split(";"):
        part = part.strip()
        if "ft(" in part:
            try:
                h = float(part.split("ft(")[0])
                p = float(part.split("ft(")[1].rstrip("%)"))
                out.append((h, p))
            except Exception:
                pass
    return out


def derive_non_housing_stories(
    p25: float | None,
    p50: float | None,
    p90: float | None,
    modes: list[tuple[float, float]],
    sqft: float,
    triage_status: str,
) -> tuple[str, str, str, str]:
    """Derive conservative story counts for standing non-housing buildings inside RAPT."""
    if triage_status == "new_post_lidar_bldg" or p50 is None:
        return "", "", "indeterminate", "indeterminate_no_lidar"

    # Guard towers / tall communication / water towers (< 2,200 sqft and >= 30 ft): physical shaft height, not conventional multi-story occupancy
    if sqft < 2200 and p50 >= 28.0:
        return "1", "1", "medium", "tower_or_elevated_post"

    # Low sheds/booths/pump houses (< 18 ft)
    if p90 is not None and p90 <= 20.5 and p50 <= 18.5:
        return "1", "1", "high", "lidar_uniform_height"

    # High-bay gymnasium / warehouse / PIA factory / industrial central plant (~21-35 ft single-volume interior)
    # Distinguishable by moderate uniform flat/clerestory roof (~20-30 ft) without residential multi-tier pattern
    high_modes = [h for h, p in modes if h >= 22.0 and p >= 15.0]
    low_modes = [h for h, p in modes if h <= 19.5 and p >= 15.0]

    if p90 is not None and p90 >= 42.0 and sqft >= 5000:
        st = max(3, min(5, int(round(p90 / 12.5))))
        lo = max(1, int(round((p25 or p50) / 14.0)))
        rng = f"{lo}-{st}" if lo < st else f"{st}"
        return str(st), rng, "medium", "lidar_sub_tier_modes"

    if p50 <= 22.5 and (p90 is None or p90 <= 26.5):
        # Single-story with parapet/clerestory or gym bay
        if low_modes and high_modes:
            return "1", "1-2", "medium", "lidar_highbay_or_split"
        return "1", "1", "high", "lidar_uniform_height"

    if p50 >= 26.5 and sqft >= 5000:
        if low_modes and high_modes:
            hi_s = max(2, min(4, int(round(max(high_modes) / 12.5))))
            return str(hi_s), f"1-{hi_s}", "medium", "lidar_sub_tier_modes"
        if (p90 and p90 >= 31.0) or p50 >= 28.0:
            hi_s = max(2, min(4, int(round(p50 / 13.0))))
            return str(hi_s), f"{max(1, hi_s-1)}-{hi_s}", "medium", "lidar_height_band"
        # High-bay gym / PIA / auditorium (~26.5-28 ft without upper sub-tier)
        return "1", "1-2", "medium", "lidar_highbay_or_split"

    if 22.5 < p50 < 26.5 or (p90 is not None and p90 > 26.5):
        return "1", "1-2", "medium", "lidar_highbay_or_split"

    return "1", "1", "medium", "lidar_uniform_height"


def classify_standard_building(
    code: str,
    r: dict[str, str],
    feat_row: dict[str, str],
) -> dict[str, str]:
    """
    Baseline rule-based classifier using LiDAR roof heights/modes + polygon geometry
    (area, solidity, aspect ratio). Ambiguous / custom facilities are refined via
    housing_overrides.json verified from visual QA + SPI.
    """
    fid = r["footprint_id"]
    triage = r["triage_status"]
    in_rapt = r["in_rapt_boundary"] == "yes"
    sqft = fnum(r["footprint_sqft"], 0.0)
    sol = fnum(feat_row.get("solidity"), 1.0)
    asp = fnum(feat_row.get("aspect_ratio"), 1.0)
    p25 = fnum(r["roof_p25_ft"], -1.0)
    p50 = fnum(r["roof_p50_ft"], -1.0)
    p90 = fnum(r["roof_p90_ft"], -1.0)
    p25v = None if p25 < 0 else p25
    p50v = None if p50 < 0 else p50
    p90v = None if p90 < 0 else p90
    sub_modes_str = feat_row.get("sub_tier_heights_ft", "")
    modes = parse_modes(sub_modes_str)

    # Non-standing / Outside-RAPT rows
    if not in_rapt:
        cat = "adjacent_prison_rapt" if r.get("other_rapt_code") else "buffer_300m_outside"
        return {
            "is_housing": "",
            "building_category": cat,
            "housing_prototype": "",
            "sub_tier_heights_ft": sub_modes_str,
            "solidity": f"{sol:.3f}",
            "stories": "",
            "stories_range": "",
            "story_confidence": "",
            "story_method": "",
        }
    if triage in ("demolished_or_pad", "solar_carport_or_array"):
        return {
            "is_housing": "no",
            "building_category": triage,
            "housing_prototype": "non_housing",
            "sub_tier_heights_ft": "",
            "solidity": f"{sol:.3f}",
            "stories": "",
            "stories_range": "",
            "story_confidence": "",
            "story_method": "",
        }

    # --- Known LiDAR-void standing prototypes ---
    if fid in ("ISP-fp-021", "ISP-fp-031"):
        return {
            "is_housing": "yes",
            "building_category": "housing",
            "housing_prototype": "level1_dorm_standard",
            "sub_tier_heights_ft": sub_modes_str,
            "solidity": f"{sol:.3f}",
            "stories": "1",
            "stories_range": "1",
            "story_confidence": "high",
            "story_method": "prototype_sister_unit_and_naip",
        }

    # 1. CDCR 180-degree housing prototype:
    #    Footprint 31k–42k sqft, solidity 0.56–0.69, aspect 1.65–2.25, uniform 22.0–27.5 ft flat roof
    if (
        31000 <= sqft <= 42500
        and 0.56 <= sol <= 0.695
        and 1.60 <= asp <= 2.25
        and p50v is not None
        and 21.5 <= p50v <= 28.0
    ):
        return {
            "is_housing": "yes",
            "building_category": "housing",
            "housing_prototype": "180_housing_unit",
            "sub_tier_heights_ft": sub_modes_str,
            "solidity": f"{sol:.3f}",
            "stories": "2",
            "stories_range": "2",
            "story_confidence": "high",
            "story_method": "lidar_mode_and_prototype",
        }

    # Note PBSP/SAC merged 180 pairs (~78k-85k) -> check overrides for PBSP-fp-022 if needed!

    # 2. CDCR 270-degree housing prototype:
    #    Footprint 15.0k–22.5k sqft (or 10k-12.5k half-270!), solidity 0.78–0.94, aspect 1.00–1.28, roof 19.5–25.5 ft
    if (
        15000 <= sqft <= 22800
        and 0.78 <= sol <= 0.945
        and 1.00 <= asp <= 1.28
        and p50v is not None
        and 19.5 <= p50v <= 25.5
        and code not in {"SQ", "CIW"}
    ):
        return {
            "is_housing": "yes",
            "building_category": "housing",
            "housing_prototype": "270_housing_unit",
            "sub_tier_heights_ft": sub_modes_str,
            "solidity": f"{sol:.3f}",
            "stories": "2",
            "stories_range": "1-2",
            "story_confidence": "high",
            "story_method": "lidar_mode_and_prototype",
        }

    # 2b. Half-270 buildings (e.g., HDSP-lid-003 10.7k sqft, COR/RJD split, or ASU 34.4k 2-tier 15/21.5 ft)
    if (
        9500 <= sqft <= 13000
        and 0.75 <= sol <= 0.93
        and 1.35 <= asp <= 1.85
        and p50v is not None
        and 19.5 <= p50v <= 24.5
        and (p90v is None or p90v <= 26.0)
        and code not in {"FOL", "SQ", "CIW", "CRC", "CTF", "CIM", "CMC", "CMF", "CHCF", "FWF"}
    ):
        return {
            "is_housing": "yes",
            "building_category": "housing",
            "housing_prototype": "270_housing_unit",
            "sub_tier_heights_ft": sub_modes_str,
            "solidity": f"{sol:.3f}",
            "stories": "2",
            "stories_range": "1-2",
            "story_confidence": "medium",
            "story_method": "lidar_mode_and_prototype",
        }

    # 3. 2-story SHU / ASU standalone rectangular+sallyport prototype (~33.5k-36k sqft, sol ~0.82-0.86, asp ~1.8-2.1, bimodal 15ft + 21.5ft, e.g., KVSP-fp-002/066)
    #    or standard standalone AD-SEG prototype (~24.9k-29.0k sqft, sol ~0.85-0.92, asp ~1.55-1.90, 14.5ft + 21.5ft)
    if (
        32000 <= sqft <= 36500
        and 0.78 <= sol <= 0.89
        and 1.75 <= asp <= 2.15
        and any(13.5 <= h <= 17.5 and p >= 15.0 for h, p in modes)
        and any(20.0 <= h <= 24.5 and p >= 35.0 for h, p in modes)
    ) or (
        24500 <= sqft <= 29500
        and 0.83 <= sol <= 0.94
        and 1.50 <= asp <= 1.95
        and any(13.5 <= h <= 16.5 and p >= 12.0 for h, p in modes)
        and any(20.0 <= h <= 23.0 and p >= 45.0 for h, p in modes)
        and code not in {"ASP", "SQ", "FOL", "CTF", "CIM", "CIW", "CMC", "CMF", "CRC", "CHCF", "FWF", "SCC", "SOL"}
    ):
        return {
            "is_housing": "yes",
            "building_category": "housing",
            "housing_prototype": "asu_2tier_unit",
            "sub_tier_heights_ft": sub_modes_str,
            "solidity": f"{sol:.3f}",
            "stories": "2",
            "stories_range": "1-2",
            "story_confidence": "high",
            "story_method": "lidar_sub_tier_modes",
        }

    # 4. CDCR Cross / X-pod 1-story (CCWF, VSP): ~24.5k-28.5k sqft, sol 0.55-0.61, asp 0.98-1.08, p50 16.5-19.0 ft, p90 <= 21.5 ft
    if (
        code in CROSS_POD_1STORY_PRISONS
        and 24000 <= sqft <= 29000
        and 0.54 <= sol <= 0.63
        and asp <= 1.12
        and p50v is not None
        and 16.0 <= p50v <= 20.0
    ):
        return {
            "is_housing": "yes",
            "building_category": "housing",
            "housing_prototype": "cross_pod_dorm_1story",
            "sub_tier_heights_ft": sub_modes_str,
            "solidity": f"{sol:.3f}",
            "stories": "1",
            "stories_range": "1",
            "story_confidence": "high",
            "story_method": "lidar_and_spi_sqft_ratio",
        }

    # 5. SATF / MCSP 2-story X-pod / Level II dorms (~29k-36k sqft, sol 0.65-0.78, asp 1.00-1.25, mode ~23-24ft + 13ft hub)
    if (
        code in {"SATF", "MCSP"}
        and 29000 <= sqft <= 37000
        and 0.65 <= sol <= 0.78
        and 1.00 <= asp <= 1.25
        and p50v is not None
        and 21.5 <= p50v <= 26.0
    ):
        return {
            "is_housing": "yes",
            "building_category": "housing",
            "housing_prototype": "xpod_2story_dorm",
            "sub_tier_heights_ft": sub_modes_str,
            "solidity": f"{sol:.3f}",
            "stories": "2",
            "stories_range": "1-2",
            "story_confidence": "high",
            "story_method": "lidar_sub_tier_modes",
        }

    # 6. Standard CDCR Level I / II 1-story Dormitory (13,244 sqft SPI signature):
    #    Footprint 12,800–16,200 sqft, sol >= 0.88, asp 1.48–1.98, p50 14.5–18.5 ft, p90 <= 22.5 ft (gabled ridge ~20-21.5 ft)
    #    (Also 16k-17k rectangular dorms in CAL/COR/SAC if matched below or via overrides)
    if (
        12800 <= sqft <= 16200
        and sol >= 0.88
        and 1.45 <= asp <= 2.00
        and p50v is not None
        and 13.8 <= p50v <= 18.8
        and (p90v is None or p90v <= 22.8)
    ):
        return {
            "is_housing": "yes",
            "building_category": "housing",
            "housing_prototype": "level1_dorm_standard",
            "sub_tier_heights_ft": sub_modes_str,
            "solidity": f"{sol:.3f}",
            "stories": "1",
            "stories_range": "1",
            "story_confidence": "high",
            "story_method": "lidar_and_spi_sqft_ratio",
        }

    # 7. NKSP / WSP Reception Center radial celled/dorm wings (~26k-45k sqft, sol 0.65-0.78, asp 2.8-4.8, p50 20.0-22.5 ft)
    if (
        code in RADIAL_RC_PRISONS
        and 25000 <= sqft <= 46000
        and 0.64 <= sol <= 0.78
        and asp >= 2.6
        and p50v is not None
        and 19.5 <= p50v <= 23.0
    ):
        return {
            "is_housing": "yes",
            "building_category": "housing",
            "housing_prototype": "reception_radial_wing",
            "sub_tier_heights_ft": sub_modes_str,
            "solidity": f"{sol:.3f}",
            "stories": "2",
            "stories_range": "1-2",
            "story_confidence": "high",
            "story_method": "lidar_mode_and_prototype",
        }

    # --- Non-housing heuristics inside RAPT ---
    # Very small buildings (< 2,500 sqft): guard towers, booths, pump houses, utility sheds
    if sqft < 2500:
        cat = "guard_tower_utility"
    elif sqft < 8000 and (p50v is not None and p50v < 15.0):
        cat = "support_warehouse_pia"
    elif p50v is not None and p50v >= 27.0 and sqft >= 20000 and sol >= 0.72 and asp >= 2.2:
        # Usually high-bay gym / dining / warehouse / central facility
        cat = "program_admin_medical"
    elif sqft >= 25000 and p50v is not None and p50v <= 19.5:
        cat = "program_admin_medical"
    else:
        cat = "program_admin_medical"

    st, rng, conf, meth = derive_non_housing_stories(p25v, p50v, p90v, modes, sqft, triage)
    return {
        "is_housing": "no",
        "building_category": cat,
        "housing_prototype": "non_housing",
        "sub_tier_heights_ft": sub_modes_str,
        "solidity": f"{sol:.3f}",
        "stories": st,
        "stories_range": rng,
        "story_confidence": conf,
        "story_method": meth,
    }


def apply_override(base: dict[str, str], ov: dict[str, Any]) -> dict[str, str]:
    out = dict(base)
    for k in (
        "is_housing",
        "building_category",
        "housing_prototype",
        "stories",
        "stories_range",
        "story_confidence",
        "story_method",
    ):
        if k in ov and ov[k] is not None:
            out[k] = str(ov[k])
    return out


def load_font(size: int) -> ImageFont.ImageFont:
    for fp in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ):
        if Path(fp).exists():
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                pass
    return ImageFont.load_default()


def render_housing_qa(
    code: str,
    inst_name: str,
    tif_path: Path | None,
    feats: list[dict[str, Any]],
    rows: list[dict[str, str]],
    spi_h_count: int,
) -> None:
    if tif_path is None or not tif_path.exists():
        return
    with rasterio.open(tif_path) as src:
        arr = src.read([1, 2, 3])
        rgb = np.transpose(arr, (1, 2, 0))
        if rgb.dtype != np.uint8:
            rgb = np.clip(rgb, 0, 255).astype(np.uint8)
        img = Image.fromarray(rgb)
        bounds = src.bounds
        w, h = src.width, src.height
        to_src = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)

    scale = min(1.0, 2000.0 / max(w, h))
    nw, nh = int(round(w * scale)), int(round(h * scale))
    if scale < 1.0:
        img = img.resize((nw, nh), Image.BILINEAR)
    draw = ImageDraw.Draw(img)
    font = load_font(12)
    hdr_font = load_font(15)

    def to_px(x_s: float, y_s: float) -> tuple[float, float]:
        px = (x_s - bounds.left) / (bounds.right - bounds.left) * nw
        py = (bounds.top - y_s) / (bounds.top - bounds.bottom) * nh
        return px, py

    by_id = {r["footprint_id"]: r for r in rows}
    story_colors = {
        "1": (0, 225, 255),      # Cyan = 1s housing
        "2": (255, 195, 0),      # Gold = 2s housing
        "3": (255, 80, 220),     # Magenta = 3s housing
        "4": (255, 60, 60),      # Red = 4s+ housing
        "5": (255, 60, 60),
    }

    h_cnt = 0
    for ft in feats:
        fid = ft["properties"]["footprint_id"]
        r = by_id.get(fid)
        if not r or r["in_rapt_boundary"] != "yes":
            continue
        geom = shape(ft["geometry"])
        is_h = r["is_housing"] == "yes"
        triage = r["triage_status"]
        if is_h:
            h_cnt += 1
            col = story_colors.get(r["stories"], (180, 180, 255))
            width = 3
        elif triage in ("demolished_or_pad", "excluded_non_occupied"):
            col = (220, 40, 40)
            width = 1
        elif r["building_category"] == "guard_tower_utility":
            col = (150, 150, 150)
            width = 1
        elif r["building_category"] == "canopy":
            col = (130, 220, 190)
            width = 2
        else:
            col = (100, 230, 110)
            width = 2

        polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
        for p in polys:
            xs, ys = p.exterior.coords.xy
            tx, ty = to_src.transform(list(xs), list(ys))
            pts = [to_px(x, y) for x, y in zip(tx, ty)]
            draw.line(pts, fill=col, width=width)

        sqft = fnum(r["footprint_sqft"], 0.0)
        if is_h or sqft >= 4000:
            c = geom.centroid
            cx, cy = to_src.transform(c.x, c.y)
            px, py = to_px(cx, cy)
            short_id = fid.replace(f"{code}-fp-", "").replace(f"{code}-", "")
            if is_h:
                rng = r["stories_range"] or r["stories"] or "?"
                p50 = r["roof_p50_ft"] or "-"
                p90 = r["roof_p90_ft"] or "-"
                lbl = f"H:{short_id} [{rng}s {p50}/{p90}]"
            elif triage == "demolished_or_pad":
                lbl = f"X:{short_id}"
            else:
                p50 = r["roof_p50_ft"] or "-"
                lbl = f"{short_id} ({r['stories']}s {p50})"
            draw.text((px - 22, py - 6), lbl, fill=(0, 0, 0), font=font)
            draw.text((px - 23, py - 7), lbl, fill=col, font=font)

    # Top banner
    draw.rectangle([(0, 0), (nw, 30)], fill=(15, 18, 22))
    banner = (
        f"{code} ({inst_name}) | Housing={h_cnt} (SPI_dorm={spi_h_count}) | "
        f"Cyan=1s Gold=2s Mag=3s Red=4-5s Green=NonH-Bldg"
    )
    draw.text((10, 7), banner, fill=(240, 245, 250), font=hdr_font)
    img.save(OUT_DIR / f"{code}_housing_qa.png")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-qa-png", action="store_true")
    parser.add_argument("--codes", nargs="*", help="Optional subset of codes for QA rendering")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(ALL34 / "all_34_summary.csv") as f:
        summary_rows = {r["cdcr_code"]: r for r in csv.DictReader(f)}
    with open(ROOT / "crosswalk" / "institutions.csv") as f:
        inst_names = {r["cdcr_code"]: r["institution_name"] for r in csv.DictReader(f)}
    with open(OUT_DIR / "building_features.csv") as f:
        feat_rows = {r["footprint_id"]: r for r in csv.DictReader(f)}

    overrides: dict[str, Any] = {}
    if OVERRIDES_PATH.exists():
        raw_ov = json.loads(OVERRIDES_PATH.read_text())
        overrides = raw_ov.get("overrides", raw_ov) if isinstance(raw_ov, dict) else {}

    # Count SPI DORMITORY rows per prison for cross-check
    spi_dorm_cnt = collections.Counter()
    with open(ROOT / "data" / "buildings" / "spi_cdcr_structures.csv") as f:
        for r in csv.DictReader(f):
            if r["structure_type"] in {"DORMITORY", "RELOCATABLE DORMITORY"}:
                spi_dorm_cnt[r["cdcr_code"]] += 1

    audit_rows: list[dict[str, Any]] = []
    for code in sorted(summary_rows):
        in_csv = HEIGHTS_DIR / f"{code}_triaged.csv"
        with open(in_csv) as f:
            reader = csv.DictReader(f)
            base_cols = list(reader.fieldnames or [])
            rows = list(reader)

        new_cols = [
            "is_housing",
            "housing_prototype",
            "sub_tier_heights_ft",
            "solidity",
            "stories",
            "stories_range",
            "story_confidence",
            "story_method",
        ]
        out_cols = list(base_cols)
        for c in new_cols:
            if c not in out_cols:
                out_cols.append(c)

        out_rows: list[dict[str, str]] = []
        story_hist: collections.Counter[str] = collections.Counter()
        proto_hist: collections.Counter[str] = collections.Counter()
        h_standing = 0
        non_h_standing = 0
        indet = 0

        for r in rows:
            fid = r["footprint_id"]
            res = classify_standard_building(code, r, feat_rows.get(fid, {}))
            ov = overrides.get(fid)
            merged = dict(r)
            if ov and ov.get("exclude_from_output"):
                res.update({
                    "is_housing": "no",
                    "building_category": str(ov.get("exclude_reason", "non_occupied_utility")),
                    "housing_prototype": "non_housing",
                    "stories": "",
                    "stories_range": "",
                    "story_confidence": "",
                    "story_method": "excluded_non_occupied",
                })
                merged["triage_status"] = "excluded_non_occupied"
            elif ov:
                res = apply_override(res, ov)
            merged.update(res)
            out_rows.append(merged)

            if merged["in_rapt_boundary"] == "yes" and merged["triage_status"] in ("valid_standing", "new_post_lidar_bldg"):
                if merged["is_housing"] == "yes":
                    h_standing += 1
                    story_hist[merged["stories"] or "blank"] += 1
                    proto_hist[merged["housing_prototype"]] += 1
                else:
                    non_h_standing += 1
                if not merged["stories"]:
                    indet += 1

        out_csv = HEIGHTS_DIR / f"{code}_step2d.csv"
        with open(out_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=out_cols)
            w.writeheader()
            w.writerows(out_rows)

        if not args.no_qa_png and (not args.codes or code in args.codes):
            with open(FP_DIR / f"{code}_reconciled.geojson") as f:
                feats = json.load(f)["features"]
            tif_candidate = NAIP_DIR / f"{code}_naip_2024.tif"
            tif_path = tif_candidate if tif_candidate.exists() else None
            render_housing_qa(
                code,
                inst_names.get(code, code),
                tif_path,
                feats,
                out_rows,
                spi_dorm_cnt.get(code, 0),
            )

        audit_rows.append({
            "cdcr_code": code,
            "is_closed": summary_rows[code]["is_closed"],
            "housing_units": h_standing,
            "spi_dormitory_rows": spi_dorm_cnt.get(code, 0),
            "non_housing_standing": non_h_standing,
            "housing_1s": story_hist.get("1", 0),
            "housing_2s": story_hist.get("2", 0),
            "housing_3s": story_hist.get("3", 0),
            "housing_4_5s": story_hist.get("4", 0) + story_hist.get("5", 0),
            "indeterminate_stories": indet,
            "prototypes": ";".join(f"{k}:{v}" for k, v in sorted(proto_hist.items())),
        })
        print(
            f"{code:4s}: housing={h_standing:2d} (SPI_dorm={spi_dorm_cnt.get(code, 0):2d}) "
            f"1s={story_hist.get('1',0):2d} 2s={story_hist.get('2',0):2d} "
            f"3+s={story_hist.get('3',0)+story_hist.get('4',0)+story_hist.get('5',0):2d} "
            f"non_h={non_h_standing:2d}",
            flush=True,
        )

    with open(OUT_DIR / "housing_audit_summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(audit_rows[0].keys()))
        w.writeheader()
        w.writerows(audit_rows)
    print("Done Step 2D baseline pass.")


if __name__ == "__main__":
    main()
