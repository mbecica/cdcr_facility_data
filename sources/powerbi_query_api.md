# Reading CDCR's Power BI dashboards without a browser

CDCR and CCHCS publish their dashboards as public Power BI reports. Each page loads its numbers from a query endpoint that needs no login, and the same requests work from a script. This returns the values directly, with no scrolling and no dependence on the page's layout.

Microsoft doesn't document this endpoint for outside use. It can change without notice, so check results against the dashboard on screen.

## Reports

The `r=` value comes from the report's public URL.

| Dashboard | `r=` value | Used by |
| :--- | :--- | :--- |
| SB 601 | `eyJrIjoiYzlkM2RiNWEtZDRjMi00ODllLTg2YzEtZjYyM2MwMjA5NmQ0IiwidCI6IjA2NjI0NzdkLWZhMGMtNDU1Ni1hOGY1LWMzYmM2MmFhMGQ5YyJ9` | `fetch_sb601_tables.py`, `fetch_sb601_grievances.py` |
| CCHCS Health Care Services | `eyJrIjoiY2QyNzllZWItMmIxYi00NTk0LWI0OWQtNWEzMTkwYzA3NGE4IiwidCI6IjA2NjI0NzdkLWZhMGMtNDU1Ni1hOGY1LWMzYmM2MmFhMGQ5YyJ9` | `fetch_cchcs_tables.py` |
| Adult Recidivism | `eyJrIjoiNmRjOTkwMWEtYmVkMy00MTA1LWIxZDYtYzg4OTIzYjkxNTRlIiwidCI6IjA2NjI0NzdkLWZhMGMtNDU1Ni1hOGY1LWMzYmM2MmFhMGQ5YyJ9` | `fetch_cdcr_recidivism_los.py` |
| Population Data Points | `eyJrIjoiN2RjZmFjNzItMzI0Ni00M2IwLWJmZjgtNDgyMjUyMjVhOWMwIiwidCI6IjA2NjI0NzdkLWZhMGMtNDU1Ni1hOGY1LWMzYmM2MmFhMGQ5YyJ9` | Report loads; the scrapers here still use a browser |

## Requests

The `r=` value is base64 JSON. Its `k` field is the resource key, sent as a header on every request.

```
echo 'eyJrIjoiYzlkM2RiNWEtZDRjMi00ODllLTg2YzEtZjYyM2MwMjA5NmQ0IiwidCI6IjA2NjI0NzdkLWZhMGMtNDU1Ni1hOGY1LWMzYmM2MmFhMGQ5YyJ9' | base64 -d
```

The host is `https://wabi-us-gov-iowa-api.analysis.usgovcloudapi.net/public/reports/`.

| Request | Returns |
| :--- | :--- |
| `GET {key}/modelsAndExploration?preferReadOnlySession=true` | The model ID and dataset name, the report ID, and every page and visual |
| `POST conceptualschema` with `{"modelIds": [model_id], "userPreferredLocale": "en-US"}` | Every table, column, and measure in the model |
| `POST querydata?synchronous=true` | Query results |

Send `X-PowerBI-ResourceKey: {key}` and `Content-Type: application/json`.

## Running a query

`scrapers/powerbi_query.py` handles the requests and decodes the results. From the repository root, this gets statewide use-of-force incidents by report date from SB 601:

```python
import sys
sys.path.insert(0, "scrapers")
from powerbi_query import Report, column, equals, total

report = Report("eyJrIjoiYzlkM2RiNWEtZDRjMi00ODllLTg2YzEtZjYyM2MwMjA5NmQ0IiwidCI6IjA2NjI0NzdkLWZhMGMtNDU1Ni1hOGY1LWMzYmM2MmFhMGQ5YyJ9")
rows = report.query(
    {"s": "SB601"},
    [column("s", "Date"), total("s", "Value")],
    [equals("s", "Category", "'Use of Force (UOF)'")],
)
print(rows[:3])
```

`sources` names the tables, `select` lists columns and sums, and `where` lists filters. Results are grouped by the selected columns.

## Matching what a dashboard shows

Copy the visual's own query. In the `modelsAndExploration` response, `exploration.sections` holds the report's pages. On each page, every item in `visualContainers` has:

- `config`, a JSON string. `singleVisual.prototypeQuery` is the visual's query: its tables, columns, and measures.
- `filters`, also a JSON string in most reports. A filter with a `filter` key has conditions to add to `where`.

To select a report measure rather than a column:

```python
{"Measure": {"Expression": {"SourceRef": {"Source": "k"}}, "Property": "3 Year Return Rate"},
 "Name": "Key Measures.3 Year Return Rate"}
```

## What to watch for

- **Sum values unless the visual doesn't.** Selecting `Value` as a plain column groups by it, so identical rows collapse into one. Selecting a sum matches the dashboard's table.
- **Results are capped.** The window here is 30,000 rows, and `powerbi_query.py` raises an error if a result is truncated. Query one date or month at a time.
- **Slicers can hide data.** A slicer's filter may leave out years the model still holds, and a report's calendar table may start later than its data. SB 601's slicers begin at FY 2022-23, but its `Date` column goes back to 2019. Querying the fact table's own date reaches all of it.
- **Dimension tables tidy the names.** SB 601's `dimCategory` folds older spellings into one published category. Use them to get the names on the dashboard.
- **Literals are typed.** Strings are `'text'`, dates are `datetime'2025-07-31T00:00:00'`, and whole numbers are `179L`. Rates can come back as strings ending in `D`, such as `0.647D`.
- **"Most Recent" can be a slicer option.** CCHCS's month slicer lists it in place of the latest month. Use `Dashboard Month MMM yyyy` for the real label.
- **Filters can reuse a source name.** Each visual filter names its own sources, and two may use the same name for different tables, so rename them before combining. `fetch_cdcr_recidivism_los.py` does this.
- **Errors can look like success.** A bad query can return HTTP 200 with an `odata.error` under `DataShapes` and no `DS` key. Its message usually names the problem.
- **Some rows have no date.** Filtering on a date leaves those out, so check for nulls.

## Use

Query the aggregate values and measures a dashboard shows. A model's schema can list more detailed fields than its pages display, including individual-level ones, and CDCR suppresses small counts on its dashboards to prevent re-identification. Those limits still apply here.

Cite the dashboard as the source, and state when values came from outside the range its slicers offer.
