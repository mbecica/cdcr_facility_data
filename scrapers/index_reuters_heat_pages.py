#!/usr/bin/env python3
"""
CDCR 2024 Heat Plan packages (Reuters CPRA production) → data/heat/heat_plan_2024/heat_plan_log_pages_2024.csv

Reuters obtained each institution's monthly Heat Plan package for May–October 2024
from CDCR under the California Public Records Act and posted them as 189 scanned
PDFs (https://github.com/reuters-graphics/prison-heat-records,
indoor-temperatures/california/responses). A package holds the Monthly Summary
Report (CDCR MH-7711-1) and the month's logs: outside temperature records (CDCR
2030), inside temperature records for each housing unit (CDCR 2031), heat
incident logs (MH-7711-2) and Stage III medical rounds logs (MH-7711-3).

This script indexes every page: which form it is, and for inside temperature
records the institution, housing unit and reading location written in the
header; for outside records, the thermometer location. It doesn't read the
temperatures themselves.

Steps:
  1. OCR (cached in .cache/reuters_pages/): each page's top quarter is rendered
     at 150 dpi and read with tesseract. Pages whose form can't be identified
     are read again as a full page with tesseract's orientation detection.
  2. Assembly: forms are classified from the printed title or form number, the
     header fields are parsed, and corrections read from the page images
     (CORRECTIONS below) are applied.

`package_month` is the month in Reuters' file name (FOL_MSR_0726 is July 2024,
MONTH_FIXES). It is usually the month the package reports, but some packages
hold a different month's logs (DUPLICATES).

Header fields on inside records are often handwritten, and OCR reads handwriting
poorly. So the housing unit on every inside record was read from the page images
instead, from sheets of each page's field line, and transcribed into
notes/heat_plan_log_pages_2024_units.csv (not published); `header_check` is 'unit read from
image' for those pages. Where the OCR reading was clean and repeated (typed
units), the group of identical readings was confirmed on example pages and its
pages are marked 'unit checked by group'. The reading location and institution stay as OCR'd and
weren't checked. Dates in the log grids are handwritten and aren't extracted.

Source: sources/reuters_heat_records/california/responses/*.pdf
Requires pdftoppm, tesseract, numpy and PIL.

Usage:
  python3 scrapers/index_reuters_heat_pages.py          # OCR (resumable) + CSV
  python3 scrapers/index_reuters_heat_pages.py --csv    # CSV from the cache only
"""

import csv
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'sources' / 'reuters_heat_records' / 'california' / 'responses'
CACHE = ROOT / '.cache' / 'reuters_pages'
OUT = ROOT / 'data' / 'heat' / 'heat_plan_2024' / 'heat_plan_log_pages_2024.csv'
# Housing unit on each inside record, read from the page images (hand transcription):
# source_file, page, housing_unit_as_written ('-' = left blank on the page, '?' = illegible),
# check ('read' = read on that page; 'group' = the page's OCR reading belongs to a group of
# identical readings that was confirmed on example pages)
READINGS = ROOT / 'notes' / 'heat_plan_log_pages_2024_units.csv'  # hand-read units, not published (superseded by indoor/pages.csv)
DPI, HEAD_H = 150, 400        # top ~24% of a letter page at 150 dpi; OCR runs on a 2/3-size copy


def tesseract_tsv(img, *args):
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    out = subprocess.run(['tesseract', '-', '-', *args, 'tsv'], input=buf.getvalue(), capture_output=True,
                         env={**os.environ, 'OMP_THREAD_LIMIT': '1'}).stdout.decode(errors='replace')
    return list(csv.DictReader(io.StringIO(out), delimiter='\t', quoting=csv.QUOTE_NONE))


def words_of(words):
    return [w for w in words if w.get('level') == '5' and (w.get('text') or '').strip()]


