#!/usr/bin/env python3
"""
Heat Plan stage days counted from CDCR's own 2024 temperature logs → two CSVs in sources/:

  1. heat_plan_log_stage_days_2024.csv
     Stage I/II/III days per prison and month, in the same units as
     heat_plan_monthly_summaries_2024.csv (days, not alerts), so the two can be
     compared. `rule` says how each count was made and `source` where it comes from.

  2. heat_plan_log_stage_days_2024_evidence.csv
     One row per day counted (or considered and left out), with the page and the
     reading or written activation it rests on, so every count can be audited.

Two sources:

  - `logs_read`: the outside (CDCR 2030) and inside (CDCR 2031) temperature records
    in the Reuters packages, read from the page images. The readings are
    handwritten, so they were transcribed by hand into STAGE_I and STAGE_II_III
    below; nothing here is OCR. Stage I days use the "Stage 1 Activated" time
    written at the foot of each day on the 2030 log; days with an outside reading
    of 90°F or more but no written activation are listed separately. Stage II/III
    days are days with an inside reading of 90°F / 95°F or more in any housing
    unit, or a written Stage II/III activation; a day counts once however many
    units. Readings that can't be read with confidence are `doubtful` and are not
    counted; the count is then a lower bound and `note` gives the upper bound.

  - `reuters_json`: Reuters' AI-extracted indoor readings for June–August 2024
    (processed_temp_logs.json, no housing unit or page). Days with any reading
    ≥90°F / ≥95°F, by the reading's own date. A cross-check only.

Coverage of `logs_read` so far (October 2026): CCWF only, Stage I for May–October
and Stage II/III for June–July. Add prisons and months by extending the tables.

Sources: sources/reuters_heat_records/california/responses/*.pdf,
         sources/reuters_heat_records/california/processed_temp_logs.json

Usage:
  python3 scrapers/count_heat_log_stage_days.py
"""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'sources'
JSON = SRC / 'reuters_heat_records' / 'california' / 'processed_temp_logs.json'

# ---------------------------------------------------------------- Stage I, from CDCR 2030 outside logs
# (cdcr_code, date, source_file, page, side, written activation as written, reading_check, note)
# side: L/R half of the page (each page holds two days).
F = {'05': 'CCWF_MSR_0524_Redacted.pdf', '06': 'CCWF_MSR_0624_Redacted.pdf', '07': 'CCWF_MSR_0724_Redacted.pdf',
     '08': 'CCWF_MSR_0824_Redacted.pdf', '09': 'CCWF_MSR_0924_Redacted.pdf', '10': 'CCWF_MSR_1024_Redacted.pdf'}
