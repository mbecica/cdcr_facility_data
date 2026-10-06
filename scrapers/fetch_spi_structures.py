#!/usr/bin/env python3
"""
Download every CDCR building from the DGS Statewide Property Inventory (SPI).

Queries the public SPI map service (Structure layer), which needs no login, and
keeps the structures at the adult institutions in crosswalk/institutions.csv
(plus the McGee training center, CTC). Youth facilities, closed or leased
facilities not in the crosswalk (CCC, DVI, NCRF), and statewide offices are
dropped.

Output: sources/spi_cdcr_structures.csv, one row per structure.
  Columns: cdcr_code, real_property_number, real_property_name,
  structure_number (DGS's ID), agency_structure_no (the agency's building
  number, as entered), structure_name, structure_type_code, structure_type,
  sqft, yr_built, data_date

All identifiers, numbers and names are kept exactly as SPI has them; matching them to
CDCR building numbers happens in scrapers/build_buildings.py.
"""

import json
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "sources" / "spi_cdcr_structures.csv"
URL = ("https://services8.arcgis.com/a4GMqC2tQHvYiVtK/arcgis/rest/services/"
       "SPIPublicMapViewer/FeatureServer/1/query")
PAGE = 2000

# SPI real property name -> CDCR code
PROPERTIES = {
    "AVENAL STATE PRISON": "ASP",
    "CALIFORNIA CORRECTIONAL INSTITUTION": "CCI",
    "CALIFORNIA INSTITUTION FOR MEN": "CIM",
    "CALIFORNIA INSTITUTION FOR WOMEN": "CIW",
    "CALIFORNIA MEDICAL FACILITY": "CMF",
    "CALIFORNIA MEN'S COLONY": "CMC",
    "CALIFORNIA REHABILITATION CENTER (AKA NORCO)": "CRC",
    "CALIF. SUBSTANCE ABUSE TREATMENT FAC. AND STATE PRISON": "SATF",
    "CALIPATRIA STATE PRISON": "CAL",
    "CENTINELA STATE PRISON": "CEN",
    "CENTRAL CALIFORNIA WOMEN'S FACILITY": "CCWF",
    "CHUCKAWALLA VALLEY STATE PRISON, RIVERSIDE CO.": "CVSP",
    "CORRECTIONAL TRAINING FACILITY": "CTF",
    "CSP, CORCORAN": "COR",
    "KERN VALLEY STATE PRISON": "KVSP",
    "CSP, LOS ANGELES": "LAC",
    "CSP, SACRAMENTO": "SAC",
    "CSP, SAN QUENTIN": "SQ",
    "CSP, SOLANO COUNTY": "SOL",
    "FOLSOM STATE PRISON": "FOL",
    "HIGH DESERT STATE PRISON": "HDSP",
    "IRONWOOD STATE PRISON": "ISP",
    "MULE CREEK STATE PRISON, IONE": "MCSP",
    "NORTH KERN STATE PRISON": "NKSP",
    "PELICAN BAY STATE PRISON": "PBSP",
    "PLEASANT VALLEY STATE PRISON": "PVSP",
    "R J DONOVAN CORR. FAC. AT ROCK MOUNTAIN": "RJD",
    "RICHARD A. MCGEE CORRECTIONAL TRAINING CENTER": "CTC",
    "SALINAS VALLEY STATE PRISON": "SVSP",
    "SIERRA CONSERVATION CENTER": "SCC",
    "VALLEY STATE PRISON": "VSP",
    "WASCO STATE PRISON RECEPTION CENTER": "WSP",
    "CALIFORNIA HEALTH CARE FACILITY": "CHCF",
}

FIELDS = {
    "Real_Property_Number": "real_property_number",
    "Real_Property_Name": "real_property_name",
    "Structure_Number": "structure_number",
    "Agency_Structure_No": "agency_structure_no",
    "Structure_Name": "structure_name",
    "Structure_Type_Code": "structure_type_code",
    "Structure_Type": "structure_type",
    "Qty_of_Unit": "sqft",
    "Yr_Built": "yr_built",
}


def fetch() -> list[dict]:
    rows, offset = [], 0
    where = "Agency LIKE 'CDCR%' OR Agency LIKE 'CORRECTIONS AND REHABILITATION%'"
    while True:
        params = urllib.parse.urlencode({
            "where": where, "outFields": ",".join(FIELDS) + ",Unit_Type",
            "orderByFields": "OBJECTID", "resultOffset": offset,
            "resultRecordCount": PAGE, "f": "json",
        })
        with urllib.request.urlopen(f"{URL}?{params}", timeout=60) as r:
            data = json.load(r)
        feats = [f["attributes"] for f in data.get("features", [])]
        rows.extend(feats)
        if len(feats) < PAGE:
            return rows
        offset += PAGE


def main():
    df = pd.DataFrame(fetch())
    if set(df["Unit_Type"].dropna()) != {"SQUARE FEET"}:
        raise ValueError(f"unexpected Unit_Type values: {set(df['Unit_Type'])}")
    df["Real_Property_Name"] = df["Real_Property_Name"].str.strip()
    df = df[df["Real_Property_Name"].isin(PROPERTIES)].rename(columns=FIELDS)
    df.insert(0, "cdcr_code", df["real_property_name"].map(PROPERTIES))
    for col in ("agency_structure_no", "structure_name"):
        df[col] = df[col].fillna("").str.strip()
    df["sqft"] = pd.to_numeric(df["sqft"], errors="coerce").astype("Int64")
    df["yr_built"] = pd.to_numeric(df["yr_built"], errors="coerce").astype("Int64")
    df["yr_built"] = df["yr_built"].where(df["yr_built"] > 0)
    df["data_date"] = date.today().isoformat()
    df = df[["cdcr_code", *FIELDS.values(), "data_date"]].sort_values(
        ["cdcr_code", "agency_structure_no", "structure_name", "structure_number"])
    df.to_csv(OUT, index=False)
    print(f"Wrote {len(df)} structures for {df.cdcr_code.nunique()} institutions to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
