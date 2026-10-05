#!/usr/bin/env python3
"""
Extract every project from the CDCR Master Plan Annual Reports (MPAR).

Reads the MPAR PDFs in sources/cdcr_facilities_planning/ (listed in MPARS
below) and parses each institution's project status report. Each report groups
projects under five headings: Active, Complete, Proposed, Future (within 5
years), and Future (between 5 and 10 years).

Output: sources/mpar_projects.csv, one row per project per MPAR year. A project
listed in several reports appears once for each, so status, phase, and funding
can be compared across years.

Columns:
  mpar_year, institution, project_id, title, type, status,
  phase, phase_start, phase_end, pct_complete, fund_sources, completed,
  total_approved_funding, total_proposed_funding, total_estimated_cost,
  anticipated_duration_yrs, category, scope, justification

`phase`, `phase_start`, `phase_end` and `pct_complete` describe the last phase
listed for an active project (the phase underway). `fund_sources` lists the
fund source of every phase.
"""

import csv
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "sources" / "cdcr_facilities_planning"
OUT = ROOT / "sources" / "mpar_projects.csv"

MPARS = {
    2022: "2022-MPAR-Narrative-Final.pdf",
    2023: "2023MasterPlanAnnualReport.pdf",
    2024: "2024_Master_Plan_Annual_Report-ADA-Final.pdf",
    2025: "2025_MPAR-ADA_Final.pdf",
}

# Institution names as printed in the MPAR -> CDCR code
INSTITUTIONS = {
    "Avenal State Prison": "ASP",
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
    "California State Prison, Solano": "SOL",
    "Calipatria State Prison": "CAL",
    "Centinela State Prison": "CEN",
    "Central California Women's Facility": "CCWF",
    "Chuckawalla Valley State Prison": "CVSP",
    "Correctional Training Facility": "CTF",
    "Folsom State Prison": "FOL",
    "High Desert State Prison": "HDSP",
    "Ironwood State Prison": "ISP",
    "Kern Valley State Prison": "KVSP",
    "Mule Creek State Prison": "MCSP",
    "Multiple Adult Institutions": "MULTIPLE",
    "North Kern State Prison": "NKSP",
    "Pelican Bay State Prison": "PBSP",
    "Pleasant Valley State Prison": "PVSP",
    "R J Donovan Correctional Facility": "RJD",
    "Richard A. McGee Correctional Training Center": "CTC",
    "Salinas Valley State Prison": "SVSP",
    "San Quentin Rehabilitation Center": "SQ",
    "San Quentin State Prison": "SQ",
    "Sierra Conservation Center": "SCC",
    "Substance Abuse Treatment Facility and State Prison": "SATF",
    "Valley State Prison": "VSP",
    "Wasco State Prison": "WSP",
}

STATUSES = {
    "Active Projects:": "active",
    "Complete Projects:": "complete",
    "Proposed Projects:": "proposed",
    "Future Projects (Within 5 Years):": "future_5yr",
    "Future Projects (Between 5 and 10 Years):": "future_5_10yr",
}

ID_RE = re.compile(r"^ID:\s+(P-\d{4}-\d{5})\s+Type:\s+(.+?)\s*$")
PHASE_RE = re.compile(
    r"^([A-Z/]+) - ([A-Za-z./ ]+?)\s{2,}(\d{1,2}/\d{4}|TBD) - (\d{1,2}/\d{4}|TBD)\s+(\d+)%\s+(\S+)\s+\$([\d,]+)"
)
MONEY_RE = re.compile(r"(Total (?:Approved|Proposed) Funding|Total Estimated Project Cost):\s+\$([\d,]+)")
DURATION_RE = re.compile(r"Anticipated Project Duration:\s+([\d.]+)\s*Yrs?\.?\s+Category:\s+(.+?)\s*$")
COMPLETED_RE = re.compile(r"^Completed:\s+(\d{1,2}/\d{4})")
# Page furniture: page numbers, report headers, and the phase table header
SKIP_RE = re.compile(r"^(\d+|Phase/Activities.*|INSTITUTION PROJECT STATUS REPORT)$")

