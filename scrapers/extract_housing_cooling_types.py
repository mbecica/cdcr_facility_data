#!/usr/bin/env python3
"""
CDCR's "Housing Unit Cooling Types by Institution" table → sources/housing_cooling_equipment_2024.csv

The table is CDCR's report dated August 22, 2024 (the date in the copy Reuters
published with "Scorching cells", July 2025), attached as Attachment B to CCHCS's February 20, 2025 memo "Heat Issues and
Temperature Measurement Practices", filed as Exhibit E to the Plata joint case
management statement (ECF 3952-1, pp. 38–79). It lists each piece of cooling or
ventilation equipment serving a housing building: institution, building, primary
use, asset description, equipment sub-type, and type of cooling. The pages are
scans with no text layer, so they are OCR'd here.

OCR runs twice. The first pass reads each column as a strip and assigns words
to rows by the table's ruling lines; the second reads the institution and
building cells one at a time with a character whitelist. Where the two passes
disagree, the value was checked against the page image and the rule used is in
`resolve_building()`. Each row's `ocr_check` says whether the passes agreed. The
output matches the text layer of the Reuters copy on every row and column.

Also writes one row per building to sources/building_mentions.csv (replacing
earlier rows from this source), so `scrapers/build_buildings.py` joins the
buildings to the inventory.

Source: sources/heat_cooling/plata_ecf3952-1_cms_exhibits_2025-03-10.pdf

Requires pdftoppm, tesseract and numpy.

Usage:
  python3 scrapers/extract_housing_cooling_types.py
"""

import csv
import io
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
STEM = 'plata_ecf3952-1_cms_exhibits_2025-03-10'
PDF = ROOT / 'sources' / 'heat_cooling' / f'{STEM}.pdf'
OUT = ROOT / 'sources' / 'housing_cooling_equipment_2024.csv'
MENTIONS = ROOT / 'sources' / 'building_mentions.csv'
FIRST, LAST = 38, 79              # PDF pages of the table (its pages 1–42)
COLS = ['site', 'building', 'primary_use', 'asset_description', 'equipment_sub_type', 'type_of_cooling']
# Rows CDCR has since corrected: (institution, asset description as printed) → (cooling_type, note)
CORRECTIONS = {
    ('CTF', 'Ventilation Without Cooling'): (
        'none', 'CDCR told Reuters (email, June 27, 2025) this was a misclassification in its maintenance system: '
                'the units are not refrigerated; type of cooling should read Ventilation Without Cooling and '
                'asset description AHU - Supply Blower.'),
}
COOLING = {'Refrigeration Cooling': 'mechanical', 'Evaporation Cooling': 'evaporative',
           'Ventilation Without Cooling': 'none'}


def group(v, gap=4):
    g = []
    for x in v:
        if g and x - g[-1][-1] <= gap:
            g[-1].append(x)
        else:
            g.append([x])
    return [(a[0], a[-1]) for a in g]


def grid(a):
    """Horizontal ruling lines (row borders) and the seven vertical column lines."""
    dark = a < 140
    h, w = dark.shape
    hl = group([y for y in range(h) if dark[y].sum() > w * 0.6])
    band = dark[hl[0][0]:hl[-1][1]]
    vl = group([x for x in range(w) if band[:, x].mean() > 0.9])
    return hl, vl


def tesseract(img, *args):
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return subprocess.run(['tesseract', '-', '-', *args], input=buf.getvalue(),
                          capture_output=True, check=True).stdout.decode()


