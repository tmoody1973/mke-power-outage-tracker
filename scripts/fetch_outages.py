#!/usr/bin/env python3
"""
Fetch the live We Energies outage feed and record it.

Data source (public, undocumented JSON endpoint that powers the official
We Energies outage map):
    https://www.we-energies.com/outagesummary/view/OutageEventJSON

This script is designed to be run on a schedule (see
.github/workflows/scrape.yml, every 15 minutes). Each run:

1. Fetches the current list of active outage events (lat/long, off time,
   estimated restoration, cause, crew status, and affected-customer counts
   broken out by city/county/zip/region).
2. Overwrites data/latest.json with the raw response. Because this file is
   committed to git on every run, its full history (via `git log -p` or
   `git show <sha>:data/latest.json`) becomes a "git-scraped" historical
   archive of the outage map over time -- the same technique used by
   projects like simonw/pge-outages.
3. Appends one flattened row per (outage, slice) to data/history.ndjson,
   which is much easier to query/analyze than replaying git history. This
   is the file scripts/build_geojson.py reads to build map layers.

No historical data exists prior to when this script started running --
utilities do not publish that. This only builds a forward-looking archive.
"""

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("Missing dependency: requests. Run `pip install -r requirements.txt`.", file=sys.stderr)
    sys.exit(1)

SOURCE_URL = "https://www.we-energies.com/outagesummary/view/OutageEventJSON"
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
LATEST_PATH = os.path.join(DATA_DIR, "latest.json")
HISTORY_PATH = os.path.join(DATA_DIR, "history.ndjson")

HEADERS = {
    # A normal browser UA. This is a public endpoint that already serves
    # the anonymous outage map to any visitor; no auth is used or implied.
    "User-Agent": (
        "Mozilla/5.0 (compatible; mke-power-outage-tracker/1.0; "
        "+https://github.com/tmoody1973/mke-power-outage-tracker)"
    ),
    "Accept": "application/json",
}


def fetch(retries: int = 3, backoff: float = 5.0):
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(SOURCE_URL, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"[attempt {attempt}] fetch failed: {e}", file=sys.stderr)
            if attempt < retries:
                time.sleep(backoff)
    raise RuntimeError(f"Could not fetch outage feed after {retries} attempts: {last_err}")


def outage_event_id(event: dict) -> str:
    """
    The source feed has no persistent event ID. Derive a stable one from
    coordinates (rounded) + off-time, which together identify a distinct
    outage event across polls even as its ETR/crew status/cause updates.
    """
    lat = round(float(event.get("Latitude") or 0), 4)
    lon = round(float(event.get("Longitude") or 0), 4)
    off_time = event.get("OffTime") or ""
    key = f"{lat}|{lon}|{off_time}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def flatten(events: list, captured_at: str) -> list:
    rows = []
    for event in events:
        eid = outage_event_id(event)
        base = {
            "event_id": eid,
            "captured_at": captured_at,
            "latitude": event.get("Latitude"),
            "longitude": event.get("Longitude"),
            "off_time": event.get("OffTime"),
            "etr": event.get("ETR"),
            "crew_status": event.get("CrewStatus"),
            "cause": event.get("Cause"),
            "last_updated": event.get("LastUpdated"),
            "is_global": event.get("IsGlobal"),
        }
        slices = event.get("Slices") or [{}]
        for s in slices:
            row = dict(base)
            row.update(
                {
                    "affected_customers": s.get("AffectedCusts"),
                    "city": s.get("City"),
                    "city_customers_out": s.get("CityCusts"),
                    "county": s.get("County"),
                    "county_customers_out": s.get("CountyCusts"),
                    "zip": s.get("Zip"),
                    "zip_customers_out": s.get("ZipCusts"),
                    "region": s.get("Region"),
                    "region_customers_out": s.get("RegionCusts"),
                }
            )
            rows.append(row)
    return rows


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    events = fetch()
    if not isinstance(events, list):
        raise RuntimeError(f"Unexpected response shape (expected list): {type(events)}")

    with open(LATEST_PATH, "w") as f:
        json.dump({"captured_at": captured_at, "events": events}, f, indent=2)

    rows = flatten(events, captured_at)
    with open(HISTORY_PATH, "a") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")

    print(
        f"[{captured_at}] fetched {len(events)} active outage event(s), "
        f"{len(rows)} flattened row(s) appended to history."
    )


if __name__ == "__main__":
    main()
