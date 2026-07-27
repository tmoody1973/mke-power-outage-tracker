#!/usr/bin/env python3
"""
Turn the append-only data/history.ndjson log into map-ready outputs:

- data/outage_events.geojson  -- one point per distinct outage event
                                   (deduped by event_id), with first/last
                                   seen timestamps and peak customers out.
- data/outage_events.csv      -- same data, flat CSV for spreadsheets/DuckDB.
- data/by_zip.csv             -- outage-event counts and total
                                   customer-impact per ZIP code, for
                                   joining against Census/ACS demographic
                                   data later.
- data/summary.json           -- small rollup used by the viewer page.

Run after every fetch_outages.py run (see .github/workflows/scrape.yml).
Safe to re-run any time; it always rebuilds from history.ndjson.
"""

import csv
import json
import os
from collections import defaultdict

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
HISTORY_PATH = os.path.join(DATA_DIR, "history.ndjson")
LATEST_PATH = os.path.join(DATA_DIR, "latest.json")
EVENTS_GEOJSON_PATH = os.path.join(DATA_DIR, "outage_events.geojson")
EVENTS_CSV_PATH = os.path.join(DATA_DIR, "outage_events.csv")
BY_ZIP_CSV_PATH = os.path.join(DATA_DIR, "by_zip.csv")
SUMMARY_PATH = os.path.join(DATA_DIR, "summary.json")


def load_history():
    if not os.path.exists(HISTORY_PATH):
        return []
    rows = []
    with open(HISTORY_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_active_ids():
    if not os.path.exists(LATEST_PATH):
        return set()
    with open(LATEST_PATH) as f:
        latest = json.load(f)
    active = set()
    # Recompute the same event_id logic inline to avoid importing across
    # files in a way that complicates the GitHub Actions step; keep it
    # simple/duplicated on purpose.
    import hashlib

    for event in latest.get("events", []):
        lat = round(float(event.get("Latitude") or 0), 4)
        lon = round(float(event.get("Longitude") or 0), 4)
        off_time = event.get("OffTime") or ""
        key = f"{lat}|{lon}|{off_time}"
        active.add(hashlib.sha1(key.encode("utf-8")).hexdigest()[:16])
    return active


def build(rows, active_ids):
    events = {}
    for row in rows:
        eid = row["event_id"]
        e = events.get(eid)
        if e is None:
            e = {
                "event_id": eid,
                "latitude": row.get("latitude"),
                "longitude": row.get("longitude"),
                "off_time": row.get("off_time"),
                "first_seen_at": row["captured_at"],
                "last_seen_at": row["captured_at"],
                "max_affected_customers": row.get("affected_customers") or 0,
                "cause": row.get("cause"),
                "city": row.get("city"),
                "county": row.get("county"),
                "zip": row.get("zip"),
                "region": row.get("region"),
                "observations": 0,
            }
            events[eid] = e
        e["last_seen_at"] = max(e["last_seen_at"], row["captured_at"])
        e["first_seen_at"] = min(e["first_seen_at"], row["captured_at"])
        cust = row.get("affected_customers") or 0
        if cust > e["max_affected_customers"]:
            e["max_affected_customers"] = cust
        # keep the most recently observed non-null cause/city/zip
        if row["captured_at"] == e["last_seen_at"]:
            for k in ("cause", "city", "county", "zip", "region"):
                if row.get(k):
                    e[k] = row.get(k)
        e["observations"] += 1

    for e in events.values():
        e["still_active"] = e["event_id"] in active_ids

    return list(events.values())


def write_geojson(events):
    features = []
    for e in events:
        if e.get("latitude") is None or e.get("longitude") is None:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [e["longitude"], e["latitude"]],
                },
                "properties": {k: v for k, v in e.items() if k not in ("latitude", "longitude")},
            }
        )
    geojson = {"type": "FeatureCollection", "features": features}
    with open(EVENTS_GEOJSON_PATH, "w") as f:
        json.dump(geojson, f)


def write_csv(events):
    if not events:
        # still write an empty file with headers for consistency
        fieldnames = [
            "event_id", "latitude", "longitude", "off_time", "first_seen_at",
            "last_seen_at", "max_affected_customers", "cause", "city",
            "county", "zip", "region", "observations", "still_active",
        ]
    else:
        fieldnames = list(events[0].keys())
    with open(EVENTS_CSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for e in events:
            writer.writerow(e)


def write_by_zip(events):
    agg = defaultdict(lambda: {"event_count": 0, "total_customer_impact": 0})
    for e in events:
        z = e.get("zip") or "unknown"
        agg[z]["event_count"] += 1
        agg[z]["total_customer_impact"] += e.get("max_affected_customers") or 0
    with open(BY_ZIP_CSV_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["zip", "event_count", "total_customer_impact"])
        for z, vals in sorted(agg.items(), key=lambda kv: -kv[1]["total_customer_impact"]):
            writer.writerow([z, vals["event_count"], vals["total_customer_impact"]])


def write_summary(events):
    total_events = len(events)
    active = sum(1 for e in events if e["still_active"])
    total_impact = sum(e.get("max_affected_customers") or 0 for e in events)
    earliest = min((e["first_seen_at"] for e in events), default=None)
    latest = max((e["last_seen_at"] for e in events), default=None)
    summary = {
        "total_distinct_outage_events": total_events,
        "currently_active_events": active,
        "cumulative_customer_impact": total_impact,
        "tracking_since": earliest,
        "last_updated": latest,
    }
    with open(SUMMARY_PATH, "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))


def main():
    rows = load_history()
    active_ids = load_active_ids()
    events = build(rows, active_ids)
    write_geojson(events)
    write_csv(events)
    write_by_zip(events)
    write_summary(events)


if __name__ == "__main__":
    main()
