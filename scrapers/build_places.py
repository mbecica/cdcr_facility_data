#!/usr/bin/env python3
"""
Build the physical-place table from the building inventory (draft, step 1 of
the location restructure).

Reads:
  crosswalk/buildings.csv       built by scrapers/build_buildings.py
  crosswalk/housing_units.csv   hand-entered; `from_building_key` names inventory
                                rows that are housing units, not places
  crosswalk/facilities.csv      hand-entered; facility names -> keys
  crosswalk/place_parts.csv     hand-entered; `from_building_key` names inventory
                                rows that are parts of a place (wings)
  sources/openstreetmap/osm_cdcr_buildings.csv
                                only the OSM_PLACES rows below: buildings a unit
                                needs that no CDCR record names (unattributed
                                mapper names, so links to them are candidates)

Output: crosswalk/places.csv
  One row per building, outdoor area or other structure. Columns are the
  inventory's, renamed (building_key -> place_key, building -> place,
  building_name -> place_name), plus:
    kind             building / other structure (outdoor area: none yet)
    facility_key     {cdcr_code}-{facility} (or the key facilities.csv gives
                     that name, e.g. NKSP "M Yard" -> NKSP-M) where a source places the building
                     in a facility: a mention's `facility`, or the SPI name
                     ("Cedar Hall, Fac-D", "Facility C Hsg Unit 1")
    facility_source  mention / SPI name
    group_row        yes when the record covers several buildings or units
                     (name lists or ranges them, or a hand list). Step 2 splits
                     these; until then this flag is a pattern match to check.
    split_from       blank until step 2
    stories          blank; no source yet

Inventory rows named in `from_building_key` are left out: they move to
housing_units.csv or place_parts.csv.
"""

import re
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CW = ROOT / 'crosswalk'

OTHER_STRUCTURE = {
    'CARPORT', 'ELECTRIC VEHICLE CHARGING STATION', 'WATER MONITORING STATION',
    'SMALL MANAGEMENT EXERCISE YARDS', 'STAGING AREA',
}
# records that cover several buildings but don't say so in the name
GROUP_ROWS = {
    'CIM-spi15084',   # "Facility-B", agency no. "(SEE COMMENTS)"
    'FOL-spi14636',   # Old Dormitories Camp Represa, agency no. "H700 TO H1300"
    'FOL-spi14637',   # New Dormitories Camp Represa, agency no. "H100 TO H600"
    'FOL-spi14661',   # Gun Towers, agency no. "S10 TO S28, S31, S34, S35"
    'FOL-spi14668',   # Main Yard Buildings, agency no. "S02 (SEE COMMENTS)"
    # KVSP 180 records: CQIT 2026 counts eight units per facility, SPI has four
    # records per facility at 50,203 sq ft, the size SATF's SPI names with two units
    'KVSP-321', 'KVSP-322', 'KVSP-323', 'KVSP-324', 'KVSP-331', 'KVSP-332', 'KVSP-333',
    'KVSP-334', 'KVSP-341', 'KVSP-342', 'KVSP-343', 'KVSP-344', 'KVSP-351', 'KVSP-352',
    'KVSP-353', 'KVSP-354',
    # SVSP and HDSP 180 records: logs name eight units per yard (C1-C8 etc.), SPI has
    # four records per yard at 42,000-46,540 sq ft
    'SVSP-331', 'SVSP-332', 'SVSP-333', 'SVSP-334', 'SVSP-335', 'SVSP-336', 'SVSP-337',
    'SVSP-338', 'HDSP-341', 'HDSP-342', 'HDSP-343', 'HDSP-344', 'HDSP-351', 'HDSP-352',
    'HDSP-353', 'HDSP-354',
}

# OSM buildings that a housing unit needs and the inventory lacks, as
# {place_key: osm_id}. A key already in the inventory keeps its row and gains
# the OSM name (if blank) and source.
OSM_PLACES = {
    'CMC-303': '204437395',   # Dormitory 31 (303)
    'CMC-304': '204437393',   # Dormitory 32 (304); inventory row from the Plata cooling table
    'CMC-305': '204437394',   # Dormitory 33 (305)
    'CMC-308': '204435962',   # Dormitory 34 (308)
}
OSM_NUM = re.compile(r'\((\w+)\)\s*$')

FAC_IN_NAME = re.compile(r'\b(?:Facility|Fac\.?)[\s\-]+([A-Z])\b', re.I)
RANGE = re.compile(r'(?<![A-Za-z\-\d])\d+\s*(?:-|to|&)\s*\d+(?![\d.])', re.I)
LETTER_LIST = re.compile(r'\b[A-Z]\s*&\s*[A-Z]\b')


