# Facilities summary

One row for each of the 34 adult institutions, summarizing the other topic folders for the latest calendar year with all twelve months published.

## Files

| File | One row is | Coverage | Source |
| :--- | :--- | :--- | :--- |
| `facilities_summary.csv` | An institution | `data_year` 2025 | Built from the tables below by `build_cdcr_facilities.py` |
| `cdcr_manual_data.csv` | An institution: year opened, planned closure, program participation | As of 2026 | LAO (2020) and online documentation, transcribed by hand |

## Caveats

- Annual figures are for `data_year` except where a field says otherwise. Condition ratings come from one assessment, whose year is in `condition_source_year`.
- Demographic shares are the mean monthly count in each group divided by `average_population`. Suppressed counts are counted as 5 (`*`, under 10) and 25 (`**`, under 50), and blanks as 0. These estimates exist only in this table; the source tables in `population/` keep the values as published.
- Institutions without a population in the data year have blank population and demographic fields.
- Housing units with more than one cooling type are counted under each, so the three `pct_hu_` shares can sum to slightly more than 1.
- Each condition rating covers the whole institution, including non-housing buildings, so a rated cooling system may not serve any housing unit.

## Fields

| Column | Meaning |
| :--- | :--- |
| `facilityid` | FEMA facility ID. Joins to the facility list in [ca_prison_climate_justice](https://github.com/mbecica/ca_prison_climate_justice) for address, coordinates, security level, and boundaries. |
| `data_year` | Calendar year of the annual figures. |
| `average_population` | Mean of the monthly in-custody counts. |
| `design_capacity` | Design capacity in the last TPOP-1 report of `data_year`. |
| `capacity_percent` | `average_population` ÷ `design_capacity`, as a 0–1 value. |
| `age_over_50_pct`, `age_over_55_pct`, `age_50_59_pct`, `age_60_69_pct`, `age_70_79_pct`, `age_80plus_pct` | Share of the population in each age group. |
| `gender_female_pct`, `gender_male_pct` | Share of the population by gender. |
| `race_white_pct`, `race_peopleofcolor_pct` | Share of the population recorded as White, and as any other race. |
| `n_housing_units` | Active housing units as of December 2025. |
| `pct_hu_mechanical`, `pct_hu_evaporative`, `pct_hu_air_handlers` | Share of housing units with mechanical cooling, evaporative cooling, and air handlers only. |
| `building_sqft` | Square feet of buildings at the institution, all uses. |
| `cell_beds`, `dorm_beds` | Design capacity split into cell and dormitory beds, as of April 2026. |
| `building_sqft_per_design_bed` | `building_sqft` ÷ design capacity. Blank where design capacity includes conservation camp beds, which no source separates. |
| `condition_source_year` | Year of the assessment behind the `cond_` columns and `condition_rank`. |
| `cond_cooling_mechanical`, `cond_cooling_evaporative`, `cond_hydronic_loops`, `cond_boilers`, `cond_automated_controls`, `cond_emergency_electrical`, `cond_roofs` | Condition rating of the system: Plus, Good, Fair, Poor, Failing, or N/A. |
| `cooling_types_outside_housing` | Cooling types with a condition rating at the institution but in none of its housing units. |
| `condition_rank` | Overall rank across all 45 rated systems, 1 (worst) to 31 (best). |
| `year_opened`, `year_opened_notes` | Year the institution opened as a state facility, with notes on prior site uses or source differences. |
| `planned_closure`, `california_model_facility`, `cdcr_air_cooling_pilot` | `Yes` if the institution is marked for closure, is part of the California Model, or is in the Air Cooling Pilot. |
| `infrastructure_priority` | `Yes` if the May 2026 Infrastructure Master Plan slates the institution for major capital projects in the next five years. |
| `cognitive_behavioral_interventions`, `rehabilitative_programs` | Semicolon-separated programs with operational capacity in any month of Jul 2025 – Jun 2026. |
| `cchcs_high_risk_p1_pct`, `cchcs_high_risk_p2_pct`, `cchcs_medium_risk_pct`, `cchcs_low_risk_pct`, `cchcs_mental_health_eop_pct`, `cchcs_dpp_pct`, `cchcs_age_over_50_pct` | Monthly means of CCHCS's percentages, on 0–100, using total institution population as the denominator. Risk tiers are defined in [`health_care/`](../health_care/). |
| `cchcs_specialized_beds` | Monthly mean of specialized health care beds. |
| `sco_state_staff` | Mean active state employees across the data year's SCO reports, including CCHCS staff where SCO reports them separately. |
| `sco_incarcerated_staff` | Mean Prison Industry Authority workers across the same reports. Blank if the institution has no such operation. |
| `avg_annual_violent_incidents` | Total violent incidents, 2021–2025, divided by the number of years with reported data. Doesn't follow `data_year`. |
| `rhu_pct` | Mean of the monthly shares of the population in restricted housing. 0 where an institution reports no restricted housing units. |

## Provenance

| Columns | Table | Covered through |
| :--- | :--- | :--- |
| Population, demographics, capacity | `population/cdcr_population_by_location.csv`, `cdcr_in-custody-{age,gender,race}.csv`, `tpop1_institutions.csv` | Data year |
| Cooling | `heat/cooling/air_cooling_infrastructure_dec2025.csv` | Dec 2025 |
| Buildings and condition | `buildings/infrastructure_plan_profiles_2026.csv`, `condition_assessment_2026.csv`, `condition_assessment_rank_2026.csv` | 2026 |
| Facility characteristics | `cdcr_manual_data.csv` | 2026 |
| Programs | `operations/sb601_programs.csv` | Jun 2026 |
| Health care | `health_care/cchcs_ipc.csv` | Data year |
| Staffing | `staffing/sco_staffing_avg.csv` | Data year |
| Violent incidents, restricted housing | `operations/cdcr_violent_incidents_by_facility.csv`, `restricted_housing.csv` | Data year |

To rebuild: `python3 build_cdcr_facilities.py`. `YEAR` at the top of the script sets `data_year`.

## References

Legislative Analyst's Office. (2020). *Effectively Managing State Prison Infrastructure* (Report 4186). https://lao.ca.gov/reports/2020/4186/prison-infrastructure-022820.pdf

Sources of the joined tables are listed in each topic's README.
