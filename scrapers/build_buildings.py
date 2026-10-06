#!/usr/bin/env python3
"""
Build the building inventory from the state property inventory and building
mentions.

Reads:
  sources/spi_cdcr_structures.csv  every CDCR structure in the DGS Statewide
                                   Property Inventory (scrapers/fetch_spi_structures.py)
  sources/building_mentions.csv    one row per place another source names a
                                   specific building or housing unit

Output: crosswalk/buildings.csv
  Columns: building_key, cdcr_code, building, building_name, aliases,
           placeholder, facility, use, program, year_built, sqft,
           spi_structure_type, spi_structure_number, spi_agency_structure_no,
           spi_real_property_number, conflicts, n_sources, sources

Keys:
  - `{cdcr_code}-{building}` for a numbered building. SPI building numbers come
    from `agency_structure_no` with prefixes such as "BLDG." or "SQ-B-" removed,
    or from the structure name ("BLDG 321 - 270 HOUSING"). Five-digit DGS serial
    numbers (e.g. 14598) are not CDCR numbers and are ignored. A structure SPI
    describes as two housing units ("FACILITY A HOUSING BUILDING #1 & 2",
    "A1 AND A2 HOUSING UNITS") is building "A1/A2". A number shared by several
    SPI structures stays with the one housing structure among them, if there
    is exactly one.
  - `{cdcr_code}-spi{structure_number}` for an SPI structure with no usable
    number, or whose number is shared and can't be assigned.
  - `{cdcr_code}-{name-slug}` for a building other sources name but don't number.
  - `{cdcr_code}-ph-{placeholder_id}` for placeholders: one per building a source
    counts without naming (e.g. "all eight of Facility A's housing units").
    These are this project's identifiers, not CDCR's, and `placeholder` is `yes`.

A mention joins an SPI structure when its building number matches (ignoring
hyphens, spaces and leading zeros), when it matches the housing unit SPI names
on the same row (LAC "3410 | HOUSING UNIT D-5" takes mentions of "D5"), or when
its name matches an SPI structure name that is unique at the institution.
Otherwise mentions merge only when they share a key. The IDs a building was
mentioned under are kept in `aliases`.

`facility`, `use`, `program` and `year_built` list every distinct value the
sources state, separated by semicolons. `use` comes from mentions only; SPI's
own category is in `spi_structure_type`. SPI identifiers are kept as entered:
`spi_structure_number` (DGS's structure ID), `spi_agency_structure_no` (the
agency's number, before prefixes are removed, including DGS serial numbers and
notes), and `spi_real_property_number` (DGS's ID for the property). `conflicts` names the columns where
sources disagree.
"""

import re
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPI = ROOT / "sources" / "spi_cdcr_structures.csv"
MENTIONS = ROOT / "sources" / "building_mentions.csv"
OUT = ROOT / "crosswalk" / "buildings.csv"

DGS_SERIAL = re.compile(r"^\d{5}(-[A-Z])?$")
ID = r"\d[A-Z]\d{1,2}[A-Z]?|[A-Z]?\d+[A-Z]{0,2}(?:\.\d+)?"
# Structures holding two housing units, e.g. SAC "FACILITY A HOUSING BUILDING #1 & 2"
# and PBSP "A1 AND A2 HOUSING UNITS", become building "A1/A2".
PAIRS = (
    re.compile(r"FACILITY ([A-Z]) HOUSING BUILDING\s*#\s*(\d+)\s*&\s*(\d+)"),
    re.compile(r"^([A-Z])(\d+) AND [A-Z]?(\d+) HOUSING UNITS"),
)


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def canon(x: str) -> str:
    """Comparison form of a building ID: no hyphens or spaces, no leading zeros."""
    x = re.sub(r"[\s-]", "", x.upper())
    return re.sub(r"(?<!\d)0+(?=\d)", "", x)


def spi_number(asn: str, name: str) -> str:
    for pat in PAIRS:
        if m := pat.search(name.upper()):
            f, x, y = m.groups()
            return f"{f}{x}/{f}{y}"
    a = re.sub(r"^KITCHELL-?\s*", "", asn.upper().strip())
    a = re.sub(r"\s*BLDG\.?$", "", a)
    a = re.sub(r"^(BLDG\.?|BUILDING\s*(NO\.?)?\s*#?|SQ-B-)\s*", "", a).strip()
    a = re.sub(r"^(\d+)\s+([A-Z])$", r"\1\2", a)  # "405 A" -> 405A
    if m := re.match(r"^(" + ID + r")\s{2,}\S", a):  # "507     BID PACKAGE 5" -> 507
        a = m.group(1)
    if a and not DGS_SERIAL.match(a) and re.fullmatch(ID, a):
        return a
    m = re.search(r"\b(?:BLDG\.?|BUILDING(?:\s+NO\.)?)\s*#?\s*(" + ID + r")\b", name.upper())
    return m.group(1) if m else ""


def spi_units(name: str, building: str) -> str:
    """Housing units an SPI structure holds: "HOUSING UNIT C-7, C-8" -> C7;C8,
    "HOUSING UNIT 16" -> 16, building "A1/A2" -> A1;A2."""
    if "/" in building:
        return building.replace("/", ";")
    m = re.search(r"HOUSING UNIT\s+([A-Z]-?\d{1,2}(?:\s*,\s*[A-Z]-?\d{1,2})*)\b", name.upper())
    if m:
        return ";".join(canon(u) for u in m.group(1).split(","))
    m = re.search(r"HOUSING UNIT\s+(?:NO\.?\s*)?(\d{1,2})$", name.upper().strip())  # RJD "HOUSING UNIT 16"
    return m.group(1) if m else ""


