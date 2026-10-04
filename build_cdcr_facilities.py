"""
Build data/cdcr_facilities.csv: one row per CDCR adult institution, joining
population, demographics, housing cooling, facility metadata, programs, health
care population, staffing, restricted housing and violent incidents.

The institution list and FEMA facility IDs come from crosswalk/institutions.csv.
Source files that use a different code for an institution (FSP for FOL, SQRC for
SQ, CCFW for CCWF) are mapped through the crosswalk's alias_codes column.

Usage:
    python3 build_cdcr_facilities.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent
SOURCES = REPO / 'sources'
DATA = REPO / 'data'
CROSSWALK = REPO / 'crosswalk' / 'institutions.csv'
OUT = DATA / 'cdcr_facilities.csv'

YEAR = 2025


def load_crosswalk():
    xw = pd.read_csv(CROSSWALK, dtype={'alias_codes': str})
    aliases = {}
    for code, alias_list in zip(xw['cdcr_code'], xw['alias_codes'].fillna('')):
        for alias in filter(None, (a.strip() for a in alias_list.split(';'))):
            aliases[alias] = code
    return xw, aliases


def population(aliases):
    """Mean monthly in-custody population for YEAR (CDCR Population Data Points dashboard)."""
    pop = pd.read_csv(DATA / 'cdcr_population_by_location.csv')
    pop['cdcr_code'] = pop['cdcr_code'].replace(aliases)
    return (
        pop[pop['year'] == YEAR]
        .groupby('cdcr_code')['in_custody'].mean().round(0)
        .rename(f'average_{YEAR}_population')
    )


def occupancy(aliases):
    """Mean monthly TPOP-1 "Percent Occupied" (population / design capacity) for YEAR."""
    tpop = pd.read_csv(DATA / 'tpop1_institutions.csv')
    tpop['cdcr_code'] = tpop['cdcr_code'].replace(aliases)
    tpop = tpop[tpop['report_date'].str.startswith(str(YEAR))]
    return (
        (tpop['pct_occupied'] / 100).groupby(tpop['cdcr_code']).mean().round(4)
        .rename(f'capacity_percent_{YEAR}')
    )


def clean_counts(df):
    """CDCR suppression rules: ** (<50) -> 25, * (<10) -> 5, (Blank) -> 0."""
    s = df['Population'].astype(str).str.replace(',', '').str.strip()
    s = s.replace('**', '25').replace('*', '5').replace(['(Blank)', 'nan', 'NaN', ''], '0')
    return df.assign(Population=pd.to_numeric(s, errors='coerce').fillna(0))


def average_counts(path, category, aliases):
    """Mean monthly count per institution and category, wide."""
    df = clean_counts(pd.read_csv(path))
    df['Location'] = df['Location'].astype(str).str.strip().replace(aliases)
    avg = df.groupby(['Location', category])['Population'].mean().reset_index()
    return avg.pivot(index='Location', columns=category, values='Population').fillna(0)


def demographics(pop, aliases):
    """Age, gender and race shares of the average population (CDCR Population Data Set)."""
    out = pd.DataFrame(index=pop.index)
    safe_pop = pop.where(pop > 0)

    age = average_counts(SOURCES / f'cdcr_in-custody-age_{YEAR}.csv', 'Age Group', aliases)
    b80 = ['80-84 Years', '85-89 Years', '90-94 Years', '95 and Older']
    b70 = ['70-74 Years', '75-79 Years']
    b60 = ['60-64 Years', '65-69 Years']
    b50 = ['50-54 Years', '55-59 Years']
    tiers = {
        'age_over_50_pct': b50 + b60 + b70 + b80,
        'age_over_55_pct': ['55-59 Years'] + b60 + b70 + b80,
        'age_50_59_pct': b50,
        'age_60_69_pct': b60,
        'age_70_79_pct': b70,
        'age_80plus_pct': b80,
    }
    for col, groups in tiers.items():
        counts = age[age.columns.intersection(groups)].sum(axis=1)
        out[col] = (counts.reindex(pop.index) / safe_pop).fillna(0)

    gender = average_counts(SOURCES / f'cdcr_in-custody-gender_{YEAR}.csv', 'Gender', aliases)
    for cat in gender.columns:
        name = f"gender_{str(cat).lower().replace(' ', '_').replace('/', '_').replace('-', '_')}_pct"
        share = (gender[cat].reindex(pop.index) / safe_pop).fillna(0).clip(0, 1)
        out[name] = share.where(share >= 0.001, 0)

    race = average_counts(SOURCES / f'cdcr_in-custody-race_{YEAR}.csv', 'Race', aliases)
    white = race['White'] if 'White' in race.columns else 0
    poc = race.drop(columns=['White'], errors='ignore').sum(axis=1)
    out['race_white_pct'] = (white.reindex(pop.index) / safe_pop).fillna(0)
    out['race_peopleofcolor_pct'] = (poc.reindex(pop.index) / safe_pop).fillna(0)

    # Facilities without a population (closed) carry no demographic shares
    return out.where(pop.notna())


def cooling(aliases):
    """Housing-unit cooling mix (CDCR Air Cooling Pilot Supplemental Report, Jan 2026)."""
    infra = pd.read_csv(SOURCES / 'air_cooling_infrastructure_dec2025.csv')
    infra['institution'] = infra['institution'].replace(aliases)
    n_hu = infra['n_housing_units']
    return pd.DataFrame({
        'n_housing_units': n_hu.values,
        'pct_hu_evaporative': (infra['hu_evaporative_cooling'] / n_hu).round(4).values,
        'pct_hu_mechanical': (infra['hu_mechanical_cooling'] / n_hu).round(4).values,
        'pct_hu_air_handlers': (infra['hu_air_handlers_only'] / n_hu).round(4).values,
    }, index=infra['institution'])


CONDITION_SYSTEMS = {
    'Air Cooling (Mechanical- A/C)': 'cond_cooling_mechanical_2026',
    'Air Cooling (Evaporative System)': 'cond_cooling_evaporative_2026',
    'Hydronic Loops': 'cond_hydronic_loops_2026',
    'Central Boiler Plant / Boilers': 'cond_boilers_2026',
    'Automated Controls - SCADA, BMS, BAS': 'cond_automated_controls_2026',
    'Emergency Electrical Distribution': 'cond_emergency_electrical_2026',
    'Roofs': 'cond_roofs_2026',
}

# Cooling systems rated in the condition assessment, and the matching housing-unit count
# in the Air Cooling report
COOLING_TYPES = {
    'mechanical': ('cond_cooling_mechanical_2026', 'hu_mechanical_cooling'),
    'evaporative': ('cond_cooling_evaporative_2026', 'hu_evaporative_cooling'),
}


def infrastructure(aliases):
    """Building size and bed types (Infrastructure Master Plan, May 2026, Appendix 1),
    and condition ratings of heat-related systems (Appendix 2)."""
    prof = pd.read_csv(SOURCES / 'infrastructure_plan_profiles_2026.csv')
    prof['institution'] = prof['institution'].replace(aliases)
    prof = prof.set_index('institution')
    out = prof[['building_sqft', 'cell_beds', 'dorm_beds']].copy()
    # Design capacity includes conservation camp beds at SCC, CIW and CMC, which no source
    # separates out, so square feet per bed is left blank there
    per_bed = (prof['building_sqft'] / prof['design_capacity_apr2026']).round(1)
    out['building_sqft_per_design_bed'] = per_bed.where(prof['conservation_camps'].isna())

    cond = pd.read_csv(SOURCES / 'condition_assessment_2026.csv', keep_default_na=False)
    cond['institution'] = cond['institution'].replace(aliases)
    cond = cond[cond['system'].isin(CONDITION_SYSTEMS)]
    ratings = cond.pivot(index='institution', columns='system', values='rating')
    ratings = ratings.rename(columns=CONDITION_SYSTEMS)[list(CONDITION_SYSTEMS.values())]

    # Cooling types rated at the institution but found in none of its housing units
    hu = pd.read_csv(SOURCES / 'air_cooling_infrastructure_dec2025.csv')
    hu['institution'] = hu['institution'].replace(aliases)
    hu = hu.set_index('institution').reindex(ratings.index)
    outside = pd.DataFrame({
        name: (ratings[rating_col] != 'N/A') & (hu[hu_col] == 0)
        for name, (rating_col, hu_col) in COOLING_TYPES.items()
    })
    ratings['cooling_types_outside_housing'] = outside.apply(
        lambda r: '; '.join(name for name in COOLING_TYPES if r[name]), axis=1).replace('', np.nan)

    rank = pd.read_csv(SOURCES / 'condition_assessment_rank_2026.csv')
    rank['institution'] = rank['institution'].replace(aliases)
    rank = rank.set_index('institution')['condition_rank'].rename('condition_rank_2026')
    return out.join(ratings, how='outer').join(rank)


def metadata():
    """Hand-reviewed facility metadata: opening year, planned closure, program flags."""
    meta = pd.read_csv(SOURCES / 'cdcr_manual_data.csv')
    meta['Acronym'] = meta['Acronym'].astype(str).str.strip()
    meta.columns = [c.lower() for c in meta.columns]
    return meta.set_index('acronym')


def sb601_programs(aliases):
    """Programs with operational capacity > 0 in any month of FY 2024-25 (SB 601 dashboard)."""
    sb = pd.read_csv(DATA / 'sb601_programs.csv', skiprows=1)
    sb.columns = ['institution', 'category', 'metric'] + list(sb.columns[3:])
    sb['institution'] = sb['institution'].replace(aliases)
    cap = sb[sb['metric'].str.endswith('- Operational Capacity')].copy()
    months = cap.columns[3:]
    for m in months:
        cap[m] = pd.to_numeric(cap[m].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    cap['program'] = cap['metric'].str.replace(r'\s*-\s*Operational Capacity$', '', regex=True).str.strip()
    cap = cap[cap[months].max(axis=1) > 0]
    lists = cap.groupby(['institution', 'category'])['program'].apply(lambda p: '; '.join(sorted(p)))
    out = pd.DataFrame(index=lists.index.get_level_values(0).unique())
    for label, col in [('Cognitive Behavioral Intervention', 'cognitive_behavioral_interventions'),
                       ('Rehabilitative Programs', 'rehabilitative_programs')]:
        out[col] = lists.xs(label, level='category') if label in lists.index.get_level_values(1) else np.nan
    return out


def cchcs(aliases):
    """YEAR averages of CCHCS Institution & Population Characteristics measures."""
    ipc = pd.read_csv(DATA / 'cchcs_ipc.csv')
    ipc['val'] = pd.to_numeric(ipc['value'].astype(str).str.replace('%', '').str.strip(), errors='coerce')
    ipc['institution'] = ipc['institution'].replace(aliases)
    measures = {
        'High Risk Priority 1': f'cchcs_high_risk_p1_pct_{YEAR}',
        'High Risk Priority 2': f'cchcs_high_risk_p2_pct_{YEAR}',
        'Medium Risk': f'cchcs_medium_risk_pct_{YEAR}',
        'Low Risk': f'cchcs_low_risk_pct_{YEAR}',
        'Mental Health EOP': f'cchcs_mental_health_eop_pct_{YEAR}',
        'Disability Placement Program (DPP) Patients': f'cchcs_dpp_pct_{YEAR}',
        'Patients 50 Years or Older': f'cchcs_age_over_50_pct_{YEAR}',
        'Specialized Health Care Beds': f'cchcs_specialized_beds_{YEAR}',
    }
    sel = ipc[ipc['month'].str.endswith(str(YEAR)) & ipc['measure'].isin(measures)]
    wide = sel.groupby(['institution', 'measure'])['val'].mean().round(1).unstack()
    return wide.rename(columns=measures)[list(measures.values())]


def staffing(aliases):
    """YEAR average SCO headcount: state staff (CDCR + CCHCS) and PIA incarcerated workers."""
    sco = pd.read_csv(DATA / 'sco_staffing_avg.csv')
    sco['cdcr_code'] = sco['cdcr_code'].replace(aliases)
    state = sco[~sco['is_pia']].groupby('cdcr_code')['total'].sum().round(1)
    pia = sco[sco['is_pia']].groupby('cdcr_code')['total'].sum().round(1)
    return pd.DataFrame({f'sco_state_staff_{YEAR}': state, f'sco_incarcerated_staff_{YEAR}': pia})


def restricted_housing(aliases):
    """Mean of the twelve monthly % in restricted housing for YEAR (STA429 reports)."""
    rh = pd.read_csv(DATA / 'restricted_housing.csv')
    rh['cdcr_code'] = rh['cdcr_code'].replace(aliases)
    rh = rh[rh['data_month'].str.startswith(str(YEAR))]
    return rh.groupby('cdcr_code')['pct_in_rhu'].mean().round(4).rename(f'rhu_pct_{YEAR}')


def violent_incidents(aliases):
    """Total violent incidents / calendar years with reported months (2021-2025)."""
    vi = pd.read_csv(DATA / 'cdcr_violent_incidents_by_facility.csv')
    vi['facility'] = vi['facility'].replace(aliases)
    g = vi.groupby('facility').agg(total=('violent_incidents', 'sum'), n_years=('year', 'nunique'))
    return (g['total'] / g['n_years']).round(1).rename('avg_annual_violent_incidents')


def main():
    xw, aliases = load_crosswalk()
    df = xw.rename(columns={'fema_facilityid': 'facilityid', 'institution_name': 'name'})
    df = df[['facilityid', 'cdcr_code', 'name']].set_index('cdcr_code')

    pop = population(aliases).reindex(df.index)
    df = df.join(pop).join(occupancy(aliases))
    df = df.join(demographics(pop, aliases))
    df = df.join(cooling(aliases))
    df = df.join(infrastructure(aliases))
    df = df.join(metadata())
    df = df.join(sb601_programs(aliases))
    df = df.join(cchcs(aliases))
    df = df.join(staffing(aliases))
    df = df.join(violent_incidents(aliases))
    df = df.join(restricted_housing(aliases))

    df = df.reset_index()
    first = ['facilityid', 'cdcr_code', 'name']
    df = df[first + [c for c in df.columns if c not in first]]
    df.to_csv(OUT, index=False)
    print(f'Wrote {len(df)} institutions to {OUT.relative_to(REPO)}')


if __name__ == '__main__':
    main()
