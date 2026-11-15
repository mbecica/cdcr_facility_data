"""Write the raw heat-log scan outputs from the scan's working table.

Input (gitignored): notes/heat_log_scan/readings.csv, adjudications.csv, transcripts/.
Output: OUT/{log_type}/raw/{cdcr_code}.csv, pages.csv and coverage.csv per log type
(OUT defaults to data/heat/heat_plan_2024).

Raw means as transcribed and adjudicated, nothing cleaned. Rows left out:
struck cells and every cell on a struck day (never published), and copies the
scan's build already dropped (struck copies with an unstruck twin, days dated in
another scanned month's package, byte-identical rescans).

    python3 scrapers/build_heat_log_raw.py [OUT_DIR]
"""
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCAN = REPO / "notes" / "heat_log_scan"

# A/C outage logs: CMF "A/C Down Log" (Attachment C-2) pages and the CIW CTC
# room lines written during a central A/C failure (layouts.md).
AC_PAGES = {("CMF_MSR_0724", p) for p in (27, 28, 29, 30, 119, 120, 121, 122, 123, 158, 159, 160)}
AC_ROWS = {("CIW_MSR_0824", 106)}  # only the room lines (unit names a room)

FORM = {"2031": "cdcr_2031"}  # other form codes are published as they are

READ_BASIS = {
    "second read agrees": "two_reads_agree",
    "pair agrees": "two_reads_agree",
    "pair agrees, one unsure": "two_reads_agree",
    "Claude read, pair agrees": "two_reads_agree",
    "pair agrees, Claude checked": "two_reads_agree",
    "pair disputed, Claude decided": "dispute_decided",
    "Claude read": "single_read",
    "single read": "single_read",
    "adjudicated": "adjudicated",
    "adjudicated by context": "adjudicated_by_context",
}

# value_label: which of several values written for one place and time this row is.
# CRC zone logs label two thermometers on the page (WALL/HAND, each sometimes twice);
# where a cell holds two values the page doesn't explain (WSP CTC "72/72"), the
# transcript splits them into "(first value)"/"(second value)" lines -> value_1/value_2.
# Choosing between them is left to the cleaned layer.
# Two reads gave the same number but a reader marked it unsure ("74?"): published as clear
# with read_basis two_reads_agree_after_doubt (user, Nov 15 2026), below 88 only; cells at
# 88 and above keep the ? until the tens digit is checked (QA threshold gate).
AGREED = {"second read agrees", "pair agrees", "pair agrees, one unsure", "Claude read, pair agrees",
          "pair agrees, Claude checked"}
DOUBT_MAX = 88

THERMOMETER = {"WALL": "wall", "WALL2": "wall_2", "HAND": "hand", "HAND2": "hand_2"}
VALUE_SUFFIX = re.compile(r"\s*\((first|second) value\)\s*$", re.I)

COLUMNS = ["package", "page", "cdcr_code", "housing_unit_as_written", "form", "day",
           "date_as_written", "date", "date_source", "time", "value_label",
           "temp_as_written", "temp_f", "status", "alt_f", "read_basis"]


def package(source_file):
    return re.sub(r"(_Redacted)?(_R)?\.pdf$", "", source_file)


def num(v):
    """70.0 -> 70 (alt_f has no as-written form)."""
    f = float(v)
    return str(int(f)) if f == int(f) else v


def temp_out(row):
    t = row["temp_f"]
    if t == "":
        return ""
    w = row["temp_as_written"]
    # keep the writer's decimals (72.0 written as 72.0); drop the build's .0 otherwise
    if re.search(r"\d\.\d", w):
        return t
    f = float(t)
    return str(int(f)) if f == int(f) else t


def unit_fixes():
    """Unit strings that carry a reader's note -> the text as written (unit_string_notes.csv)."""
    with open(SCAN / "unit_string_notes.csv", newline="") as f:
        return {(r["cdcr_code"], r["unit_as_transcribed"]): r["housing_unit_as_written"] for r in csv.DictReader(f)}


def unit_page_fixes():
    """Pages whose unit string was misread, checked against the page image (unit_string_page_fixes.csv)."""
    p = SCAN / "unit_string_page_fixes.csv"
    if not p.exists():
        return {}
    with open(p, newline="") as f:
        return {(r["source_file"], int(r["page"]), r["unit_as_transcribed"]): r["housing_unit_as_written"]
                for r in csv.DictReader(f)}


