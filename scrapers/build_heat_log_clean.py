"""Write the cleaned indoor heat-log readings from the published raw readings.

Input: data/heat/heat_plan_2024/indoor/raw/{cdcr_code}.csv and indoor/locations.csv, plus two
manual review inputs in scrapers/heat_log_clean/:
- drops.csv: page-days whose readings are left out (package, page, housing_unit_as_written, date, reason).
  reason is one of
    other_month_package  the day is also on a sheet in the package for the date's own month
    sheet_change_day     the day is also on the next or previous sheet; the sheet whose printed week
                         holds the day is kept
    repeated_day         the same readings are repeated on a later sheet
    overlapping_sheet    two sheets for one unit cover the same week; each day is kept from one sheet
- value_fixes.csv: readings whose written value is a clear writing slip (temp_f_raw -> temp_f).
Output: OUT/indoor/clean/{cdcr_code}.csv (OUT defaults to data/heat/heat_plan_2024).

Rules:
- Only cells with a reading; blank, illegible and redacted cells are left out.
- Every value in a multi-value cell stays as its own row with value_label, as in raw.
- Doubtful readings keep their published value; `doubtful` = yes where raw status is unsure or
  ambiguous. raw keeps status, alt_f and read_basis.

Usage:
    python3 scrapers/build_heat_log_clean.py [OUT_DIR]
"""
import csv
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / 'data/heat/heat_plan_2024'
IND = REPO / 'data/heat/heat_plan_2024/indoor'
RULES = Path(__file__).resolve().parent / 'heat_log_clean'

LOC_COLS = ['facility_key', 'unit_key', 'place_key', 'place_type', 'section', 'level',
            'place_part', 'location_type', 'room_kind']
COLS = (['package', 'page', 'cdcr_code', 'form', 'housing_unit_as_written'] + LOC_COLS
        + ['day', 'date', 'time', 'value_label', 'temp_f', 'doubtful'])


def main():
    loc = {(r['package'], r['page'], r['housing_unit_as_written']): r
           for r in csv.DictReader(open(IND / 'locations.csv'))}
    drops = {(r['package'], r['page'], r['housing_unit_as_written'], r['date']): r['reason']
             for r in csv.DictReader(open(RULES / 'drops.csv'))}
    fixes = {(r['package'], r['page'], r['housing_unit_as_written'], r['date'], r['time'], r['value_label']): r
             for r in csv.DictReader(open(RULES / 'value_fixes.csv'))}
    used_drops, used_fixes, n = set(), set(), Counter()
    out_dir = OUT / 'indoor/clean'
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in sorted((IND / 'raw').glob('*.csv')):
        rows = []
        for r in csv.DictReader(open(f)):
            if r['temp_f'] == '':
                n['no reading'] += 1
                continue
            dk = (r['package'], r['page'], r['housing_unit_as_written'], r['date'])
            if dk in drops:
                used_drops.add(dk)
                n['dropped: ' + drops[dk]] += 1
                continue
            fk = dk + (r['time'], r['value_label'])
            if fk in fixes:
                if r['temp_f'] != fixes[fk]['temp_f_raw']:
                    sys.exit(f'value fix no longer matches raw: {fk} raw {r["temp_f"]}')
                r['temp_f'] = fixes[fk]['temp_f']
                used_fixes.add(fk)
            l = loc.get((r['package'], r['page'], r['housing_unit_as_written']))
            if l is None:
                sys.exit(f'no locations.csv row for {r["package"]} p{r["page"]} {r["housing_unit_as_written"]!r}')
            r.update({c: l[c] for c in LOC_COLS})
            r['doubtful'] = 'yes' if r['status'] in ('unsure', 'ambiguous') else 'no'
            rows.append({c: r[c] for c in COLS})
        n['kept'] += len(rows)
        with open(out_dir / f.name, 'w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=COLS)
            w.writeheader()
            w.writerows(rows)
    missing_d = set(drops) - used_drops
    missing_f = set(fixes) - used_fixes
    if missing_d or missing_f:
        sys.exit(f'rules that matched no raw rows: {len(missing_d)} drops, {len(missing_f)} value fixes')
    for k, v in sorted(n.items()):
        print(f'{k}: {v:,}')


if __name__ == '__main__':
    main()
