"""Published institution code -> cdcr_code, from crosswalk/institutions.csv."""

import csv
from pathlib import Path

# Closed institutions that older reports still list; not in the crosswalk.
CLOSED_CODES = ("CCC", "DVI")


def load_codes():
    """Dict of every code and alias code to cdcr_code."""
    codes = {c: c for c in CLOSED_CODES}
    path = Path(__file__).resolve().parent.parent / "crosswalk" / "institutions.csv"
    with open(path) as f:
        for row in csv.DictReader(f):
            codes[row["cdcr_code"]] = row["cdcr_code"]
            for alias in filter(None, (a.strip() for a in row["alias_codes"].split(";"))):
                codes[alias] = row["cdcr_code"]
    return codes
