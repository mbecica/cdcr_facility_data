#!/usr/bin/env python3
"""
Step 2C: 0-Roof Classification, Boundary/Grounds Triage, and Facility Roof QA Cross-check.

1. Generates visual contact sheets of all zero_roof_flag==yes polygons inside RAPT
   on 2024 NAIP imagery so every active-prison 0-roof polygon can be verified visually.
2. Classifies triage_status (valid_standing, demolished_or_pad, solar_carport_or_array,
   new_post_lidar_bldg), honoring any visual overrides in all_34/step2c_triage_overrides.json.
3. Adds join-safe columns: perimeter_status, is_closed_facility, broad building_category,
   and facility-level MPAR/condition roof QA metadata.
4. Writes {CODE}_triaged.csv alongside {CODE}_reconciled.csv and summary reports.
"""

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image, ImageDraw
from rasterio.features import rasterize
from rasterio.windows import from_bounds
from shapely.geometry import shape

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parents[1]
WORK_DIR = ROOT / "notes" / "building_heights_pilot"
OUT_ROOT = WORK_DIR / "all_34"
FP_DIR = OUT_ROOT / "footprints"
HT_DIR = OUT_ROOT / "heights"
TRIAGE_DIR = OUT_ROOT / "step2c_triage"
NAIP_DIR = ROOT / "sources" / "imagery" / "naip_2024"
TRIAGE_DIR.mkdir(parents=True, exist_ok=True)

CLOSED_CODES = {"CAC", "CVSP", "FWF"}
OVERRIDES_PATH = SCRIPTS_DIR / "triage_overrides.json"


def load_facility_roof_qa() -> dict[str, dict]:
    insts = list(csv.DictReader(open(ROOT / "crosswalk" / "institutions.csv")))
    aliases_by_code = {}
    for r in insts:
        c = r["cdcr_code"]
        aliases_by_code[c] = [c] + [a.strip() for a in (r.get("alias_codes") or "").split(";") if a.strip()]

    cond_by_inst = {}
    for r in csv.DictReader(open(ROOT / "data" / "buildings" / "condition_assessment_2026.csv")):
        if r["system"] == "Roofs":
            cond_by_inst[r["institution"]] = r["rating"]

    env_by_inst = {}
    for r in csv.DictReader(open(ROOT / "data" / "buildings" / "mpar_envelope_last_completed.csv")):
        env_by_inst[r["institution"]] = r

    mpar_roofs_by_inst: dict[str, list[dict]] = {}
    for r in csv.DictReader(open(ROOT / "data" / "buildings" / "mpar_projects.csv")):
        txt = (r["title"] + " " + r["scope"]).lower()
        if "roof" in txt:
            mpar_roofs_by_inst.setdefault(r["institution"], []).append(r)

    mentions_roof_by_code: dict[str, int] = {}
    for r in csv.DictReader(open(ROOT / "data" / "buildings" / "building_mentions.csv")):
        if "roof" in (r["quote"] or "").lower():
            mentions_roof_by_code[r["cdcr_code"]] = mentions_roof_by_code.get(r["cdcr_code"], 0) + 1

    sum_by_code = {r["cdcr_code"]: r for r in csv.DictReader(open(OUT_ROOT / "all_34_summary.csv"))}

    qa = {}
    for c, aliases in aliases_by_code.items():
        cond = next((cond_by_inst[a] for a in aliases if a in cond_by_inst), "")
        env = next((env_by_inst[a] for a in aliases if a in env_by_inst), {})
        last_yr = env.get("last_envelope_year", "")
        last_pid = env.get("project_id", "")

        mpar_rows = []
        for a in aliases:
            mpar_rows.extend(mpar_roofs_by_inst.get(a, []))
        active_pids = sorted({r["project_id"] for r in mpar_rows if r["status"] in ("active", "complete") and "roof" in (r["title"]).lower()})
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