ACT = 'written_activation'
THR = 'threshold_only'
STAGE_I = [
    # May: pages p2 (5/1-5/2) … p17 (5/31-6/1)
    ('CCWF', '2024-05-12', F['05'], 7, 'R', '1400', ACT, 'read from image', 'Deactivated 1600.'),
    ('CCWF', '2024-05-23', F['05'], 13, 'L', '', THR, 'read from image', '1900 reading 90; no activation written.'),
    ('CCWF', '2024-05-31', F['05'], 17, 'L', '1507', ACT, 'read from image', 'Deactivated 2000.'),
    # June: p_k holds days 2k-3 (L) and 2k-2 (R); p2 L repeats 5/31
    *[('CCWF', f'2024-06-{d:02d}', F['06'], (d + 3) // 2, 'L' if d % 2 else 'R', t, ACT, 'read from image', '')
      for d, t in [(1, '1400'), (5, '1200'), (6, '1020'), (7, '1117'), (8, '1800'), (10, '1700'), (11, '1203'),
                   (12, '1112'), (13, '1300'), (14, '1500'), (21, '1300'), (22, '1240'), (23, '1058'),
                   (24, '1100'), (25, '1030'), (26, '1129'), (27, '1200'), (28, '1325'), (29, '1215'),
                   (30, '1300')]],
    # July: p2 L is 6/30 (redacted), then p_k holds 2k-4 (L) and 2k-3 (R)
    *[('CCWF', f'2024-07-{d:02d}', F['07'], (d + 4) // 2, 'L' if d % 2 == 0 else 'R', t, ACT, 'read from image', '')
      for d, t in [(1, '1200'), (2, '1155'), (3, '1100'), (4, '1000'), (5, '1012'), (6, '0955'), (7, '0950'),
                   (8, '1100'), (9, '1050'), (10, '1200'), (11, '1056'), (12, '1025'), (13, '1020'),
                   (14, '1146'), (15, '1230'), (16, '1340'), (17, '1430'), (18, '1400'), (19, '1125'),
                   (20, '1041'), (21, '1200'), (22, '1145'), (23, '1052'), (24, '1030'), (25, '1030'),
                   (26, '1055'), (27, '1515'), (29, '1400'), (30, '1400'), (31, '1345')]],
    # August: p22 holds 8/1 (L) and 8/2 (R) … p37 holds 8/31 (L) and 9/1 (R)
    *[('CCWF', f'2024-08-{d:02d}', F['08'], 22 + (d - 1) // 2, 'L' if d % 2 else 'R', t, ACT, 'read from image', '')
      for d, t in [(1, '1225'), (2, '1400'), (3, '1144'), (4, '1135'), (5, '1200'), (6, '1200'), (7, '1100'),
                   (8, '1150'), (9, '1050'), (10, '1045'), (11, '1155'), (12, '1300'), (13, '1430'),
                   (14, '1330'), (15, '1330'), (16, '1337'), (17, '1500'), (19, '1500'), (20, '1330'),
                   (21, '1420'), (26, '1500'), (27, '1410'), (28, '1349'), (29, '1315'), (30, '1328'),
                   (31, '1244')]],
    ('CCWF', '2024-08-25', F['08'], 34, 'L', '', THR, 'read from image', '2000 reading 90; no activation written.'),
    ('CCWF', '2024-09-01', F['08'], 37, 'R', '1244 / 1330', ACT, 'read from image',
     'In the August package; the September package starts on 9/2.'),
    # September: p95 holds 9/2 (L) and 9/3 (R) … p109 holds 9/30 (L) and 10/1 (R)
    *[('CCWF', f'2024-09-{d:02d}', F['09'], 95 + (d - 2) // 2, 'L' if d % 2 == 0 else 'R', t, ACT,
       'read from image', '')
      for d, t in [(2, '1520'), (3, '1400'), (4, '1200'), (5, '1130'), (6, '1133'), (7, '1201'), (8, '1226'),
                   (9, '1145'), (13, '1500'), (14, '1350'), (22, '1700'), (23, '1600'), (24, '1320'),
                   (25, '1607'), (27, '1430'), (28, '1500')]],
    # October: p86 holds 9/30 (L) and 10/1 (R); p87 holds 10/2 (L) and 10/3 (R) …
    ('CCWF', '2024-10-01', F['10'], 86, 'R', '1500', ACT, 'read from image', ''),
    *[('CCWF', f'2024-10-{d:02d}', F['10'], 87 + (d - 2) // 2, 'L' if d % 2 == 0 else 'R', t, ACT,
       'read from image', '')
      for d, t in [(2, '1333'), (3, '1224'), (4, '1130'), (5, '1330'), (6, '1308')]],
    ('CCWF', '2024-10-07', F['10'], 89, 'R', '1335', ACT, 'read from image',
     'Page 90 has a second, crossed-out 10/7 half-page.'),
    ('CCWF', '2024-10-08', F['10'], 90, 'R', '1322', ACT, 'read from image', ''),
]
# Pages of CDCR 2030 logs read, by prison and month (every page in the package)
STAGE_I_PAGES = {('CCWF', '2024-05'): 16, ('CCWF', '2024-06'): 16, ('CCWF', '2024-07'): 16,
                 ('CCWF', '2024-08'): 16, ('CCWF', '2024-09'): 15, ('CCWF', '2024-10'): 17}

# ---------------------------------------------------------------- Stage II/III, from CDCR 2031 inside logs
# (cdcr_code, date, source_file, page, housing unit, highest reading seen, written activation, reading_check, note)
STAGE_II_III = [
    ('CCWF', '2024-06-02', F['06'], 55, '508', '97', '', 'doubtful',
     '2100 reading looks like 97 but the day otherwise runs 74.8–87 and the 1800 reading is illegible. '
     'Reuters JSON has 97 on 6/2 and 92 on 6/3 for this page.'),
    ('CCWF', '2024-06-21', F['06'], 79, '512', '90', '', 'read from image', '2100 reading 90.'),
    ('CCWF', '2024-06-28', F['06'], 80, '512', '90', '', 'doubtful', '2100 reading could be 90 or 80.'),
    ('CCWF', '2024-07-06', F['07'], 19, '501', '90', '', 'read from image',
     '2400 reading 90; Facility B memo (p. 39) also gives a high of 92 in Building 508 on 7/6.'),
    ('CCWF', '2024-07-07', F['07'], 19, '501', '93', '', 'read from image',
     'Unit 501 1500 91, 1800 93, 2100 92; also 507 91.7 (p. 50), 508 90 (p. 55), 516 90 (p. 100).'),
    ('CCWF', '2024-07-10', F['07'], 101, '516', '90', '', 'doubtful', '2400 reading could be 90 or 80.'),
    ('CCWF', '2024-07-13', F['07'], 40, '505', '92', '', 'read from image',
     '1500 91, 1800 92, 2100 91.2; note on the page and Facility B memo (p. 39) confirm.'),
    ('CCWF', '2024-07-23', F['07'], 61, '510', '', 'Stage II 1500–2100', 'read from image',
     'Written on the Facility C monthly synopsis ("510 Dayroom"); the unit log itself was not found ≥90.'),
]
STAGE_II_III_PAGES = {('CCWF', '2024-06'): 61, ('CCWF', '2024-07'): 84}
STAGE_II_III_MONTHS = set(STAGE_II_III_PAGES)

# ---------------------------------------------------------------- build
def codes():
    out = {}
    with open(ROOT / 'crosswalk' / 'institutions.csv') as f:
        for r in csv.DictReader(f):
            out[r['cdcr_code']] = r['cdcr_code']
            for a in filter(None, r['alias_codes'].split(';')):
                out[a.strip()] = r['cdcr_code']
    return out


def main():
    evidence = []
    for c, d, f, p, side, act, kind, check, note in STAGE_I:
        evidence.append(dict(cdcr_code=c, date=d, form='cdcr_2030', housing_unit='', source_file=f, page=p,
                             half=side, max_reading_seen='90' if kind == THR else '', threshold_hit=kind == THR,
                             written_activation=act, stage='I', counted=kind == ACT,
                             reading_check=check, note=note))
    for c, d, f, p, unit, mx, act, check, note in STAGE_II_III:
        hit = bool(mx) and float(mx) >= 90
        evidence.append(dict(cdcr_code=c, date=d, form='cdcr_2031', housing_unit=unit, source_file=f, page=p,
                             half='', max_reading_seen=mx, threshold_hit=hit, written_activation=act,
                             stage='III' if mx and float(mx) >= 95 else 'II',
                             counted=check != 'doubtful', reading_check=check, note=note))

    rows = []
    # logs_read: Stage I by written activation; Stage II/III by threshold or written activation
    months = sorted(set(STAGE_I_PAGES) | STAGE_II_III_MONTHS)
    for key in months:
        c, m = key
        ev = [e for e in evidence if e['cdcr_code'] == c and e['date'][:7] == m]
        s1 = {e['date'] for e in ev if e['stage'] == 'I' and e['counted']}
        s1_thr = {e['date'] for e in ev if e['stage'] == 'I' and e['threshold_hit'] and not e['counted']}
        notes = []
        if s1_thr:
            notes.append(f'{len(s1_thr)} more day(s) with an outside reading of 90 but no written activation '
                         f'({", ".join(sorted(s1_thr))}).')
        s2 = s3 = None
        if key in STAGE_II_III_MONTHS:
            s2 = {e['date'] for e in ev if e['form'] == 'cdcr_2031' and e['counted']}
            s3 = {e['date'] for e in ev if e['form'] == 'cdcr_2031' and e['counted'] and e['stage'] == 'III'}
            doubt = {e['date'] for e in ev if e['form'] == 'cdcr_2031' and not e['counted']}
            if doubt:
                notes.append(f'Stage II/III counts are lower bounds; {len(doubt)} doubtful day(s) not counted '
                             f'({", ".join(sorted(doubt))}).')
        pages = STAGE_I_PAGES.get(key, 0) + STAGE_II_III_PAGES.get(key, 0)
        rows.append(dict(cdcr_code=c, month=m, stage_i_days=len(s1) if key in STAGE_I_PAGES else '',
                         stage_ii_days='' if s2 is None else len(s2),
                         stage_iii_days='' if s3 is None else len(s3),
                         rule='stage I: written activation on the 2030 log; stage II/III: inside reading '
                              '≥90/≥95°F in any unit or a written activation, doubtful readings not counted',
                         source='logs_read', pages_read=pages, note=' '.join(notes)))

    # reuters_json: days with any indoor reading ≥90 / ≥95, by the reading's own date
    cmap = codes()
    s2j, s3j, seen, off = defaultdict(set), defaultdict(set), defaultdict(set), defaultdict(int)
    for x in json.load(open(JSON)):
        c = cmap.get(x['file'].split('_')[0])
        fm = re.search(r'_(\d\d)(\d\d)_', x['file'])
        mm, dd, yy = x['date'].split('/')
        k = (c, f'20{yy}-{mm}')
        if f'20{fm.group(2)}-{fm.group(1)}' != k[1]:
            off[k] += 1
        seen[k].add(x['date'])
        if x['temperature'] >= 90:
            s2j[k].add(x['date'])
        if x['temperature'] >= 95:
            s3j[k].add(x['date'])
    for k in sorted(seen):
        if k[1] not in ('2024-06', '2024-07', '2024-08'):
            continue
        note = f'{off[k]} readings come from another month\'s package.' if off[k] else ''
        rows.append(dict(cdcr_code=k[0], month=k[1], stage_i_days='', stage_ii_days=len(s2j[k]),
                         stage_iii_days=len(s3j[k]),
                         rule='days with any indoor reading ≥90 / ≥95°F (no written activations)',
                         source='reuters_json', pages_read='', note=note))

    def write(path, data):
        with open(path, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(data[0]), lineterminator='\n')
            w.writeheader()
            w.writerows(data)
    write(SRC / 'heat_plan_log_stage_days_2024.csv', rows)
    write(SRC / 'heat_plan_log_stage_days_2024_evidence.csv', evidence)
    print(f'{len(rows)} prison-months, {len(evidence)} evidence rows')


if __name__ == '__main__':
    main()