def joined(values) -> str:
    return ";".join(dict.fromkeys(str(v) for v in values if v not in ("", None)))


def load_spi() -> pd.DataFrame:
    s = pd.read_csv(SPI, dtype=str).fillna("")
    s["building"] = [spi_number(a, n) for a, n in zip(s.agency_structure_no, s.structure_name)]
    s["unit"] = [spi_units(n, b) for n, b in zip(s.structure_name, s.building)]
    # A number shared by several structures stays with the one housing structure
    # among them (CEN 325 is Housing Unit A-5 and also its exercise yards); if
    # none or several are housing, no structure keeps it.
    grp = s[s.building != ""].groupby(["cdcr_code", "building"])
    size = grp.building.transform("size")
    n_dorm = grp.structure_type.transform(lambda t: (t == "DORMITORY").sum())
    drop = (size > 1) & ~((n_dorm == 1) & (s.loc[size.index, "structure_type"] == "DORMITORY"))
    s.loc[drop[drop].index, ["building", "unit"]] = ""
    s["building_key"] = [
        f"{c}-{b}" if b else f"{c}-spi{n}"
        for c, b, n in zip(s.cdcr_code, s.building, s.structure_number)
    ]
    return s


def lookups(s: pd.DataFrame) -> dict:
    """(cdcr_code, comparison form) -> SPI building key, for numbers, units, and unique names."""
    out = {}
    for c, b, k in zip(s.cdcr_code, s.building, s.building_key):
        if b:
            out[(c, canon(b))] = k
    units = s.assign(u=s.unit.str.split(";")).explode("u")
    units = units[units.u.fillna("") != ""]
    counts = units.groupby(["cdcr_code", "u"]).size()
    for c, u, k in zip(units.cdcr_code, units.u, units.building_key):
        if counts[(c, u)] == 1:
            out.setdefault((c, u), k)
    counts = s[s.structure_name != ""].groupby(["cdcr_code", "structure_name"]).size()
    for c, n, k in zip(s.cdcr_code, s.structure_name, s.building_key):
        if n and counts[(c, n)] == 1:
            out.setdefault((c, "NAME:" + slug(n)), k)
    return out


def mention_key(row, look: dict) -> str:
    c = row["cdcr_code"]
    if row["placeholder_id"]:
        return f"{c}-ph-{row['placeholder_id']}"
    if row["building"]:
        for part in [row["building"], *row["building"].split("/")]:
            if (c, canon(part)) in look:
                return look[(c, canon(part))]
        return f"{c}-{row['building']}"
    return look.get((c, "NAME:" + slug(row["building_name"])), f"{c}-{slug(row['building_name'])}")


def main():
    s = load_spi()
    look = lookups(s)
    m = pd.read_csv(MENTIONS, dtype=str).fillna("")
    m["building_key"] = m.apply(mention_key, axis=1, look=look)
    spi_rows = pd.DataFrame({
        "building_key": s.building_key, "cdcr_code": s.cdcr_code, "building": s.building,
        "building_name": s.structure_name.str.title(), "year_built": s.yr_built,
        "sqft": s.sqft, "spi_structure_type": s.structure_type,
        "spi_structure_number": s.structure_number,
        "spi_agency_structure_no": s.agency_structure_no,
        "spi_real_property_number": s.real_property_number, "source": "SPI",
    })
    allrows = pd.concat([spi_rows, m], ignore_index=True).fillna("")
    rows = []
    for key, g in allrows.groupby("building_key", sort=True):
        spi = g[g.source == "SPI"]
        ment = g[g.source != "SPI"]
        building = spi.building.iloc[0] if len(spi) else ment.building.iloc[0]
        row = {
            "building_key": key,
            "cdcr_code": g.cdcr_code.iloc[0],
            "building": building,
            "building_name": joined(g.building_name),
            "aliases": joined(b for b in ment.building if b and b != building),
            "placeholder": "yes" if ment.placeholder_id.any() else "",
            "facility": joined(ment.facility),
            "use": joined(ment.use),
            "program": joined(ment.program),
            "year_built": joined(g.year_built),
            "sqft": joined(spi.sqft),
            "spi_structure_type": joined(spi.spi_structure_type),
            "spi_structure_number": joined(spi.spi_structure_number),
            "spi_agency_structure_no": joined(spi.spi_agency_structure_no),
            "spi_real_property_number": joined(spi.spi_real_property_number),
        }
        row["conflicts"] = ";".join(c for c in ("facility", "use", "year_built") if ";" in row[c])
        row["n_sources"] = g.source.nunique()
        row["sources"] = joined(g.source)
        rows.append(row)
    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)
    linked = out[(out.sources.str.contains("SPI")) & (out.sources != "SPI")]
    print(f"Wrote {len(out)} buildings to {OUT.relative_to(ROOT)}: "
          f"{(out.sources == 'SPI').sum()} SPI only, {len(linked)} SPI plus other sources, "
          f"{(~out.sources.str.contains('SPI')).sum()} other sources only; "
          f"{(out.conflicts != '').sum()} with conflicts")


if __name__ == "__main__":
    main()
