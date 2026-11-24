"""Build data/buildings/locations/footprint_places.csv: links building footprints to places or place sets.
Run from the repo root. Needs shapely. Run after build_building_heights.py and build_places.py.
osm_name rows: OSM point inside the footprint AND the OSM name/code matches one place. set rows: equal counts only."""
import csv,json,re,sys,collections
from shapely.geometry import shape,Point
rd=lambda p:list(csv.DictReader(open(p)))
FP=[(f['properties'],shape(f['geometry'])) for f in json.load(open('data/buildings/building_footprints.geojson'))['features']]
PL={r['place_key']:r for r in rd('data/buildings/locations/places.csv')}
SQ={'Adjustment Center / Death Row Unit 2':'SQ-20','East Cell Block':'SQ-24','North Cell Block / Death Row Unit 1':'SQ-23','South Cell Block':'SQ-28','West Cell Block':'SQ-30','Gymnasium':'SQ-33','Mattress Manufacturing':'SQ-39','Dining Halls':'SQ-26'}
def cmc():
    d=collections.defaultdict(set)
    for k,r in PL.items():
        if r['cdcr_code']!='CMC' or not r['spi_structure_number'] and not r['place_name'].startswith('Dormitory'): continue
        n=r['place_name'].upper()
        for m in re.finditer(r'BLDG\.? ([A-Z]{1,2}(?: ?- ?\d|\d)?)\b',n): d[m.group(1).replace(' ','').replace('-','')].add(k)
        for m in re.finditer(r'\(([A-Z0-9]{1,3})\)',n): d[m.group(1)].add(k)
        m=re.match(r'\d+-([A-Z]{1,2}\d?)$',r['spi_agency_structure_no'] or '')
        if m: d[m.group(1)].add(k)
    return d
CM=cmc(); out=[]; miss=[]
for o in rd('sources/openstreetmap/osm_cdcr_buildings.csv'):
    c,n=o['cdcr_code'],o['name']
    if not n or c not in('CMC','COR','SQ'): continue
    key=set()
    if c=='CMC':
        m=re.search(r'\(([^()]+)\)\s*$',n); code=(m.group(1) if m else n if re.fullmatch('[A-Z]{1,2}',n) else '').replace('-','').replace(' ','')
        key={'M':{'CMC-5'},'N':{'CMC-6'}}.get(code) or CM.get(code,set());  # SPI number and name disagree; use the name
        basis='OSM name carries the SPI building letter or number'
    elif c=='COR':
        m=re.fullmatch(r'(\d[ABC])0?(\d)',n); k=m and f'COR-{m.group(1)}0{m.group(2)}'; key={k} if k in PL else set(); basis='OSM name is the SPI building code'
    else: k=SQ.get(n); key={k} if k else set(); basis='OSM name and SPI name match'
    p=Point(float(o['lon']),float(o['lat'])); hit=[d for d,g in FP if d['cdcr_code']==c and g.contains(p)]
    note='SPI agency number and name disagree on M/N; linked by the SPI name' if c=='CMC' and code in 'MN' and code else ''
    if c=='COR' and len(key)==1 and not hit:  # V-shaped 180 units: the OSM point falls in the notch
        near=sorted(((g.distance(p)*95000,d) for d,g in FP if d['cdcr_code']==c),key=lambda x:x[0])
        if near[0][0]<=15 and near[1][0]>30 and near[0][1]['is_housing']=='yes': hit=[near[0][1]]; note=f'OSM point is about {near[0][0]:.0f} m outside this V-shaped footprint; next nearest is about {near[1][0]:.0f} m away'
    if len(key)==1 and len(hit)==1:
        k=min(key); out.append(dict(cdcr_code=c,footprint_id=hit[0]['footprint_id'],place_key=k,set_key='',relation='same as building',basis=basis,source=f"OSM {o['osm_type']}/{o['osm_id']}",source_name=n,place_name=PL[k]['place_name'],note=note))
    else: miss.append(dict(cdcr_code=c,osm_id=o['osm_id'],osm_name=n,places=';'.join(sorted(key)),footprints=';'.join(d['footprint_id'] for d in hit),why='no place match' if not key else 'several places (conflict)' if len(key)>1 else 'point not inside one footprint'))
cnt=collections.Counter(r['footprint_id'] for r in out)
for r in out:
    if cnt[r['footprint_id']]>1: r['relation']='footprint holds several places'
sets=collections.defaultdict(list)
for r in rd('data/buildings/locations/place_sets.csv'): sets[r['set_key']].append(r['place_key'])
for c,keys,proto in(('HDSP',['HDSP-set-A','HDSP-set-B'],'270_housing_unit'),('HDSP',['HDSP-set-C','HDSP-set-D'],'180_housing_unit'),('KVSP',['KVSP-set-180'],'180_housing_unit'),('SVSP',['SVSP-set-270'],'270_housing_unit'),('SVSP',['SVSP-set-180'],'180_housing_unit')):
    f=[d['footprint_id'] for d,_ in FP if d['cdcr_code']==c and d['housing_prototype']==proto]; ps=[p for k in keys for p in sets[k]]
    print(keys,proto,len(f),'footprints',len(ps),'places')
    if len(f)!=len(ps): continue
    for k in keys:
        for x in f: out.append(dict(cdcr_code=c,footprint_id=x,place_key='',set_key=k,relation='one of the set' if len(keys)==1 else 'one of the union of '+' + '.join(keys),basis=f'count match: {len(f)} {proto} footprints = {len(ps)} places',source='building_heights.csv + place_sets.csv',source_name='',place_name='',note='no source says which footprint is which place'+('' if len(keys)==1 else ', or which yard')))
def w(p,rows):
    with open(p,'w',newline='') as f: x=csv.DictWriter(f,fieldnames=rows[0].keys(),lineterminator='\n'); x.writeheader(); x.writerows(rows)
D='notes/building_heights_pilot/bridge/'; w('data/buildings/locations/footprint_places.csv',out); w(D+'osm_unmatched.csv',miss)
H={d['footprint_id']:d for d,_ in FP}
for c in('CMC','COR','SQ'):
    m=[r for r in out if r['cdcr_code']==c]; print(c,len(m),'rows',sum(H[r['footprint_id']]['is_housing']=='yes' for r in m),'on housing footprints;',sum(r['cdcr_code']==c for r in miss),'unmatched')
print('CHECK housing place on non-housing footprint, or reverse:')
for r in out:
    if r['place_key']:
        h='HOUS' in r['place_name'].upper() or PL[r['place_key']]['spi_structure_type']=='DORMITORY'
        if h!=(H[r['footprint_id']]['is_housing']=='yes'): print('  ',r['footprint_id'],r['source_name'],r['place_key'],r['place_name'],H[r['footprint_id']]['housing_prototype'])
dup=[k for k,v in collections.Counter(r['place_key'] for r in out if r['place_key']).items() if v>1]; print('places on 2+ footprints',dup)
for r in miss:
    if r['why']!='no place match': print('  miss',r)
print('SQ/COR no place:',[r['osm_name'] for r in miss if r['cdcr_code']!='CMC' and r['why']=='no place match'])
