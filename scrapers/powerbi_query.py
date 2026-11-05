"""
Reads a public Power BI report through its query endpoint, the same one the report's page uses.
No browser and no scrolling, and results don't depend on the page's layout.
"""

import base64
import gzip
import json
import urllib.request

API = "https://wabi-us-gov-iowa-api.analysis.usgovcloudapi.net/public/reports/"
WINDOW = 30000


def post(url, key, body=None):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode() if body else None,
        headers={"X-PowerBI-ResourceKey": key, "Content-Type": "application/json",
                 "Accept-Encoding": "gzip"})
    raw = urllib.request.urlopen(req, timeout=300).read()
    try:
        raw = gzip.decompress(raw)
    except OSError:
        pass
    return json.loads(raw)


def decode(res):
    """Rows from a Power BI DSR response (value dictionaries, repeat and null bitmasks)."""
    ds = res["results"][0]["result"]["data"]["dsr"]["DS"][0]
    if not ds.get("IC", True):
        raise RuntimeError("Power BI returned a truncated result")
    dicts = ds.get("ValueDicts", {})
    rows, prev, schema = [], None, None
    for ph in ds["PH"]:
        for dms in ph.values():
            for dm in dms:
                schema = dm.get("S", schema)
                if not any(k in dm for k in ("C", "R", "Ø")):
                    row = [dm.get(s["N"]) for s in schema]
                else:
                    vals, repeat, null, row = iter(dm.get("C", [])), dm.get("R", 0), dm.get("Ø", 0), []
                    for i, s in enumerate(schema):
                        if repeat >> i & 1:
                            row.append(prev[i])
                        elif null >> i & 1:
                            row.append(None)
                        else:
                            v = next(vals)
                            row.append(dicts[s["DN"]][v] if "DN" in s and isinstance(v, int) else v)
                prev = row
                rows.append(row)
    return rows


def column(source, prop):
    return {"Column": {"Expression": {"SourceRef": {"Source": source}}, "Property": prop},
            "Name": f"{source}.{prop}"}


def total(source, prop):
    return {"Aggregation": {"Expression": {"Column": {"Expression": {"SourceRef": {"Source": source}},
                                                      "Property": prop}}, "Function": 0},
            "Name": f"Sum({source}.{prop})"}


def equals(source, prop, literal):
    return {"Condition": {"In": {
        "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": source}}, "Property": prop}}],
        "Values": [[{"Literal": {"Value": literal}}]]}}}


class Report:
    """A published report, from the r= value in its public URL."""

    def __init__(self, resource):
        self.key = json.loads(base64.b64decode(resource + "=="))["k"]
        model = post(API + self.key + "/modelsAndExploration?preferReadOnlySession=true", self.key)
        self.exploration = model["exploration"]
        self.model_id = model["models"][0]["id"]
        self.dataset = model["models"][0]["dbName"]
        self.report_id = model["exploration"]["report"]["objectId"]

    def query(self, sources, select, where=()):
        """Rows for `select`, grouped by its columns. `sources` maps source names to entities."""
        q = {"Version": 2,
             "From": [{"Name": n, "Entity": e, "Type": 0} for n, e in sources.items()],
             "Select": list(select), "Where": list(where)}
        body = {"version": "1.0.0", "modelId": self.model_id, "cancelQueries": [], "queries": [{
            "Query": {"Commands": [{"SemanticQueryDataShapeCommand": {"Query": q, "Binding": {
                "Primary": {"Groupings": [{"Projections": list(range(len(q["Select"])))}]},
                "DataReduction": {"DataVolume": 4, "Primary": {"Window": {"Count": WINDOW}}},
                "Version": 1}}}]},
            "QueryId": "",
            "ApplicationContext": {"DatasetId": self.dataset, "Sources": [{"ReportId": self.report_id}]}}]}
        return decode(post(API + "querydata?synchronous=true", self.key, body))