def facility(row, names):
    if row['facility']:
        keys = [names.get((row['cdcr_code'], f.strip()), f"{row['cdcr_code']}-{f.strip()}")
                for f in row['facility'].split(';')]
        return ';'.join(keys), 'mention'
    if row['spi_structure_number']:
        m = FAC_IN_NAME.search(row['building_name'])
        if m:
            return f"{row['cdcr_code']}-{m.group(1).upper()}", 'SPI name'
    return '', ''


def group_row(row):
    if row['building_key'] in GROUP_ROWS or '/' in row['building']:
        return 'yes'
    name = row['building_name']
    m = RANGE.search(name)
    # "Bldg 321 - 270 Housing" is a number and a design size, not a range
    if m and not name.lower().startswith(('bldg ' + row['building']).lower()):
        return 'yes'
    # letter pairs ("R&R", "A & B Visiting") are mostly one building; only
    # dormitory records are counted ("Facility C F&G")
    if LETTER_LIST.search(name) and row['spi_structure_type'] == 'DORMITORY':
        return 'yes'
    return ''


def add_osm(b):
    osm = pd.read_csv(ROOT / 'sources/openstreetmap/osm_cdcr_buildings.csv', dtype=str).fillna('')
    osm = osm.set_index('osm_id')
    new = []
    for key, oid in OSM_PLACES.items():
        r = osm.loc[oid]
        src = f"OSM {r['osm_type']}/{oid}"
        hit = b['building_key'] == key
        if hit.any():
            i = b.index[hit][0]
            if not b.at[i, 'building_name']:
                b.at[i, 'building_name'] = r['name']
            b.at[i, 'sources'] = ';'.join(filter(None, [b.at[i, 'sources'], src]))
            b.at[i, 'n_sources'] = str(int(b.at[i, 'n_sources'] or 0) + 1)
            continue
        row = {c: '' for c in b.columns}
        row.update(building_key=key, cdcr_code=r['cdcr_code'],
                   building=OSM_NUM.search(r['name']).group(1), building_name=r['name'],
                   use='housing' if 'Dormitory' in r['name'] else '',
                   n_sources='1', sources=src)
        new.append(row)
    return pd.concat([b, pd.DataFrame(new)], ignore_index=True)


def main():
    b = pd.read_csv(CW / 'buildings.csv', dtype=str).fillna('')
    moved = set()
    for f in ('housing_units.csv', 'place_parts.csv'):
        t = pd.read_csv(CW / f, dtype=str).fillna('')
        moved |= set(t['from_building_key']) - {''}
    missing = moved - set(b['building_key'])
    if missing:
        raise SystemExit(f'from_building_key not in buildings.csv: {sorted(missing)}')
    b = b[~b['building_key'].isin(moved)].copy()
    b = add_osm(b)

    b['kind'] = b['spi_structure_type'].map(
        lambda t: 'other structure' if t in OTHER_STRUCTURE else 'building')
    fac = pd.read_csv(CW / 'facilities.csv', dtype=str).fillna('')
    fac = fac[fac['facility_key'] != '']
    names = {(r.cdcr_code, r.name_as_written): r.facility_key for r in fac.itertuples()}
    fk = b.apply(facility, axis=1, result_type='expand', args=(names,))
    b['facility_key'], b['facility_source'] = fk[0], fk[1]
    b['group_row'] = b.apply(group_row, axis=1)
    b['split_from'] = ''
    b['stories'] = ''
    b = b.rename(columns={'building_key': 'place_key', 'building': 'place',
                          'building_name': 'place_name'})
    cols = ['place_key', 'cdcr_code', 'place', 'place_name', 'kind', 'aliases', 'placeholder',
            'facility_key', 'facility_source', 'group_row', 'split_from', 'use', 'program',
            'beds', 'year_built', 'stories', 'sqft', 'spi_structure_type',
            'spi_structure_number', 'spi_agency_structure_no', 'spi_real_property_number',
            'conflicts', 'n_sources', 'sources']
    b[cols].to_csv(CW / 'places.csv', index=False)
    print(f'places.csv: {len(b)} rows ({len(moved)} inventory rows moved to units/parts); '
          f"{(b['kind'] == 'other structure').sum()} other structures, "
          f"{(b['group_row'] == 'yes').sum()} group rows, "
          f"{(b['facility_key'] != '').sum()} with a facility")


if __name__ == '__main__':
    main()
