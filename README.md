# Milwaukee-area We Energies Outage Tracker

A civic-transparency project that logs [We Energies](https://www.we-energies.com/) power
outages across its Wisconsin service area (Milwaukee and southeast Wisconsin) over time, with
coordinates, so outage frequency and duration can eventually be mapped against neighborhood
demographics — including whether Milwaukee's majority-Black north side experiences
disproportionate outage frequency, as residents and advocacy groups have alleged.

## Why this exists

There is **no public historical dataset** of geolocated We Energies outages. Utilities don't
publish this, and the one company that archives it commercially (PowerOutage.us) only sells it
as a paid enterprise product. What We Energies *does* expose is a live, undocumented JSON feed
that powers its own public outage map — refreshed every 10 minutes, with latitude/longitude per
outage event. This project polls that feed on a schedule and builds a historical archive going
forward, the same "git-scraping" technique used by projects like
[simonw/pge-outages](https://github.com/simonw/pge-outages) and
[Code for Kentuckiana's power-outage-data](https://openkentuckiana.org/2019-12-18-power-utility-data/).

**Important limitation:** this can only capture data from the day it started running onward.
It cannot retroactively reconstruct the last two years of outages — that history was never
recorded anywhere publicly. See [Regulatory data](#regulatory-data-worth-requesting) below for
one path to older, non-geocoded reliability data.

## How it works

- `scripts/fetch_outages.py` — fetches `https://www.we-energies.com/outagesummary/view/OutageEventJSON`,
  overwrites `data/latest.json` (full history preserved via git commits), and appends one row per
  outage/ZIP-slice to `data/history.ndjson` with a `captured_at` timestamp.
- `scripts/build_geojson.py` — rebuilds `data/outage_events.geojson`, `data/outage_events.csv`,
  `data/by_zip.csv`, and `data/summary.json` from the accumulated history log. Outage events are
  deduplicated using a hash of rounded coordinates + off-time (the source feed has no persistent
  event ID), tracking first-seen/last-seen timestamps and peak customers affected.
- `.github/workflows/scrape.yml` — runs both scripts every 15 minutes via GitHub Actions and
  commits any changes. Free to run indefinitely on a public repo.
- `index.html` — a Leaflet map (see [Viewing the map](#viewing-the-map)) that reads the GeoJSON
  output directly from the repo.

## Data files

| File | Contents |
|---|---|
| `data/latest.json` | Raw snapshot of currently active outages (overwritten each run; history lives in git log) |
| `data/history.ndjson` | Append-only log, one JSON row per (outage, zip-slice, poll) |
| `data/outage_events.geojson` | Deduplicated point features for mapping, one per distinct outage event |
| `data/outage_events.csv` | Same data as CSV |
| `data/by_zip.csv` | Outage-event counts and cumulative customer-impact aggregated by ZIP code — join this against Census/ACS demographic data by ZCTA to analyze disparity |
| `data/summary.json` | Small rollup (tracking start date, totals, currently-active count) |

## Running it yourself

```bash
pip install -r requirements.txt
python scripts/fetch_outages.py
python scripts/build_geojson.py
```

## Viewing the map

Enable GitHub Pages on this repo (Settings → Pages → Deploy from branch `main` / root), then
visit `https://<your-username>.github.io/mke-power-outage-tracker/`. The map is empty until the
first few scheduled scrapes have run — check the Actions tab to confirm the workflow is enabled
and has run at least once (or trigger it manually with "Run workflow").

## Regulatory data worth requesting

For pre-existing (non-geocoded) reliability history, Wisconsin utilities with 100,000+ customers
must file annual SAIDI/SAIFI reliability reports with the Public Service Commission of Wisconsin,
including a list of worst-performing circuits and remediation plans
([Wis. Admin. Code PSC 113.0604](https://www.law.cornell.edu/regulations/wisconsin/Wis-Admin-Code-SS-PSC-113-0604)).
These aren't published as open data but can be requested from the PSC
([psc.wi.gov](https://psc.wi.gov/Pages/ForConsumers/LogAComplaint.aspx)) and would let you check
whether north-side circuits are disproportionately represented among the utility's
worst-performing circuits — a stronger signal than raw outage counts alone.

## Roadmap ideas

- Join `data/by_zip.csv` against Census ACS demographic data (race, income, redlining-era HOLC
  grades) to quantify any correlation between outage frequency/impact and neighborhood
  demographics.
- Overlay Milwaukee neighborhood/aldermanic-district boundaries instead of raw ZIP codes for a
  more precise "north side" definition.
- Add a rolling 24h/7d/30d outage-frequency heatmap layer.
- Publish a periodic public summary (e.g., monthly digest of outage counts by neighborhood).

## Background reading

- [Sierra Club — energy burden study on Milwaukee's majority-Black/Latinx neighborhoods](https://www.sierraclub.org/wisconsin/we-energies-files-third-rate-increase-three-years-marginalized-milwaukeeans-bear-brunt)
- [Milwaukee Journal Sentinel — energy affordability on Milwaukee's north side](https://www.jsonline.com/story/money/business/energy/2024/04/16/electric-rates-going-up-as-challenges-grow-for-milwaukees-least-well-off/73302668007/)
- [Power to the People MKE — municipal utility campaign, reliability arguments](https://www.powertothepeoplemke.org/wp-content/uploads/2023/11/PTTP-White-Paper.pdf)