FIELDS = [
    "mpar_year", "institution", "project_id", "title", "type", "status",
    "phase", "phase_start", "phase_end", "pct_complete", "fund_sources", "completed",
    "total_approved_funding", "total_proposed_funding", "total_estimated_cost",
    "anticipated_duration_yrs", "category", "scope", "justification",
]


def pdf_lines(path: Path) -> list[str]:
    text = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [line.strip() for line in text.splitlines()]


def new_project(year, institution, status, title) -> dict:
    p = {f: "" for f in FIELDS}
    p.update(mpar_year=year, institution=institution, status=status, title=title)
    p["_phases"] = []
    p["_text"] = None  # which multi-line text field is being read
    return p


def finish(p: dict) -> dict:
    phases = p.pop("_phases")
    p.pop("_text")
    if phases:
        last = phases[-1]
        p.update(phase=last[1], phase_start=last[2], phase_end=last[3], pct_complete=last[4])
        p["fund_sources"] = ";".join(dict.fromkeys(ph[5] for ph in phases))
    for f in ("title", "scope", "justification"):
        p[f] = re.sub(r"\s+", " ", p[f]).strip()
    return p


def parse(year: int, lines: list[str]) -> list[dict]:
    projects, cur = [], None
    institution = status = None
    i = 0
    while i < len(lines):
        line = lines[i]
        if line == "INSTITUTION PROJECT STATUS REPORT":
            # Institution name is the next non-blank line
            j = i + 1
            while not lines[j]:
                j += 1
            name = lines[j].replace("’", "'")
            if name not in INSTITUTIONS:
                raise ValueError(f"{year}: unknown institution {name!r}")
            institution = INSTITUTIONS[name]
            i = j + 1
            continue
        if line in STATUSES:
            status = STATUSES[line]
        elif line.startswith("Title:") and institution:
            if cur:
                projects.append(finish(cur))
            cur = new_project(year, institution, status, line[len("Title:"):])
            cur["_text"] = "title"
        elif cur is None:
            pass
        elif m := ID_RE.match(line):
            cur["project_id"], cur["type"] = m.group(1), m.group(2).split(" - ")[0]
            cur["_text"] = None
        elif line.startswith("Scope:"):
            cur["scope"] = line[len("Scope:"):]
            cur["_text"] = "scope"
        elif line.startswith("Justification:"):
            cur["justification"] = line[len("Justification:"):]
            cur["_text"] = "justification"
        elif m := DURATION_RE.match(line):
            cur["anticipated_duration_yrs"], cur["category"] = m.group(1), m.group(2)
            cur["_text"] = None
        elif m := COMPLETED_RE.match(line):
            cur["completed"] = m.group(1)
            cur["_text"] = None
        elif m := PHASE_RE.match(line):
            cur["_phases"].append(m.groups())
            cur["_text"] = None
        elif m := MONEY_RE.search(line):
            col = {
                "Total Approved Funding": "total_approved_funding",
                "Total Proposed Funding": "total_proposed_funding",
                "Total Estimated Project Cost": "total_estimated_cost",
            }[m.group(1)]
            cur[col] = m.group(2).replace(",", "")
            cur["_text"] = None
        elif line and cur["_text"] and not SKIP_RE.match(line) and line != institution_name(institution):
            cur[cur["_text"]] += " " + line
        i += 1
    if cur:
        projects.append(finish(cur))
    return projects


def institution_name(code: str) -> str:
    return next((n for n, c in INSTITUTIONS.items() if c == code), "")


def main():
    rows = []
    for year, fname in MPARS.items():
        found = parse(year, pdf_lines(PDF_DIR / fname))
        missing_id = [p["title"] for p in found if not p["project_id"]]
        if missing_id:
            raise ValueError(f"{year}: projects without an ID: {missing_id}")
        print(f"{year}: {len(found)} projects")
        rows.extend(found)
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
