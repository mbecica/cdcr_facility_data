#!/usr/bin/env python3
"""
Monthly grievance and appeal claim counts by institution from SB 601 reporting.

Two sources, marked in the `source` column:
  dashboard  The SB 601 Power BI dashboard, "Incarcerated Persons Grievances and
             Appeals" category, read through the dashboard's public query
             endpoint (the same one the page uses). Jul 2021 onward, plus a few
             Jan 2021 values. Detailed claim statuses (Denied, Granted,
             Redirected, Rejected, ...).
  open_data  The data.ca.gov "SB601 Reporting" download saved in
             sources/sb601_open_data/ (Jan 2020 – Jun 2024). Older status
             groupings (Upheld, Dismissed, Pending, Time Expired), plus the
             1st/2nd/3rd level appeals that were retired June 30, 2020.

The dashboard is used for every month it reports Grievance Claims Received;
open data rows for those months are dropped. Where the two overlapped they
mostly agreed, but CDCR notes counts are "subject to future restatement or
correction" and the dashboard is the more recent publication.

Output: data/sb601_grievances.csv, one row per institution, report date and
metric.
  Columns: source, institution (as published), cdcr_code, report_date (as
  published), month (YYYY-MM), fiscal_year, category, metric, value

Some dashboard values carry a report date that is not the month end (e.g.
2024-01-01, 2025-07-01); they never repeat a metric already reported for that
month, so `month` groups them with the rest of the month.

Usage:
  python3 scrapers/fetch_sb601_grievances.py
"""

import base64
import gzip
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sb601_grievances.csv"
OPEN_DATA = ROOT / "sources" / "sb601_open_data" / "sb601_data_2024_06.xlsx"
CROSSWALK = ROOT / "crosswalk" / "institutions.csv"

# Resource key from the dashboard URL (same report as fetch_sb601_operations.js)
REPORT_R = "eyJrIjoiYzlkM2RiNWEtZDRjMi00ODllLTg2YzEtZjYyM2MwMjA5NmQ0IiwidCI6IjA2NjI0NzdkLWZhMGMtNDU1Ni1hOGY1LWMzYmM2MmFhMGQ5YyJ9"
API = "https://wabi-us-gov-iowa-api.analysis.usgovcloudapi.net/public/reports/"
DASHBOARD_CATEGORY = "Incarcerated Persons Grievances and Appeals"
OPEN_DATA_CATEGORIES = {
    "Inmate Grievances and Appeals",
    "Inmate Appeals - 1st Level",
    "Inmate Appeals - 2nd Level",
    "Inmate Appeals - 3rd Level",
}

# Open data institution name -> CDCR code (names as published)
OPEN_DATA_CODES = {
    "Avenal State Prison": "ASP",
    "California City Correctional Facility": "CAC",
    "California Correctional Center": "CCC",
    "California Correctional Institution": "CCI",
    "California Health Care Facility": "CHCF",
    "California Institution for Men": "CIM",
    "California Institution for Women": "CIW",
    "California Medical Facility": "CMF",
    "California Men's Colony": "CMC",
    "California Rehabilitation Center": "CRC",
    "California State Prison, Corcoran": "COR",
    "California State Prison, Los Angeles County": "LAC",
    "California State Prison, Sacramento": "SAC",
    "California State Prison, Solano County": "SOL",
    "California Substance Abuse Treatment Facility": "SATF",
    "Calipatria State Prison": "CAL",
    "Centinela State Prison": "CEN",
    "Central California Women's Facility": "CCWF",
    "Chuckawalla Valley State Prison": "CVSP",
    "Correctional Training Facility": "CTF",
    "Deuel Vocational Institution": "DVI",
    "Folsom State Prison": "FOL",
    "High Desert State Prison": "HDSP",
    "Ironwood State Prison": "ISP",
    "Kern Valley State Prison": "KVSP",
    "Mule Creek State Prison": "MCSP",
    "North Kern State Prison": "NKSP",
    "Pelican Bay State Prison": "PBSP",
    "Pleasant Valley State Prison": "PVSP",
    "Richard J. Donovan Correctional Facility": "RJD",
    "Salinas Valley State Prison": "SVSP",
    "San Quentin Rehabilitation Center": "SQ",
    "Sierra Conservation Center": "SCC",
    "Valley State Prison": "VSP",
    "Wasco State Prison": "WSP",
}


def fiscal_year(d):
    start = d.year if d.month >= 7 else d.year - 1
    return f"{start}-{start + 1}"


def post(url, key, body=None):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode() if body else None,
        headers={"X-PowerBI-ResourceKey": key, "Content-Type": "application/json",
                 "Accept-Encoding": "gzip"})
    raw = urllib.request.urlopen(req, timeout=300).read()
    try:
        raw = gzip.decompress(raw)
    except OSError:
        pass
    return json.loads(raw)