def multi_value_cells():
    """Cells holding several values the page doesn't explain (multi_value_cells.csv, checked on the
    page image): (package, page, day, time) -> values in written order. Each value becomes a row."""
    p = SCAN / "multi_value_cells.csv"
    if not p.exists():
        return {}
    with open(p, newline="") as f:
        return {(r["package"], int(r["page"]), r["day"], r["time"]): r["values_in_order"].split(";")
                for r in csv.DictReader(f)}


def value_cell(v):
    """One written value -> (temp_f, status): '74' clear, '74?' unsure, '7?' (a digit missing) illegible."""
    v = v.strip()
    m = re.fullmatch(r"(\d\d+(?:\.\d+)?)(\?)?", v)
    if not m:
        return "", "illegible"
    f = float(m.group(1))
    temp = m.group(1) if "." in m.group(1) else str(int(f))
    return temp, "unsure" if m.group(2) else "clear"


def researcher_cells():
    """Cells whose last adjudication row is the researcher's own decision."""
    last = {}
    with open(SCAN / "adjudications.csv", newline="") as f:
        for a in csv.DictReader(f):
            if a["time"] in ("date", "unit"):
                continue
            last[(a["pkg"], a["page"], a["day"], a["time"], a.get("unit") or "")] = a["reason"]
    return {k for k, r in last.items() if r.startswith("user")}


def skip_pages():
    """Pages the scan read and set aside: (package, page) -> reason."""
    out = {}
    for t in sorted((SCAN / "transcripts").glob("*.txt")):
        pkg = t.name.split("__")[0]
        for line in t.open():
            m = re.match(r"@p (\d+) \|.*\| skip (.*)", line.strip()) or re.match(r"@p (\d+) \| skip (.*)", line.strip())
            if m:
                out[(pkg, int(m.group(1)))] = m.group(2).strip()
    return out


def skip_kind(reason):
    m = re.search(r"duplicate scan of p(\d+)", reason)
    if m:
        return "duplicate_scan", m.group(1)
    return "no_inside_readings", ""