def lines_of(words):
    """Group tesseract words into lines: [(text, top, bottom, mean_conf)]."""
    lines = {}
    for w in words:
        if w.get('level') != '5' or not (w.get('text') or '').strip():
            continue
        k = (w['block_num'], w['par_num'], w['line_num'])
        lines.setdefault(k, []).append(w)
    out = []
    for ws in lines.values():
        out.append((' '.join(w['text'] for w in ws),
                    min(int(w['top']) for w in ws),
                    max(int(w['top']) + int(w['height']) for w in ws),
                    round(sum(float(w['conf']) for w in ws) / len(ws))))
    return sorted(out, key=lambda x: x[1])


def ocr_file(name):
    """OCR every page header of one package; cache JSON and the field-line strips."""
    cache = CACHE / f'{name}.json'
    if cache.exists():
        return name, 'cached'
    strips = CACHE / 'strips' / name
    strips.mkdir(parents=True, exist_ok=True)
    pages = {}
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(['pdftoppm', '-r', str(DPI), '-gray', '-x', '0', '-y', '0', '-W', '1300',
                        '-H', str(HEAD_H), '-png', str(SRC / name), f'{tmp}/p'],
                       check=True, capture_output=True)
        files = sorted(Path(tmp).glob('p-*.png'), key=lambda p: int(p.stem.split('-')[1]))

        def one(path):
            n = int(path.stem.split('-')[1])
            img = Image.open(path)
            img.load()
            small = img.resize((img.width * 2 // 3, img.height * 2 // 3))
            words = tesseract_tsv(small, '--psm', '6')
            ls = lines_of(words)
            rec = {'lines': [l[0] for l in ls], 'conf': [l[3] for l in ls]}
            # Save the "Housing Unit" / "Thermometer Location" line at 150 dpi with its words'
            # positions, so the handwritten values can be read from the image later. When OCR
            # garbles the labels, the field line is the one after "...seven (7) days a week."
            pick = [l for l in ls if re.search(r'Housing\s*Unit\s*[:;]|Reading\s*Locat|Thermometer\s*Locat', l[0], re.I)]
            if not pick:
                for a, b in zip(ls, ls[1:]):
                    if re.search(r'days\s+a\s+week|three\s*\(3\)\s*hours', a[0], re.I) and re.search(r'INSIDE|2031', ' '.join(rec['lines'][:4]), re.I):
                        pick = [b]
                        break
            for text, top, bot, _ in pick[:1]:
                y0, y1 = max(0, top * 3 // 2 - 18), min(img.height, bot * 3 // 2 + 18)
                img.crop((0, y0, img.width, y1)).save(strips / f'{n}.png', optimize=True)
                rec['strip_y'] = [y0, y1]
                rec['field_words'] = [[w['text'], int(w['left']) * 3 // 2, int(w['left']) * 3 // 2 + int(w['width']) * 3 // 2]
                                      for w in words_of(words) if top <= int(w['top']) + int(w['height']) / 2 <= bot]
            return n, rec

        with ThreadPoolExecutor(1) as ex:
            for n, rec in ex.map(one, files):
                pages[n] = rec
    cache.write_text(json.dumps(pages))
    return name, len(pages)


def find_field_line(name, pages_needed):
    """Inside records whose field line wasn't in the header crop (taller variants): look lower on the page."""
    out = {}
    strips = CACHE / 'strips' / name
    for n in pages_needed:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(['pdftoppm', '-r', str(DPI), '-gray', '-f', str(n), '-l', str(n), '-x', '0', '-y', '0',
                            '-W', '1700', '-H', '1000', '-png', str(SRC / name), f'{tmp}/p'], check=True, capture_output=True)
            img = Image.open(next(Path(tmp).glob('*.png')))
            img.load()
        small = img.resize((img.width * 2 // 3, img.height * 2 // 3))
        words = tesseract_tsv(small, '--psm', '6')
        rec = {}
        ls = lines_of(words)
        pick = [l for l in ls if re.search(r'Housing\s*Unit\s*[:;]|Reading\s*Locat', l[0], re.I)]
        if not pick:
            pick = [b for a, b in zip(ls, ls[1:]) if re.search(r'days\s+a\s+week|three\s*\(3\)\s*hours', a[0], re.I)]
        for text, top, bot, _ in pick[:1]:
            if True:
                y0, y1 = max(0, top * 3 // 2 - 18), min(img.height, bot * 3 // 2 + 18)
                img.crop((0, y0, img.width, y1)).save(strips / f'{n}.png', optimize=True)
                rec = {'field_text': text, 'strip_y': [y0, y1],
                       'field_words': [[w['text'], int(w['left']) * 3 // 2, int(w['left']) * 3 // 2 + int(w['width']) * 3 // 2]
                                       for w in words_of(words) if top <= int(w['top']) + int(w['height']) / 2 <= bot]}
                break
        out[n] = rec
    return name, out


def reocr_unclassified(name, pages_needed):
    """Full-page OCR with orientation detection for pages the header pass couldn't identify."""
    out = {}
    for n in pages_needed:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(['pdftoppm', '-r', '100', '-gray', '-f', str(n), '-l', str(n), '-png',
                            str(SRC / name), f'{tmp}/p'], check=True, capture_output=True)
            img = Image.open(next(Path(tmp).glob('*.png')))
            ls = lines_of(tesseract_tsv(img, '--psm', '1'))
            out[n] = [l[0] for l in ls][:40]
    return name, out


FORMS = [
    ('mh_7711_1', r'MONTHLY\s+SUMMARY|7711\s*-\s*1\b'),
    ('mh_7711_2', r'HEAT\s+INCIDENT\s+LOG|7711\s*-\s*2\b'),
    ('mh_7711_3', r'MEDICAL\s+ROUNDS|7711\s*-\s*3\b'),
    ('cdcr_2030', r'OUTSIDE\s+TEMP|C[DO][CG]R\s*2030\b'),
    ('cdcr_2031', r'INSIDE\s+TEMP|C[DO][CG]R\s*2031\b'),
]


def classify(lines):
    text = '\n'.join(lines[:12])
    for form, pat in FORMS:
        if re.search(pat, text, re.I):
            return form, ''
    # garbled titles ("INS|DE TEMPERATURE", "EMPERATURE RECORD"): outside records name a thermometer location
    if re.search(r'EMPERATURE\s*R|INS\W?DE\s+TE', text, re.I):
        whole = '\n'.join(lines)
        if re.search(r'OUTSIDE|Thermometer\s*Loc|every\s+hour', whole, re.I) and not re.search(r'three\s*\(3\)|Housing\s*Unit', whole, re.I):
            return 'cdcr_2030', ''
        return 'cdcr_2031', ''
    words = re.findall(r'[A-Za-z]{3,}', text)
    if len(words) < 4:
        return 'blank_or_unreadable', ''
    # name the form only from a title-like line (never a signer's or officer's name)
    title = next((l for l in lines if re.search(r'\b(LOG|RECORD|REPORT|SHEET|PLAN|LIST|MEMORANDUM|SEQUENCE|ROSTER|'
                                              r'SCHEDULE|FORM|CHECKLIST|MEDS|ATTACHMENT|NOTICE)\b', l, re.I)
                  and not re.search(r'STATE OF CALIFORNIA|DEPARTMENT OF', l, re.I)), '')
    return 'other_form', clean(title)[:80]


def clean(x):
    return re.sub(r'\s+', ' ', x).strip(' _-|:;.,~—')


def parse(form, lines):
    """Header fields: the text between each printed label and the next one."""
    r = {}
    if form == 'cdcr_2031':
        line = next((l for l in lines if re.search(r'Housing\s*Unit\s*[:;]|Reading\s*Locat', l, re.I)), '')
        m = re.search(r'stitution\s*[:;]?(.*?)(?:Housing|$)', line, re.I)
        r['institution_as_stated'] = clean(m.group(1)) if m else ''
        m = re.search(r'Housing\s*Unit\s*[:;]?(.*?)(?:Temp\w*\.?\s*Read|Read\w*\s*Loc|$)', line, re.I)
        r['housing_unit_as_stated'] = clean(m.group(1)) if m else ''
        m = re.search(r'Loca\w*\s*[:;]?(.*)$', line, re.I)
        r['reading_location_as_stated'] = clean(m.group(1)) if m else ''
    elif form == 'cdcr_2030':
        line = next((l for l in lines if re.search(r'INSTITUTION\s*[:;]', l, re.I)), '')
        r['institution_as_stated'] = clean(re.sub(r'.*INSTITUTION\s*[:;]', '', line, flags=re.I)) if line else ''
        line = next((l for l in lines if re.search(r'Thermometer\s*Locat', l, re.I)), '')
        r['thermometer_location_as_stated'] = clean(re.sub(r'.*Locat\w*\s*[:;]?', '', line, flags=re.I)) if line else ''
    return r


def institution_codes():
    codes = {}
    with open(ROOT / 'data' / 'institutions.csv') as f:
        for r in csv.DictReader(f):
            codes[r['cdcr_code']] = r['cdcr_code']
            for a in filter(None, r['alias_codes'].split(';')):
                codes[a.strip()] = r['cdcr_code']
    return codes


def file_meta(name, codes):
    m = re.match(r'([A-Z]+)_(?:[A-Z]+_)*?(?:MSR_)?(\d{2})(\d{2})_', name)
    code = name.split('_')[0]
    mm, yy = m.group(2), m.group(3)
    return codes.get(code, code), MONTH_FIXES.get(name, f'20{yy}-{mm}')


# File names with a wrong year (the package's Monthly Summary gives the month)
MONTH_FIXES = {'FOL_MSR_0726_Redacted.pdf': '2024-07'}


# Packages whose pages repeat another package (compared page images)
DUPLICATES = {
    'PBSP_MSR_0724_Redacted.pdf': 'Same pages as PBSP_MSR_0624_Redacted.pdf: the June 2024 package (Monthly Summary '
                                  'dated July 1, 2024, for June); no July 2024 logs.',
}


# Weather-station data exports (15-minute records: Temp Out, Hum, Dew, Wind, Heat Index, Rain,
# plus the console's own In Temp/Hum), filed after each CDCR 2030 outside record. Identified
# Nov 2026 from whole-page OCR (rotated for August) and page order; titles don't OCR.
WEATHER_STATION_EXPORTS = {
    'NKSP_MSR_0624_Redacted.pdf': '43-46, 48-55, 97-104, 106-113, 115-122, 164-171, 173-180, 182-189, 191-198, 240-247, 249-256, 258-265, 267-270, 312-319, 321-328, 330-337',
    'NKSP_MSR_0724_Redacted.pdf': '52-59, 61-68, 70-77, 134-141, 143-150, 152-159, 161-168, 210-217, 219-226, 228-235, 237-244, 298-305, 307-314, 316-323, 326-333, 375-382',
    'NKSP_MSR_0824_Redaction.pdf': '42-49, 51-58, 104-111, 113-120, 122-129, 131-138, 178-185, 187-194, 196-203, 245-252, 254-261, 263-270, 317-324, 326-333, 335-342, 344-351',
    'NKSP_MSR_0924_Redacted.pdf': '48-55, 104-111, 113-120, 122-129, 176-183, 185-192, 194-201, 203-210, 257-264, 266-273, 275-282, 284-291, 340-347, 349-356, 358-365, 412-419',
    'NKSP_MSR_1024_Redacted.pdf': '47-54, 56-63, 65-72, 74-81, 128-135, 137-144, 146-153, 200-207, 209-216, 263-270, 272-279, 326-333, 335-342, 344-351, 353-360',
}


# Page types checked by eye on pages the header OCR misfiled (Nov 2026 audit of never-read pages:
# whole-page OCR triage, then contact sheets). Pages with transcribed readings are taken from
# indoor/pages.csv instead (see INDOOR_PAGES), so this list only needs pages not yet transcribed.
FORM_BY_EYE = {
    'cdcr_2031': {  # inside temperature records not yet transcribed
        'CIM_MSR_0624_Redacted.pdf': '76', 'CIM_MSR_1024_Redacted.pdf': '41',
        'CMC_MSR_0524_Redacted.pdf': '7', 'CMC_MSR_0824_Redacted.pdf': '21, 92, 144, 150',
        'CMC_MSR_0924_Redacted.pdf': '311', 'HDSP_MSR_0524_Redacted.pdf': '62',
        'HDSP_MSR_0624_Redacted.pdf': '42, 57', 'RJD_MSR_0824_Redacted.pdf': '22',
        'SVSP_MSR_0924_Redacted.pdf': '47-48, 83', 'WSP_MSR_0924_Redacted.pdf': '98',
        'WSP_MSR_1024_Redacted.pdf': '79, 81, 83, 85-87, 98-100, 103, 106',
    },
    'other_form': {  # titled as outside records by OCR, but checklists or memos
        'CIW_MSR_0524_Redacted.pdf': '100, 102-105, 107-120, 122-130',
        'NKSP_MSR_0724_Redacted.pdf': '31, 122, 324',
        'SCC_MSR_0524_Redacted.pdf': '2', 'SCC_MSR_0624_Redacted_R.pdf': '2',
        # page 2 of the daily "Heat Plan Expectation Meeting" minutes, OCR'd as mh_7711_3 (checked by eye Nov 18)
        'CEN_MSR_0924_Redacted.pdf': '64, 68, 72, 76, 80, 84, 88, 92, 96, 100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 140',
        'CEN_MSR_1024_Redacted.pdf': '63, 67, 71, 75, 79, 83, 87, 91, 95, 99, 103, 107, 111, 115, 119, 123, 127, 131, 135, 139, 143, 147, 151',
    },
    'cdcr_2030': {  # outside temperature records (thermometer location D-OBSERVATION), checked by eye Nov 18
        'CIM_MSR_0524_Redacted.pdf': '105-112', 'CIM_MSR_0624_Redacted.pdf': '7',
        'CIM_MSR_0924_Redacted.pdf': '123, 125',
        'CEN_MSR_0724_Redacted.pdf': '32',
    },
}
INDOOR_PAGES = ROOT / 'data' / 'heat' / 'heat_plan_2024' / 'indoor' / 'pages.csv'


def load_read_pages():
    """(package, page) of pages the transcription identified as inside records, readings or not."""
    out = set()
    if INDOOR_PAGES.exists():
        with open(INDOOR_PAGES) as f:
            for r in csv.DictReader(f):
                if (r['form'] and r['set_aside'] != 'no_inside_readings') or r['set_aside'] == 'duplicate_scan':
                    out.add((r['package'], int(r['page'])))
    return out


def _expand(spec):
    out = set()
    for part in spec.split(', '):
        a, _, b = part.partition('-')
        out.update(range(int(a), int(b or a) + 1))
    return out


def load_readings():
    out = {}
    if READINGS.exists():
        with open(READINGS) as f:
            for r in csv.DictReader(f):
                out[(r['source_file'], int(r['page']))] = (r['housing_unit_as_written'], r['check'])
    return out

COLS = ['source_file', 'page', 'cdcr_code', 'package_month', 'form', 'form_as_stated',
        'institution_as_stated', 'housing_unit_as_stated', 'reading_location_as_stated',
        'thermometer_location_as_stated', 'first_date_as_stated', 'last_date_as_stated',
        'header_check', 'note']


def assemble():
    codes = institution_codes()
    reocr = json.loads((CACHE / '_reocr.json').read_text()) if (CACHE / '_reocr.json').exists() else {}
    fields = json.loads((CACHE / '_fields.json').read_text()) if (CACHE / '_fields.json').exists() else {}
    readings = load_readings()
    read_pages = load_read_pages()
    rows = []
    for name in sorted(p.name for p in SRC.glob('*.pdf')):
        pages = json.loads((CACHE / f'{name}.json').read_text())
        code, month = file_meta(name, codes)
        for n in sorted(pages, key=int):
            lines = pages[n]['lines']
            form, as_stated = classify(lines)
            note = ''
            if form in ('blank_or_unreadable', 'other_form') and n in reocr.get(name, {}):
                f2, s2 = classify(reocr[name][n])
                if f2 not in ('blank_or_unreadable',):
                    form, as_stated, lines = f2, s2, reocr[name][n]
                    note = 'identified from full-page OCR'
            if int(n) in _expand(WEATHER_STATION_EXPORTS.get(name, '0')):
                form, as_stated, note = 'weather_station_export', '', ''
            for f_eye, spec in FORM_BY_EYE.items():
                if int(n) in _expand(spec.get(name, '0')) and form != f_eye:
                    form, as_stated, note = f_eye, '', 'identified from page image'
            if (re.sub(r'(_Redacted)?(_R)?\.pdf$', '', name), int(n)) in read_pages and form != 'cdcr_2031':
                form, as_stated, note = 'cdcr_2031', '', 'identified from page image'
            extra = fields.get(name, {}).get(n, {}).get('field_text')
            if form == 'cdcr_2031' and extra:
                lines = lines + [extra]
            r = dict(source_file=name, page=int(n), cdcr_code=code, package_month=month, form=form,
                     form_as_stated=as_stated, header_check='ocr', note=note, **parse(form, lines))
            u, how = readings.get((name, int(n)), (None, None))
            if form == 'cdcr_2031' and u is not None:
                r['housing_unit_as_stated'] = '' if u in ('-', '?') else u
                r['header_check'] = 'unit read from image' if how == 'read' else 'unit checked by group'
                if u == '-':
                    r['note'] = ((r['note'] + '; ') if r['note'] else '') + 'housing unit left blank on the page'
                elif u == '?':
                    r['note'] = ((r['note'] + '; ') if r['note'] else '') + 'housing unit illegible or cut off'
            if name in DUPLICATES:
                r['note'] = ((r['note'] + '; ') if r['note'] else '') + DUPLICATES[name]
            rows.append(r)
    with open(OUT, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLS, lineterminator='\n', extrasaction='ignore')
        w.writeheader()
        w.writerows({c: r.get(c, '') for c in COLS} for r in rows)
    print(f'{len(rows)} pages → {OUT}')
    return rows


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    if '--csv' not in sys.argv:
        names = sorted(p.name for p in SRC.glob('*.pdf'))
        with ProcessPoolExecutor(6) as ex:
            for i, (name, n) in enumerate(ex.map(ocr_file, names), 1):
                print(f'[{i}/{len(names)}] {name}: {n}', flush=True)
        # second pass for pages the header couldn't identify
        todo = {}
        for name in names:
            pages = json.loads((CACHE / f'{name}.json').read_text())
            todo[name] = [int(n) for n, p in pages.items() if classify(p['lines'])[0] in ('blank_or_unreadable', 'other_form')]
        done = json.loads((CACHE / '_reocr.json').read_text()) if (CACHE / '_reocr.json').exists() else {}
        todo = {k: [n for n in v if str(n) not in done.get(k, {})] for k, v in todo.items()}
        with ProcessPoolExecutor(4) as ex:
            for name, out in ex.map(reocr_unclassified, todo.keys(), todo.values()):
                done.setdefault(name, {}).update({str(k): v for k, v in out.items()})
                (CACHE / '_reocr.json').write_text(json.dumps(done))
        # inside records whose field line sits below the header crop
        fields = json.loads((CACHE / '_fields.json').read_text()) if (CACHE / '_fields.json').exists() else {}
        todo = {}
        for name in names:
            pages = json.loads((CACHE / f'{name}.json').read_text())
            todo[name] = [int(n) for n, p in pages.items()
                          if classify(p['lines'])[0] == 'cdcr_2031' and 'strip_y' not in p and str(n) not in fields.get(name, {})]
        with ProcessPoolExecutor(6) as ex:
            for name, out in ex.map(find_field_line, todo.keys(), todo.values()):
                fields.setdefault(name, {}).update({str(k): v for k, v in out.items()})
                (CACHE / '_fields.json').write_text(json.dumps(fields))
    assemble()


if __name__ == '__main__':
    main()