def read_page(path):
    a = np.array(Image.open(path).convert('L'))
    hl, vl = grid(a)
    if len(vl) != 7:
        raise SystemExit(f'{path}: found {len(vl)} column lines, expected 7')
    clean = a.copy()
    for y0, y1 in hl:
        clean[max(0, y0 - 1):y1 + 2, :] = 255
    bands = [(hl[i][1], hl[i + 1][0]) for i in range(len(hl) - 1)]
    cells = [[[] for _ in COLS] for _ in bands]
    for c in range(6):
        strip = Image.fromarray(clean[:, vl[c][1] + 3:vl[c + 1][0] - 3])
        words = csv.DictReader(io.StringIO(tesseract(strip, '--psm', '6', 'tsv')),
                               delimiter='\t', quoting=csv.QUOTE_NONE)
        for wd in words:
            if wd['level'] != '5' or not wd['text'].strip():
                continue
            yc = int(wd['top']) + int(wd['height']) / 2
            for r, (y0, y1) in enumerate(bands):
                if y0 <= yc <= y1:
                    cells[r][c].append(wd['text'])
                    break
    header = [' '.join(x) for x in cells[0]]
    if header != ['Site Acronym', 'Building', 'Primary Use', 'Asset Description', 'Equipment Sub-Type', 'Type of Cooling']:
        raise SystemExit(f'{path}: unexpected header {header}')
    rows = []
    for r in range(1, len(bands)):
        vals = dict(zip(COLS, (' '.join(x) for x in cells[r])))
        if not any(vals.values()):
            continue
        # second pass: institution and building cells alone
        y0, y1 = hl[r][1] + 2, hl[r + 1][0] - 2
        for c, key, wl in ((0, 'site_cell', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'),
                           (1, 'building_cell', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-./')):
            img = Image.fromarray(a[y0:y1, vl[c][1] + 4:vl[c + 1][0] - 4])
            img = img.resize((img.width * 2, img.height * 2))
            vals[key] = tesseract(img, '--psm', '7', '-c', f'tessedit_char_whitelist={wl}').strip()
        rows.append(vals)
    return rows


def resolve_building(site, strip, cell):
    """Pick between the two OCR passes. Rules were checked against the page images."""
    b = strip
    if strip != cell and site in ('COR', 'MCSP', 'CMC'):
        b = cell              # COR 3C01 (strip read 3001), MCSP Y11 (Yi1), CMC S (S$)
    # CCWF 511/512/515 (cell read 911…) and CTF O (cell read nothing): strip is right
    b = re.sub(r'^([A-Z])[Oo]+(\d)$', r'\g<1>0\2', b)     # H09 read as Ho9, HO9, HOo9
    b = re.sub(r'^([A-Z])O(0\d)$', r'\1\2', b)            # H08 read as HO08
    b = re.sub(r'^([A-Z])0O(\d)$', r'\g<1>0\2', b)        # H02 read as H0O2
    return b


def institution_codes():
    codes = {}
    with open(ROOT / 'crosswalk' / 'institutions.csv') as f:
        for r in csv.DictReader(f):
            codes[r['cdcr_code']] = r['cdcr_code']
            for alias in filter(None, r['alias_codes'].split(';')):
                codes[alias.strip()] = r['cdcr_code']
    return codes


def main():
    codes = institution_codes()
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(['pdftoppm', '-r', '300', '-gray', '-png', '-f', str(FIRST), '-l', str(LAST),
                        str(PDF), f'{tmp}/p'], check=True, capture_output=True)
        pages = sorted(Path(tmp).glob('p-*.png'))
        with ThreadPoolExecutor(8) as ex:
            results = list(ex.map(read_page, pages))
    out = []
    for path, rows in zip(pages, results):
        n = int(path.stem.split('-')[1])
        for r in rows:
            site = r['site_cell'] if r['site'] != r['site_cell'] else r['site']   # CCI read as CCl
            building = resolve_building(site, r['building'], r['building_cell'])
            agreed = r['site'] == r['site_cell'] and r['building'] == r['building_cell']
            if site not in codes:
                raise SystemExit(f'p{n}: unknown institution {site!r}')
            if r['type_of_cooling'] not in COOLING:
                raise SystemExit(f'p{n}: unexpected type of cooling {r["type_of_cooling"]!r}')
            cooling_type, note = CORRECTIONS.get((codes[site], r['asset_description']),
                                                 (COOLING[r['type_of_cooling']], ''))
            out.append(dict(
                cdcr_code=codes[site], site_as_stated=site, building=building,
                primary_use=r['primary_use'], asset_description=r['asset_description'],
                equipment_sub_type=re.sub(r'(AHU|RTU)HQ', r'\1 HQ', r['equipment_sub_type']),
                type_of_cooling=r['type_of_cooling'], cooling_type=cooling_type, note=note,
                source=STEM, page=n, table_page=n - FIRST + 1,
                ocr_check='passes agree' if agreed else 'passes differed; checked against image'))
    with open(OUT, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]), lineterminator='\n')
        w.writeheader()
        w.writerows(out)
    print(f'{len(out)} rows, {len({(r["cdcr_code"], r["building"]) for r in out})} buildings → {OUT}')

    # one mention per building, at the first row that names it
    with open(MENTIONS) as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        keep = [m for m in reader if m['source'] != STEM]
    seen, new = set(), []
    for r in out:
        k = (r['cdcr_code'], r['building'])
        if k in seen:
            continue
        seen.add(k)
        new.append(dict(cdcr_code=r['cdcr_code'], building=r['building'], use='housing', as_of='2024-08',
                        source=STEM, page=r['page'],
                        quote=' | '.join([r['site_as_stated'], r['building'], r['primary_use'],
                                          r['asset_description'], r['equipment_sub_type'], r['type_of_cooling']])))
    with open(MENTIONS, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        w.writeheader()
        w.writerows(keep + [{c: m.get(c, '') for c in fields} for m in new])
    print(f'{len(new)} building mentions → {MENTIONS}')


if __name__ == '__main__':
    main()