def sample_naip_stats(src, geom) -> tuple[float, float, float, float, float, float, float]:
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
    b_minus_r = b - r
    return round(r, 1), round(g, 1), round(b, 1), round(n, 1), round(ndvi, 3), round(bright, 1), round(b_minus_r, 1)


def render_zero_roof_contact_sheets(zero_items: list[dict]) -> None:
    """Render contact sheets of all zero-roof RAPT polygons (180x180 px crop each) for visual QA."""
    if not zero_items:
        return
    cols, cell_w, cell_h = 6, 220, 235
    per_page = 30
    for page_idx in range(0, len(zero_items), per_page):
        batch = zero_items[page_idx : page_idx + per_page]
        nrows = math.ceil(len(batch) / cols)
        sheet = Image.new("RGB", (cols * cell_w, nrows * cell_h), (20, 20, 20))
        draw = ImageDraw.Draw(sheet)

        for i, item in enumerate(batch):
            r_idx, c_idx = divmod(i, cols)
            x0, y0 = c_idx * cell_w, r_idx * cell_h
            tif_path = item["tif_path"]
            geom = item["geom"]
            cx, cy = geom.centroid.x, geom.centroid.y
            # ~90m x 90m window (~0.0009 deg)
            minx, miny, maxx, maxy = geom.bounds
            pad = max(0.00035, (maxx - minx) * 0.8, (maxy - miny) * 0.8)
            wx0, wy0, wx1, wy1 = cx - pad, cy - pad, cx + pad, cy + pad
            with rasterio.open(tif_path) as src:
                win = from_bounds(wx0, wy0, wx1, wy1, src.transform)
                arr = src.read([1, 2, 3], window=win, boundless=True, fill_value=0)
                w_tr = src.window_transform(win)
                crop = Image.fromarray(np.transpose(arr, (1, 2, 0)), mode="RGB").resize((210, 195), Image.Resampling.BILINEAR)
                cdraw = ImageDraw.Draw(crop)
                sx = 210.0 / max(1, arr.shape[2])
                sy = 195.0 / max(1, arr.shape[1])
                geoms = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
                for poly in geoms:
                    pts = []
                    for lon, lat in poly.exterior.coords:
                        col_p, row_p = ~w_tr * (lon, lat)
                        pts.append((col_p * sx, row_p * sy))
                    if len(pts) >= 2:
                        cdraw.line(pts, fill=(255, 60, 60), width=2)
            sheet.paste(crop, (x0 + 5, y0 + 5))
            lbl1 = f"{item['fid']} ({item['sqft']:.0f}sf)"
            lbl2 = f"pts={item['pts']} {item['status'][:14]}"
            draw.text((x0 + 6, y0 + 202), lbl1, fill=(255, 255, 255))
            draw.text((x0 + 6, y0 + 216), lbl2, fill=(255, 210, 100))

        out_png = TRIAGE_DIR / f"zero_roof_sheet_{page_idx // per_page + 1}.png"
        sheet.save(out_png)
        print(f"Saved {out_png} ({len(batch)} polygons)")


