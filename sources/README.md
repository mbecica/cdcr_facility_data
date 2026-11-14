# Sources

Raw inputs to the tables in `data/`, as published. Most are large PDFs and aren't stored in this repository; each topic README in `data/` links to the source and names the folder it goes in.

[`powerbi_query_api.md`](powerbi_query_api.md) describes how to read CDCR's Power BI dashboards through their query endpoint, without a browser.

`sb601_open_data/` is stored here: the SB 601 data download, data dictionary, and counting rules from [data.ca.gov](https://data.ca.gov/dataset/sb601-reporting).

`imagery/naip_2024_rgb/` stores JPEG-compressed RGB GeoTIFF tiles for all 34 adult CDCR institutions (`2024` USDA NAIP aerials clipped to the institutional boundary + 300 m buffer) used for [`scrapers/building_heights/`](../scrapers/building_heights/README.md).

`openstreetmap/osm_cdcr_buildings.csv` stores raw OpenStreetMap `building=*` elements extracted via Overpass inside CDCR institution RAPT boundaries (`1,595` features across `32` institutions; `193` named buildings concentrated in `CMC`, `COR`, and `SQ`, plus `CMF` and `PBSP`).
