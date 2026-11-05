#!/usr/bin/env python3
"""
Selected measures from the CCHCS Health Care Services Dashboard for every month it offers, read
through its query endpoint.

Output, one row per month, institution and measure with a published value:
  data/health_care/cchcs_ipc.csv        Institution & Population Characteristics
  data/health_care/cchcs_measures.csv   staffing, costs, and other trends

Refreshes add to the files. A new value replaces the old one, and a value the dashboard no longer
gives stays, such as ED/Hospital Stay*, which it no longer lists.

Usage:
  python3 scrapers/fetch_cchcs_tables.py
"""

import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from institution_codes import load_codes
from powerbi_query import Report, column, equals

ROOT = Path(__file__).resolve().parent.parent
IPC = ROOT / "data" / "health_care" / "cchcs_ipc.csv"
MEASURES = ROOT / "data" / "health_care" / "cchcs_measures.csv"

REPORT_R = "eyJrIjoiY2QyNzllZWItMmIxYi00NTk0LWI0OWQtNWEzMTkwYzA3NGE4IiwidCI6IjA2NjI0NzdkLWZhMGMtNDU1Ni1hOGY1LWMzYmM2MmFhMGQ5YyJ9"
SOURCES = {"d": "MeasureData", "i": "InstitutionDim", "l": "LKMeasureDim", "c": "DateDim"}

IPC_MEASURES = ["High Risk Priority 1", "High Risk Priority 2", "Medium Risk", "Low Risk",
                "Mental Health EOP", "Disability Placement Program (DPP) Patients",
                "Patients 50 Years or Older", "Specialized Health Care Beds", "Institution Population"]
GROUPS = {
    "Actual Vacancies (All)": "Staffing",
    "Medical Vacancies (All)": "Staffing",
    "Mental Health Vacancies (All)": "Staffing",
    "Dental Vacancies (All)": "Staffing",
    "Total Labor Cost (All)": "Major Costs",
    "ED & Hospital Stays": "Major Costs",
    "ED/Hospital Send-Outs (All)*": "Care Management",
    "Specialty Care Referrals*": "Other Trends",
    "Prescriptions Per Patient": "Other Trends",
}


def fetch():
    report = Report(REPORT_R)
    months = report.query({"c": "DateDim"}, [column("c", "Dashboard Month MMM yyyy"), column("c", "DashboardID")])
    print(f"{len(months)} dashboard months")
    select = [column("i", "Institution"), column("l", "Element"), column("d", "RateFormatted")]
    keep = set(IPC_MEASURES) | set(GROUPS)
    rows = []
    for label, dashboard_id in months:
        month = datetime.strptime(label, "%b %Y").strftime("%Y-%m")
        for inst, measure, formatted in report.query(SOURCES, select, [equals("c", "DashboardID", f"{dashboard_id}L")]):
            if measure in keep:
                rows.append([month, inst, measure, formatted])
    df = pd.DataFrame(rows, columns=["month", "institution_as_stated", "measure", "formatted"]).drop_duplicates()
    text = df["formatted"].fillna("").str.strip()
    df["unit"] = text.map(lambda s: "%" if "%" in s else "$" if "$" in s else "")
    df["value"] = pd.to_numeric(text.str.replace(r"[%$,]", "", regex=True), errors="coerce")
    return df.dropna(subset=["value"]).drop(columns="formatted")


def merge(new, path, codes, columns):
    """New values replace old ones, and old values the dashboard no longer gives stay."""
    key = ["month", "institution_as_stated", "measure"]
    old = pd.read_csv(path).dropna(subset=["value"])
    both = old.merge(new, on=key, how="left", suffixes=("_old", ""))
    kept = old[both["value"].isna().values]
    changed = both[both["value"].notna() & ((both["value"] - both["value_old"]).abs() > 0.051)]
    out = pd.concat([new, kept], ignore_index=True)
    out["cdcr_code"] = out["institution_as_stated"].map(lambda i: codes.get(i, ""))
    out["value"] = out["value"].map(lambda v: f"{v:.6f}".rstrip("0").rstrip("."))
    out = out[columns].sort_values(key)
    out.to_csv(path, index=False)
    print(f"{path.relative_to(ROOT)}: {len(out)} rows, {out['month'].min()} to {out['month'].max()}; "
          f"{len(changed)} held values changed {dict(Counter(changed['measure']))}; "
          f"{len(kept)} kept that the dashboard no longer gives {dict(Counter(kept['measure']))}")


def main():
    new = fetch()
    codes = load_codes()
    merge(new[new["measure"].isin(IPC_MEASURES)], IPC, codes,
          ["month", "cdcr_code", "institution_as_stated", "measure", "value", "unit"])
    measures = new[new["measure"].isin(GROUPS)].copy()
    measures["group"] = measures["measure"].map(GROUPS)
    merge(measures, MEASURES, codes,
          ["month", "cdcr_code", "institution_as_stated", "group", "measure", "value", "unit"])


if __name__ == "__main__":
    main()
