#!/usr/bin/env python3
"""
Build the building inventory from building mentions.

Reads sources/building_mentions.csv (one row per place a source names a
specific building or housing unit) and collapses it to one row per building.

Output: crosswalk/buildings.csv
  Columns: building_key, cdcr_code, building, building_name, facility, use,
           program, conflicts, n_sources, sources

`building_key` is `{cdcr_code}-{building}`, or `{cdcr_code}-{name-slug}` for
buildings the sources name but don't number. Mentions are only merged when
they share a key; a numbered building and a named one are kept apart until a
source gives both on the same row.

`facility`, `use` and `program` list every distinct value the sources state,
separated by semicolons. `conflicts` names the columns where sources disagree.
"""

import re
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MENTIONS = ROOT / "sources" / "building_mentions.csv"
OUT = ROOT / "crosswalk" / "buildings.csv"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def building_key(row) -> str:
    if row["building"]:
        return f"{row['cdcr_code']}-{row['building']}"
    return f"{row['cdcr_code']}-{slug(row['building_name'])}"


def joined(values) -> str:
    return ";".join(dict.fromkeys(v for v in values if v))


def main():
    m = pd.read_csv(MENTIONS, dtype=str).fillna("")
    m["building_key"] = m.apply(building_key, axis=1)
    rows = []
    for key, g in m.groupby("building_key", sort=True):
        row = {
            "building_key": key,
            "cdcr_code": g["cdcr_code"].iloc[0],
            "building": g["building"].iloc[0],
            "building_name": joined(g["building_name"]),
            "facility": joined(g["facility"]),
            "use": joined(g["use"]),
            "program": joined(g["program"]),
        }
        row["conflicts"] = ";".join(c for c in ("facility", "use") if ";" in row[c])
        row["n_sources"] = g["source"].nunique()
        row["sources"] = joined(g["source"])
        rows.append(row)
    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)
    print(f"Wrote {len(out)} buildings ({(out.conflicts != '').sum()} with conflicts) to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