def main(out_dir):
    out = Path(out_dir)
    user = researcher_cells()
    ufix = unit_fixes()
    pfix = unit_page_fixes()
    multi = multi_value_cells()
    printed = defaultdict(set)  # (package, page, date, day as published) -> printed weekdays
    with open(SCAN / "date_fixes.csv", newline="") as f:
        for fx in csv.DictReader(f):
            if fx.get("day_fixed"):
                printed[(fx["pkg"], fx["page"], fx["date"], fx["day_fixed"])].add(fx["day"])
    rows_by = defaultdict(list)          # (log_type, cdcr) -> rows
    pages = defaultdict(lambda: {"units": Counter(), "forms": Counter(), "dates": set(), "n": 0, "cells": 0})
    dropped = Counter()
    for r in csv.DictReader(open(SCAN / "readings.csv", newline="")):
        pkg = package(r["source_file"])
        page = int(r["page"])
        if r["status"] == "struck" or r["day_struck"] == "yes":
            dropped["struck"] += 1
            continue
        unit = pfix.get((r["source_file"], page, r["housing_unit_as_written"]))
        if unit is None:
            unit = ufix.get((r["cdcr_code"], r["housing_unit_as_written"]), r["housing_unit_as_written"])
        label = ""
        m = VALUE_SUFFIX.search(unit)
        if m:
            unit = unit[:m.start()]
            label = "value_1" if m.group(1).lower() == "first" else "value_2"
        lt = "indoor"
        if (pkg, page) in AC_PAGES or ((pkg, page) in AC_ROWS and "room" in r["housing_unit_as_written"].lower()):
            lt = "ac_outage"
        t = r["time"]
        if t in THERMOMETER:
            label, t = THERMOMETER[t], ""
        basis = READ_BASIS.get(r["check"], r["check"])
        # adjudications use the printed weekday; a relabelled block has its written weekday in `day`
        for d in {r["day"]} | printed.get((pkg, r["page"], r["date"], r["day"]), set()):
            for u in ("", r["housing_unit_as_written"]):  # adjudications name a unit only on override lines
                if (pkg, r["page"], d, r["time"], u) in user:
                    basis = "researcher_review"
        o = {
            "package": pkg, "page": page, "cdcr_code": r["cdcr_code"],
            "housing_unit_as_written": unit,
            "form": FORM.get(r["form"], r["form"]), "day": r["day"],
            "date_as_written": r["date_as_written"], "date": r["date"],
            "date_source": r["date_check"] or ("written" if r["date"] else ""),
            "time": t, "value_label": label,
            "temp_as_written": r["temp_as_written"], "temp_f": temp_out(r),
            "status": r["status"], "alt_f": num(r["alt_f"]) if r["alt_f"] else "",
            "read_basis": basis if r["temp_f"] != "" else "",
        }
        if (r["status"] == "unsure" and r["check"] in AGREED and basis == "two_reads_agree"
                and o["temp_f"] != "" and float(o["temp_f"]) < DOUBT_MAX):
            o.update(status="clear", temp_as_written=o["temp_as_written"].replace("?", ""),
                     read_basis="two_reads_agree_after_doubt")
        vals = multi.get((pkg, page, r["day"], r["time"])) if not r["housing_unit_as_written"].endswith("value)") else None
        if vals:
            for i, v in enumerate(vals, 1):
                temp, status = value_cell(v)
                rows_by[(lt, r["cdcr_code"])].append(dict(o, value_label=f"value_{i}", temp_as_written=v.strip(),
                                                          temp_f=temp, status=status, alt_f="",
                                                          read_basis="single_read" if temp else ""))
        else:
            rows_by[(lt, r["cdcr_code"])].append(o)
        p = pages[(lt, pkg, page)]
        p["units"][unit] += 1
        p["forms"][o["form"]] += 1
        p["cells"] += 1
        if r["temp_f"] != "":
            p["n"] += 1
        if r["date"]:
            p["dates"].add(r["date"])

    for (lt, cdcr), rows in sorted(rows_by.items()):
        d = out / lt / "raw"
        d.mkdir(parents=True, exist_ok=True)
        rows.sort(key=lambda o: (o["package"], o["page"], o["date"] or "9", o["housing_unit_as_written"], o["time"]))
        with open(d / f"{cdcr}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, COLUMNS)
            w.writeheader()
            w.writerows(rows)

    skips = skip_pages()
    for lt in sorted({k[0] for k in pages}):
        with open(out / lt / "pages.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["package", "page", "cdcr_code", "form", "housing_units_as_written", "first_date",
                        "last_date", "cells", "readings", "set_aside", "duplicate_of_page"])
            keys = [k for k in pages if k[0] == lt]
            if lt == "indoor":
                keys += [("indoor", pkg, pg) for (pkg, pg) in skips if ("indoor", pkg, pg) not in pages
                         and ("ac_outage", pkg, pg) not in pages]
            for k in sorted(set(keys), key=lambda k: (k[1], k[2])):
                _, pkg, pg = k
                if k in pages:
                    p = pages[k]
                    ds = sorted(p["dates"])
                    w.writerow([pkg, pg, pkg.split("_")[0], ";".join(p["forms"]), "; ".join(p["units"]),
                                ds[0] if ds else "", ds[-1] if ds else "", p["cells"], p["n"], "", ""])
                else:
                    kind, dup = skip_kind(skips[(pkg, pg)])
                    w.writerow([pkg, pg, pkg.split("_")[0], "", "", "", "", 0, 0, kind, dup])

    cov = defaultdict(lambda: [set(), set(), 0])
    for (lt, cdcr), rows in rows_by.items():
        for o in rows:
            if o["temp_f"] == "":
                continue
            c = cov[(lt, cdcr, o["date"][:7] or "undated")]
            c[0].add((o["package"], o["page"]))
            c[1].add((o["housing_unit_as_written"], o["date"]))
            c[2] += 1
    for lt in sorted({k[0] for k in cov}):
        with open(out / lt / "coverage.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["cdcr_code", "month", "pages", "unit_days", "readings"])
            for k in sorted(k for k in cov if k[0] == lt):
                w.writerow([*k[1:], len(cov[k][0]), len(cov[k][1]), cov[k][2]])

    total = sum(len(v) for v in rows_by.values())
    print(f"{total} rows written ({dropped['struck']} struck cells left out)")
    for lt in sorted({k[0] for k in rows_by}):
        n = sum(len(v) for k, v in rows_by.items() if k[0] == lt)
        print(f"  {lt}: {n} rows, {len({k[1] for k in rows_by if k[0] == lt})} prisons")
    print(f"  pages set aside: {len(skips)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else REPO / "data" / "heat" / "heat_plan_2024")