def decode(res):
    """Rows from a Power BI DSR response (value dictionaries, repeat and null bitmasks)."""
    ds = res["results"][0]["result"]["data"]["dsr"]["DS"][0]
    if not ds.get("IC", True):
        raise RuntimeError("Power BI returned a truncated result")
    dicts = ds.get("ValueDicts", {})
    rows, prev, schema = [], None, None
    for ph in ds["PH"]:
        for dms in ph.values():
            for dm in dms:
                schema = dm.get("S", schema)
                if not any(k in dm for k in ("C", "R", "Ø")):
                    row = [dm.get(s["N"]) for s in schema]
                else:
                    vals, repeat, null, row = iter(dm.get("C", [])), dm.get("R", 0), dm.get("Ø", 0), []
                    for i, s in enumerate(schema):
                        if repeat >> i & 1:
                            row.append(prev[i])
                        elif null >> i & 1:
                            row.append(None)
                        else:
                            v = next(vals)
                            row.append(dicts[s["DN"]][v] if "DN" in s and isinstance(v, int) else v)
                prev = row
                rows.append(row)
    return rows


def fetch_dashboard():
    key = json.loads(base64.b64decode(REPORT_R + "=="))["k"]
    model = post(API + key + "/modelsAndExploration?preferReadOnlySession=true", key)
    model_id, dataset = model["models"][0]["id"], model["models"][0]["dbName"]
    report = model["exploration"]["report"]["objectId"]

    def query(columns, where):
        col = lambda p: {"Column": {"Expression": {"SourceRef": {"Source": "s"}}, "Property": p}, "Name": f"s.{p}"}
        q = {"Version": 2, "From": [{"Name": "s", "Entity": "SB601", "Type": 0}],
             "Select": [col(c) for c in columns], "Where": where}
        body = {"version": "1.0.0", "modelId": model_id, "cancelQueries": [], "queries": [{
            "Query": {"Commands": [{"SemanticQueryDataShapeCommand": {"Query": q, "Binding": {
                "Primary": {"Groupings": [{"Projections": list(range(len(columns)))}]},
                "DataReduction": {"DataVolume": 4, "Primary": {"Window": {"Count": 30000}}},
                "Version": 1}}}]},
            "QueryId": "", "ApplicationContext": {"DatasetId": dataset, "Sources": [{"ReportId": report}]}}]}
        return decode(post(API + "querydata?synchronous=true", key, body))

    def equals(prop, literal):
        return {"Condition": {"In": {
            "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "s"}}, "Property": prop}}],
            "Values": [[{"Literal": {"Value": literal}}]]}}}

    category = equals("Category", f"'{DASHBOARD_CATEGORY}'")
    dates = sorted(r[0] for r in query(["Date"], [category]))
    rows = []
    # One query per report date keeps each result well under the 30,000-row cap
    for ms in dates:
        d = datetime.fromtimestamp(ms / 1000, timezone.utc)
        where = [category, equals("Date", f"datetime'{d:%Y-%m-%dT00:00:00}'")]
        for _, inst, metric, value in query(["Date", "Institution", "Metric", "Value"], where):
            rows.append({"source": "dashboard", "institution": inst, "report_date": d.date(),
                         "category": DASHBOARD_CATEGORY, "metric": metric, "value": value})
        print(f"  {d:%Y-%m-%d}: {len(rows)} rows so far")
    return pd.DataFrame(rows)


def read_open_data():
    od = pd.read_excel(OPEN_DATA)
    od = od[od["CategoryTitle"].isin(OPEN_DATA_CATEGORIES)]
    return pd.DataFrame({
        "source": "open_data",
        "institution": od["Institution"],
        "report_date": pd.to_datetime(od["ReportDate"]).dt.date,
        "category": od["CategoryTitle"],
        "metric": od["FieldName"],
        "value": od["FieldValue"],
    })


def main():
    print("Querying SB 601 dashboard...")
    dash = fetch_dashboard()
    print(f"Reading {OPEN_DATA.relative_to(ROOT)}...")
    od = read_open_data()

    unmapped = set(od["institution"]) - set(OPEN_DATA_CODES)
    if unmapped:
        raise SystemExit(f"Add these open data institutions to OPEN_DATA_CODES: {sorted(unmapped)}")

    xw = pd.read_csv(CROSSWALK, dtype={"alias_codes": str})
    aliases = {a.strip(): code for code, al in zip(xw["cdcr_code"], xw["alias_codes"].fillna(""))
               for a in al.split(";") if a.strip()}
    dash["cdcr_code"] = dash["institution"].replace(aliases)
    od["cdcr_code"] = od["institution"].map(OPEN_DATA_CODES)

    df = pd.concat([dash, od], ignore_index=True)
    df["month"] = pd.to_datetime(df["report_date"]).dt.strftime("%Y-%m")
    dash_months = set(df.loc[(df["source"] == "dashboard")
                             & (df["metric"] == "Grievance Claims Received"), "month"])
    dropped = (df["source"] == "open_data") & df["month"].isin(dash_months)
    print(f"Dropping {dropped.sum()} open data rows for months the dashboard covers")
    df = df[~dropped]
    df["fiscal_year"] = pd.to_datetime(df["report_date"]).map(fiscal_year)
    df["value"] = pd.to_numeric(df["value"]).astype("Int64")
    cols = ["source", "institution", "cdcr_code", "report_date", "month", "fiscal_year",
            "category", "metric", "value"]
    df = df[cols].sort_values(["source", "cdcr_code", "report_date", "metric"])
    df.to_csv(OUT, index=False)
    print(f"Saved {len(df)} rows to {OUT.relative_to(ROOT)}")
    for src, g in df.groupby("source"):
        print(f"  {src}: {g['month'].min()} – {g['month'].max()}, "
              f"{g['cdcr_code'].nunique()} institutions, {g['metric'].nunique()} metrics")


if __name__ == "__main__":
    main()
