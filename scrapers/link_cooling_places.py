"""Add place_key to data/heat/cooling/housing_cooling_equipment_2024.csv (user, Nov 23 2026).

Run after extract_housing_cooling_types.py (which rewrites the file without this column).
place_key is the place in data/buildings/locations/places.csv that the CDCR building ID names: the key
CODE-building when it exists, else the one place whose name or alias is the building ID. `building`
stays as written. Exits if a building matches no place or more than one.
"""
import collections
import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COOL = os.path.join(ROOT, 'data', 'heat', 'cooling', 'housing_cooling_equipment_2024.csv')
PLACES = os.path.join(ROOT, 'data', 'buildings', 'locations', 'places.csv')

places = {r['place_key']: r for r in csv.DictReader(open(PLACES, newline='', encoding='utf-8'))}
byname = collections.defaultdict(set)
for k, r in places.items():
    for n in [r['place']] + [a for a in r['aliases'].split(';') if a]:
        byname[(r['cdcr_code'], n.strip().upper())].add(k)

rows = list(csv.DictReader(open(COOL, newline='', encoding='utf-8')))
cols = [c for c in rows[0] if c != 'place_key']
cols.insert(cols.index('building') + 1, 'place_key')
bad = []
for r in rows:
    key = f"{r['cdcr_code']}-{r['building']}"
    hits = {key} if key in places else byname.get((r['cdcr_code'], r['building'].strip().upper()), set())
    if len(hits) != 1:
        bad.append((r['cdcr_code'], r['building'], sorted(hits)))
        continue
    r['place_key'] = next(iter(hits))
if bad:
    sys.exit(f'{len(bad)} rows without exactly one place, e.g. {bad[:5]}')
w = csv.DictWriter(open(COOL, 'w', newline='', encoding='utf-8'), fieldnames=cols, lineterminator='\n')
w.writeheader()
w.writerows(rows)
print(f'{len(rows)} rows, {len({r["place_key"] for r in rows})} places')