def run_triage(render_sheets: bool = True):
    overrides = json.loads(OVERRIDES_PATH.read_text()) if OVERRIDES_PATH.exists() else {}
    roof_qa = load_facility_roof_qa()
    insts = list(csv.DictReader(open(ROOT / "crosswalk" / "institutions.csv")))

    zero_items_for_sheets = []
    triage_summary_rows = []
    zero_detail_rows = []

    for inst in insts:
        code = inst["cdcr_code"]
        is_closed = "yes" if code in CLOSED_CODES else "no"
        rec_gj = FP_DIR / f"{code}_reconciled.geojson"
        rec_csv = HT_DIR / f"{code}_reconciled.csv"
        feats = json.loads(rec_gj.read_text())["features"]
        geom_by_fid = {f["properties"]["footprint_id"]: shape(f["geometry"]) for f in feats}
        rows = list(csv.DictReader(open(rec_csv)))
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
                other_code = r.get("other_rapt_code", "")
                if in_rapt:
                    perim = "inside_fence_rapt"
                elif other_code:
                    perim = "adjacent_prison_rapt"
                else:
                    perim = "buffer_300m_outside"

                pts_in = int(r["pts_inside"] or 0)
                sqft = float(r["footprint_sqft"] or 0)
                zero_flag = r["zero_roof_flag"] == "yes"

                triage_status = "valid_standing"
                triage_note = ""
                if not in_rapt:
                    triage_status = "outside_rapt_unverified" if zero_flag else "valid_standing"
                    counts[perim] += 1
                elif not zero_flag:
                    triage_status = "valid_standing"
                    counts["inside_valid_standing"] += 1
                else:
                    # Zero-roof inside RAPT: check overrides, LiDAR void, NAIP spectral signature
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
                        "code": code,
                        "fid": fid,
                        "sqft": sqft,
                        "pts": pts_in,
                        "status": triage_status,
                        "geom": g,
                        "tif_path": tif_path,
                    })

                # Preliminary broad category (Step 2D refines housing/program/support/utility)
                if perim != "inside_fence_rapt":
                    bcat = "buffer_unclassified"
                elif triage_status == "demolished_or_pad":
                    bcat = "demolished_or_pad"
                elif triage_status == "solar_carport_or_array":
                    bcat = "solar_array"
                else:
                    bcat = "standing_unclassified"

                r2 = dict(r)
                r2["perimeter_status"] = perim
                r2["is_closed_facility"] = is_closed
                r2["triage_status"] = triage_status
                r2["triage_note"] = triage_note
                r2["building_category"] = bcat
                r2["cond_roofs_2026"] = fqa["cond_roofs_2026"]
                r2["mpar_last_roof_year"] = fqa["mpar_last_roof_year"]
                r2["post_lidar_roof_project_flag"] = fqa["post_lidar_roof_project_flag"]
                triaged_rows.append(r2)

        out_csv = HT_DIR / f"{code}_triaged.csv"
        with open(out_csv, "w", newline="") as fp:
            w = csv.DictWriter(fp, fieldnames=list(triaged_rows[0].keys()))
            w.writeheader()
            w.writerows(triaged_rows)

        triage_summary_rows.append({
            "cdcr_code": code,
            "is_closed_facility": is_closed,
            **counts,
            **fqa,
        })

    with open(TRIAGE_DIR / "zero_roof_triage_detail.csv", "w", newline="") as fp:
        if zero_detail_rows:
            w = csv.DictWriter(fp, fieldnames=list(zero_detail_rows[0].keys()))
            w.writeheader()
            w.writerows(zero_detail_rows)

    with open(TRIAGE_DIR / "facility_triage_and_roof_qa.csv", "w", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=list(triage_summary_rows[0].keys()))
        w.writeheader()
        w.writerows(triage_summary_rows)

    if render_sheets:
        render_zero_roof_contact_sheets(zero_items_for_sheets)

    tot_in = sum(
        r["inside_valid_standing"] + r["inside_demolished_or_pad"] + r["inside_solar_carport_or_array"] + r["inside_new_post_lidar_bldg"]
        for r in triage_summary_rows
    )
    print(f"Triaged {len(triage_summary_rows)} prisons: in_RAPT={tot_in}, zero_roof_in_RAPT={len(zero_detail_rows)}")
    for k in ("inside_valid_standing", "inside_demolished_or_pad", "inside_solar_carport_or_array", "inside_new_post_lidar_bldg", "buffer_300m_outside", "adjacent_prison_rapt"):
        print(f"  {k}: {sum(r[k] for r in triage_summary_rows)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-sheets", action="store_true")
    args = parser.parse_args()
    run_triage(render_sheets=not args.no_sheets)
