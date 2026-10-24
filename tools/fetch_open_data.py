#!/usr/bin/env python3
"""Fetch Boston open-data violations and approved permits once into data/raw/.

Pages through data.boston.gov CKAN datastore_search_sql, selecting only the
columns the design needs (no street addresses), and records provenance in
MANIFEST.json including each dataset's CKAN license. Idempotent: exits if the
outputs already exist unless --force.
"""
import argparse
import csv
import datetime as dt
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://data.boston.gov/api/3/action"
RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
PAGE = 10000
SLEEP_S = 0.5
UA = "zoning-auditor-agent/1.0 (hackathon prototype; stdlib urllib)"

DATASETS = {
    "violations": {
        "resource": "800a2663-1d6a-46e7-9356-bedb70f5332c",
        "columns": ["case_no", "status_dttm", "status", "code", "value",
                    "description", "violation_city", "violation_zip", "ward"],
        "filter": "status_dttm >= '2024-01-01'",
        # case_no is not unique; these columns together make the order stable
        # enough for OFFSET paging.
        "order_by": ["case_no", "status_dttm", "code", "value"],
        "page_url": "https://data.boston.gov/dataset/building-and-property-violations1",
    },
    "permits": {
        "resource": "6ddcd912-32a0-43df-9908-63574f8c7e77",
        "columns": ["permitnumber", "worktype", "permittypedescr", "description",
                    "declared_valuation", "total_fees", "issued_date",
                    "expiration_date", "status", "occupancytype", "sq_feet",
                    "zip", "ward"],
        "filter": "issued_date >= '2024-01-01'",
        "order_by": ["permitnumber"],  # unique key: exact keyset-grade stability
        "page_url": "https://data.boston.gov/dataset/approved-building-permits",
    },
}


def api_get(action: str, params: dict) -> dict:
    url = f"{API}/{action}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        payload = json.load(r)
    if not payload.get("success"):
        raise RuntimeError(f"CKAN {action} failed: {payload.get('error')}")
    return payload["result"]


def sql_template(cfg: dict) -> str:
    cols = ", ".join(cfg["columns"])
    order = ", ".join(cfg["order_by"])
    return (f'SELECT {cols} FROM "{cfg["resource"]}" '
            f'WHERE {cfg["filter"]} ORDER BY {order} '
            f'LIMIT {{limit}} OFFSET {{offset}}')


def fetch(cfg: dict) -> list[dict]:
    tmpl = sql_template(cfg)
    rows: list[dict] = []
    while True:
        recs = api_get("datastore_search_sql",
                       {"sql": tmpl.format(limit=PAGE, offset=len(rows))})["records"]
        rows.extend(recs)
        # PAGE is below CKAN's per-response row cap, so only the last page is short.
        if len(recs) < PAGE:
            return rows
        time.sleep(SLEEP_S)


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> int:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)
    return len(rows)


def license_of(resource: str) -> dict:
    pkg_id = api_get("resource_show", {"id": resource})["package_id"]
    pkg = api_get("package_show", {"id": pkg_id})
    return {"license_title": pkg.get("license_title"),
            "license_id": pkg.get("license_id"),
            "package": pkg.get("name")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true",
                    help="refetch even if outputs already exist")
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    manifest_path = RAW / "MANIFEST.json"
    outputs = {name: RAW / f"{name}.csv" for name in DATASETS}
    if not args.force and manifest_path.exists() and all(p.exists() for p in outputs.values()):
        print(f"Outputs already present in {RAW} (use --force to refetch):")
        for p in [*outputs.values(), manifest_path]:
            print(f"  {p}")
        return 0

    manifest = {}
    for name, cfg in DATASETS.items():
        print(f"Fetching {name} ...", flush=True)
        rows = fetch(cfg)
        n = write_csv(outputs[name], cfg["columns"], rows)
        lic = license_of(cfg["resource"])
        manifest[name] = {
            "sql_template": sql_template(cfg),
            "row_count": n,
            "downloaded_at_utc": dt.datetime.now(dt.UTC).isoformat(),
            "dataset_page_url": cfg["page_url"],
            "resource_id": cfg["resource"],
            "page_size": PAGE,
            **lic,
        }
        print(f"  {name}: {n} rows -> {outputs[name]} "
              f"(license: {lic['license_title']})", flush=True)

    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
