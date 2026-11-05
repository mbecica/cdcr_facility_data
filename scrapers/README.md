# Scrapers

Each topic README in `data/` says which script produces each table and where its inputs go.

## Setup

- **Dashboard scrapers (`fetch_*.js`):** `npm install`, then `npx playwright install chromium`. They drive live Power BI dashboards in a visible browser, so they need a display, and they can break when a dashboard's layout changes.
- **Dashboard query scripts (`fetch_sb601_*.py`, `fetch_cchcs_tables.py`, `fetch_cdcr_recidivism_los.py`):** these read the dashboard's public query endpoint and need no browser.
- **Python scripts:** pandas, numpy, and pdfplumber. `extract_housing_cooling_types.py`, `extract_reuters_msr.py`, and `index_reuters_heat_pages.py` also need `tesseract`.
- **PDFs** aren't stored in the repository. Download them into the `sources/` folder the topic README names, then run the extractor.

## Running

```
node scrapers/fetch_cdcr_demographics.js
python3 scrapers/extract_tpop1.py
python3 build_cdcr_facilities.py
```

After updating any table the main table uses, rerun `build_cdcr_facilities.py`. Some scrapers have a `LATEST_YEAR`, `FISCAL_YEAR`, or file list near the top of the script to change at refresh.

`tidy.js` and `institution_codes.py` hold the output formatting and institution code lookups the scripts share. `powerbi.js` and `powerbi_query.py` hold the Power BI browser and query code.
