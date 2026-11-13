#!/usr/bin/env python3
"""
Housing identification, building category refinement, and verified story-count
classification across all 34 CDCR institutions.

Reads per-building triaged height tables ({CODE}_triaged.csv), precomputed geometric/
sub-tier features (building_features.csv), and visual QA overrides (housing_overrides.json),
and writes {CODE}_classified.csv plus housing_audit_summary.csv and optional QA overlays.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
from pathlib import Path
from typing import Any

import rasterio
from PIL import ImageDraw
from pyproj import Transformer
from shapely.geometry import shape

from common import (
    ALL34_DIR,
    DATA_BUILDINGS,
    FP_DIR,
    HOUSING_OVERRIDES_PATH,
    HOUSING_QA_DIR,
    HT_DIR,
    NAIP_DIR,
    ROOT,
    fnum,
    load_font,
    open_naip_rgb_canvas,
)

RADIAL_RC_PRISONS = {"NKSP", "WSP"}
CROSS_POD_1STORY_PRISONS = {"CCWF", "VSP"}
NON_HALF270_CODES = {"FOL", "SQ", "CIW", "CRC", "CTF", "CIM", "CMC", "CMF", "CHCF", "FWF"}
NON_ADSEG_CODES = {"ASP", "SQ", "FOL", "CTF", "CIM", "CIW", "CMC", "CMF", "CRC", "CHCF", "FWF", "SCC", "SOL"}


def parse_modes(modes_str: str) -> list[tuple[float, float]]:
    """Parse semicolon-delimited roof height mode strings like '14.5ft(38%);21.5ft(55%)'."""
    out: list[tuple[float, float]] = []
    if not modes_str:
        return out
    for part in modes_str.split(";"):
        part = part.strip()
        if "ft(" in part:
            try:
                out.append((float(part.split("ft(")[0]), float(part.split("ft(")[1].rstrip("%)"))))
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

    if sqft < 2200 and p50 >= 28.0:
        return "1", "1", "medium", "tower_or_elevated_post"

    if p90 is not None and p90 <= 20.5 and p50 <= 18.5:
        return "1", "1", "high", "lidar_uniform_height"

    high_modes = [h for h, p in modes if h >= 22.0 and p >= 15.0]
    low_modes = [h for h, p in modes if h <= 19.5 and p >= 15.0]

    if p90 is not None and p90 >= 42.0 and sqft >= 5000:
        st = max(3, min(5, int(round(p90 / 12.5))))
        lo = max(1, int(round((p25 or p50) / 14.0)))
        rng = f"{lo}-{st}" if lo < st else f"{st}"
        return str(st), rng, "medium", "lidar_sub_tier_modes"

    if p50 <= 22.5 and (p90 is None or p90 <= 26.5):
        if low_modes and high_modes:
            return "1", "1-2", "medium", "lidar_highbay_or_split"
        return "1", "1", "high", "lidar_uniform_height"

    if p50 >= 26.5 and sqft >= 5000:
        if low_modes and high_modes:
            hi_s = max(2, min(4, int(round(max(high_modes) / 12.5))))
            return str(hi_s), f"1-{hi_s}", "medium", "lidar_sub_tier_modes"
        if (p90 and p90 >= 31.0) or p50 >= 28.0:
            hi_s = max(2, min(4, int(round(p50 / 13.0))))
            return str(hi_s), f"{max(1, hi_s - 1)}-{hi_s}", "medium", "lidar_height_band"
        return "1", "1-2", "medium", "lidar_highbay_or_split"

    if 22.5 < p50 < 26.5 or (p90 is not None and p90 > 26.5):
        return "1", "1-2", "medium", "lidar_highbay_or_split"

    return "1", "1", "medium", "lidar_uniform_height"


def _classification_dict(
    is_housing: str,
    category: str,
    prototype: str,
    sub_modes_str: str,
    sol: float,
    stories: str = "",
    stories_range: str = "",
    confidence: str = "",
    method: str = "",
) -> dict[str, str]:
    return {
        "is_housing": is_housing,
        "building_category": category,
        "housing_prototype": prototype,
        "sub_tier_heights_ft": sub_modes_str,
        "solidity": f"{sol:.3f}",
        "stories": stories,
        "stories_range": stories_range,
        "story_confidence": confidence,
        "story_method": method,
    }


def _match_housing_prototype(
    code: str,
    fid: str,
    sqft: float,
    sol: float,
    asp: float,
    p50v: float | None,
    p90v: float | None,
    modes: list[tuple[float, float]],
) -> tuple[str, str, str, str, str] | None:
    """Return (prototype, stories, stories_range, confidence, method) if building matches a standard CDCR housing prototype."""
    if fid in ("ISP-fp-021", "ISP-fp-031"):
        return "level1_dorm_standard", "1", "1", "high", "prototype_sister_unit_and_naip"

    if 31000 <= sqft <= 42500 and 0.56 <= sol <= 0.695 and 1.60 <= asp <= 2.25 and p50v is not None and 21.5 <= p50v <= 28.0:
        return "180_housing_unit", "2", "2", "high", "lidar_mode_and_prototype"

    if 15000 <= sqft <= 22800 and 0.78 <= sol <= 0.945 and 1.00 <= asp <= 1.28 and p50v is not None and 19.5 <= p50v <= 25.5 and code not in {"SQ", "CIW"}:
        return "270_housing_unit", "2", "1-2", "high", "lidar_mode_and_prototype"

    if (
        9500 <= sqft <= 13000
        and 0.75 <= sol <= 0.93
        and 1.35 <= asp <= 1.85
        and p50v is not None
        and 19.5 <= p50v <= 24.5
        and (p90v is None or p90v <= 26.0)
        and code not in NON_HALF270_CODES
    ):
        return "270_housing_unit", "2", "1-2", "medium", "lidar_mode_and_prototype"

    is_shu_asu = (
        32000 <= sqft <= 36500
        and 0.78 <= sol <= 0.89
        and 1.75 <= asp <= 2.15
        and any(13.5 <= h <= 17.5 and p >= 15.0 for h, p in modes)
        and any(20.0 <= h <= 24.5 and p >= 35.0 for h, p in modes)
    )
    is_adseg = (
        24500 <= sqft <= 29500
        and 0.83 <= sol <= 0.94
        and 1.50 <= asp <= 1.95
        and any(13.5 <= h <= 16.5 and p >= 12.0 for h, p in modes)
        and any(20.0 <= h <= 23.0 and p >= 45.0 for h, p in modes)
        and code not in NON_ADSEG_CODES
    )
    if is_shu_asu or is_adseg:
        return "asu_2tier_unit", "2", "1-2", "high", "lidar_sub_tier_modes"

    if code in CROSS_POD_1STORY_PRISONS and 24000 <= sqft <= 29000 and 0.54 <= sol <= 0.63 and asp <= 1.12 and p50v is not None and 16.0 <= p50v <= 20.0:
        return "cross_pod_dorm_1story", "1", "1", "high", "lidar_and_spi_sqft_ratio"

    if code in {"SATF", "MCSP"} and 29000 <= sqft <= 37000 and 0.65 <= sol <= 0.78 and 1.00 <= asp <= 1.25 and p50v is not None and 21.5 <= p50v <= 26.0:
        return "xpod_2story_dorm", "2", "1-2", "high", "lidar_sub_tier_modes"

    if 12800 <= sqft <= 16200 and sol >= 0.88 and 1.45 <= asp <= 2.00 and p50v is not None and 13.8 <= p50v <= 18.8 and (p90v is None or p90v <= 22.8):
        return "level1_dorm_standard", "1", "1", "high", "lidar_and_spi_sqft_ratio"

    if code in RADIAL_RC_PRISONS and 25000 <= sqft <= 46000 and 0.64 <= sol <= 0.78 and asp >= 2.6 and p50v is not None and 19.5 <= p50v <= 23.0:
        return "reception_radial_wing", "2", "1-2", "high", "lidar_mode_and_prototype"

    return None


def classify_standard_building(code: str, r: dict[str, str], feat_row: dict[str, str]) -> dict[str, str]:
    """Rule-based classifier combining LiDAR roof heights/modes and polygon geometry."""
    fid = r["footprint_id"]
    triage = r["triage_status"]
    sol = fnum(feat_row.get("solidity"), 1.0)
    sub_modes_str = feat_row.get("sub_tier_heights_ft", "")

    if r["in_rapt_boundary"] != "yes":
        cat = "adjacent_prison_rapt" if r.get("other_rapt_code") else "buffer_300m_outside"
        return _classification_dict("", cat, "", sub_modes_str, sol)

    if triage in ("demolished_or_pad", "solar_carport_or_array"):
        return _classification_dict("no", triage, "non_housing", "", sol)

    sqft = fnum(r["footprint_sqft"], 0.0)
    asp = fnum(feat_row.get("aspect_ratio"), 1.0)
    p25 = fnum(r["roof_p25_ft"], -1.0)
    p50 = fnum(r["roof_p50_ft"], -1.0)
    p90 = fnum(r["roof_p90_ft"], -1.0)
    p25v = None if p25 < 0 else p25
    p50v = None if p50 < 0 else p50
    p90v = None if p90 < 0 else p90
    modes = parse_modes(sub_modes_str)

    proto_match = _match_housing_prototype(code, fid, sqft, sol, asp, p50v, p90v, modes)
    if proto_match is not None:
        proto, st, rng, conf, meth = proto_match
        return _classification_dict("yes", "housing", proto, sub_modes_str, sol, st, rng, conf, meth)

    if sqft < 2500:
        cat = "guard_tower_utility"
    elif sqft < 8000 and (p50v is not None and p50v < 15.0):
        cat = "support_warehouse_pia"
    else:
        cat = "program_admin_medical"

    st, rng, conf, meth = derive_non_housing_stories(p25v, p50v, p90v, modes, sqft, triage)
    return _classification_dict("no", cat, "non_housing", sub_modes_str, sol, st, rng, conf, meth)


def apply_override(base: dict[str, str], ov: dict[str, Any]) -> dict[str, str]:
    """Apply curated fields from housing_overrides.json on top of rule-based classification."""
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


def render_housing_qa(
    code: str,
    inst_name: str,
    tif_path: Path | None,
    feats: list[dict[str, Any]],
    rows: list[dict[str, str]],
    spi_h_count: int,
) -> None:
    """Render annotated housing & story-count QA overlay onto the institution's 2024 NAIP image."""
    if tif_path is None or not tif_path.exists():
        return

    with rasterio.open(tif_path) as src:
        bounds = src.bounds
        to_src = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)

    img, _, _ = open_naip_rgb_canvas(tif_path, max_dim=2000)
    nw, nh = img.size
    draw = ImageDraw.Draw(img)
    font = load_font(12)
    hdr_font = load_font(15)

    def to_px(x_s: float, y_s: float) -> tuple[float, float]:
        return (
            (x_s - bounds.left) / (bounds.right - bounds.left) * nw,
            (bounds.top - y_s) / (bounds.top - bounds.bottom) * nh,
        )

    by_id = {r["footprint_id"]: r for r in rows}
    story_colors = {
        "1": (0, 225, 255),
        "2": (255, 195, 0),
        "3": (255, 80, 220),
        "4": (255, 60, 60),
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
            col, width = (220, 40, 40), 1
        elif r["building_category"] == "guard_tower_utility":
            col, width = (150, 150, 150), 1
        elif r["building_category"] == "canopy":
            col, width = (130, 220, 190), 2
        else:
            col, width = (100, 230, 110), 2

        polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
        for p in polys:
            xs, ys = p.exterior.coords.xy
            tx, ty = to_src.transform(list(xs), list(ys))
            draw.line([to_px(x, y) for x, y in zip(tx, ty)], fill=col, width=width)

        sqft = fnum(r["footprint_sqft"], 0.0)
        if is_h or sqft >= 4000:
            c = geom.centroid
            cx, cy = to_src.transform(c.x, c.y)
            px, py = to_px(cx, cy)
            short_id = fid.replace(f"{code}-fp-", "").replace(f"{code}-", "")
            if is_h:
                rng = r["stories_range"] or r["stories"] or "?"
                lbl = f"H:{short_id} [{rng}s {r['roof_p50_ft'] or '-'}/{r['roof_p90_ft'] or '-'}]"
            elif triage == "demolished_or_pad":
                lbl = f"X:{short_id}"
            else:
                lbl = f"{short_id} ({r['stories']}s {r['roof_p50_ft'] or '-'})"
            draw.text((px - 22, py - 6), lbl, fill=(0, 0, 0), font=font)
            draw.text((px - 23, py - 7), lbl, fill=col, font=font)

    draw.rectangle([(0, 0), (nw, 30)], fill=(15, 18, 22))
    banner = (
        f"{code} ({inst_name}) | Housing={h_cnt} (SPI_dorm={spi_h_count}) | "
        f"Cyan=1s Gold=2s Mag=3s Red=4-5s Green=NonH-Bldg"
    )
    draw.text((10, 7), banner, fill=(240, 245, 250), font=hdr_font)
    img.save(HOUSING_QA_DIR / f"{code}_housing_qa.png")


def run_classify(qa_png: bool = False, codes: list[str] | None = None) -> None:
    """Classify housing/stories across all 34 institutions and write {CODE}_classified.csv."""
    HOUSING_QA_DIR.mkdir(parents=True, exist_ok=True)
    with open(ALL34_DIR / "all_34_summary.csv") as f:
        summary_rows = {r["cdcr_code"]: r for r in csv.DictReader(f)}
    with open(ROOT / "crosswalk" / "institutions.csv") as f:
        inst_names = {r["cdcr_code"]: r["institution_name"] for r in csv.DictReader(f)}
    with open(HOUSING_QA_DIR / "building_features.csv") as f:
        feat_rows = {r["footprint_id"]: r for r in csv.DictReader(f)}

    overrides: dict[str, Any] = {}
    if HOUSING_OVERRIDES_PATH.exists():
        raw_ov = json.loads(HOUSING_OVERRIDES_PATH.read_text())
        overrides = raw_ov.get("overrides", raw_ov) if isinstance(raw_ov, dict) else {}

    spi_dorm_cnt: collections.Counter[str] = collections.Counter()
    with open(DATA_BUILDINGS / "spi_cdcr_structures.csv") as f:
        for r in csv.DictReader(f):
            if r["structure_type"] in {"DORMITORY", "RELOCATABLE DORMITORY"}:
                spi_dorm_cnt[r["cdcr_code"]] += 1

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
    audit_rows: list[dict[str, Any]] = []

    for code in sorted(summary_rows):
        with open(HT_DIR / f"{code}_triaged.csv") as f:
            reader = csv.DictReader(f)
            base_cols = list(reader.fieldnames or [])
            rows = list(reader)

        out_cols = list(base_cols) + [c for c in new_cols if c not in base_cols]
        out_rows: list[dict[str, str]] = []
        story_hist: collections.Counter[str] = collections.Counter()
        proto_hist: collections.Counter[str] = collections.Counter()
        h_standing = non_h_standing = indet = 0

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

        with open(HT_DIR / f"{code}_classified.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=out_cols)
            w.writeheader()
            w.writerows(out_rows)

        if qa_png and (not codes or code in codes):
            feats = json.loads((FP_DIR / f"{code}_reconciled.geojson").read_text())["features"]
            tif_candidate = NAIP_DIR / f"{code}_naip_2024.tif"
            render_housing_qa(
                code, inst_names.get(code, code),
                tif_candidate if tif_candidate.exists() else None,
                feats, out_rows, spi_dorm_cnt.get(code, 0),
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
            f"1s={story_hist.get('1', 0):2d} 2s={story_hist.get('2', 0):2d} "
            f"3+s={story_hist.get('3', 0) + story_hist.get('4', 0) + story_hist.get('5', 0):2d} "
            f"non_h={non_h_standing:2d}",
            flush=True,
        )

    with open(HOUSING_QA_DIR / "housing_audit_summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(audit_rows[0].keys()))
        w.writeheader()
        w.writerows(audit_rows)
    print(f"Classified {len(audit_rows)} institutions into {HT_DIR.relative_to(ROOT)}/*_classified.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify housing prototypes, categories, and story counts.")
    parser.add_argument("--qa-png", action="store_true", help="Render per-institution housing QA overlay PNGs")
    parser.add_argument("--codes", nargs="*", help="Optional subset of institution codes for QA rendering")
    args = parser.parse_args()
    run_classify(qa_png=args.qa_png, codes=args.codes)


if __name__ == "__main__":
    main()
