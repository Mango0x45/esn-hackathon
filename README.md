# WasteWatt

Finds energy waste in student flats and tells students what to do about it, in kWh, SEK and CO₂e.
Built for the *AI for Energy Saving* hackathon track on the organiser's synthetic dataset (`data/`).

## Run it

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env               # then paste your Gemini API key into .env
.venv/bin/python app.py            # open http://localhost:8000
```

The AI coach uses Gemini (`gemini-3.6-flash`) and needs a [Gemini API key](https://aistudio.google.com/apikey). `app.py` reads it from `.env`, which git ignores; a real `GEMINI_API_KEY` environment variable takes precedence. Without one, everything else works and the coach says it needs a key.

```sh
python3 analyze.py                 # data-quality summary, findings per flat, per-student savings
python3 -m unittest -v             # tests (stdlib only, no key needed)
```

## How it works

| File | Job |
|---|---|
| `clean.py` | Loads the four CSVs and repairs every defect it finds, counting each repair |
| `analyze.py` | Four waste detectors, then pricing and annualising of each finding |
| `app.py` | Local web server: `/api/flats`, `/api/report?flat=F001`, `POST /api/coach`, `POST`/`DELETE /api/devices`, `POST /api/flats` |
| `static/index.html` | The student-facing page |

### Data cleaning
| Defect | Count | Decision |
|---|---:|---|
| `Wh` units, ` kwh ` spelling | 141 / 70 | Normalised to kWh |
| Comma decimals (`0,033`) | 100 | Parsed |
| Empty / `N/A` values | 490 | Missing, **never zero** |
| Negative or > 4 kWh/h | 62 | Impossible for one 16 A circuit (max ≈3.7 kWh/h), so treated as missing |
| Duplicate rows | 125 | Removed. In 25 conflicting pairs the lower value is kept, so savings are not inflated |
| Lower-case / padded appliance IDs | 65 | Trimmed and upper-cased |
| `flat_id` ≠ appliance prefix | 24 | Appliance ID wins: each such row fills a gap in its own series |
| Orphan appliance `F999-A01` | 12 | Dropped |
| Legacy `YYYY/MM/DD HH:MM` timestamps | 79 | Converted (they are UTC) |
| Occupancy empty or above the resident count | 97 | Unknown |
| Missing spot price | 8 h | Skipped in price maths |

98.4 % of appliance-hours are measured. Yearly figures use the mean of observed hours, so gaps do not count as zero use.

### Detectors
1. **Fault:** an always-on circuit whose last-week median is >1.5x its first-week median (and >20 W higher). Lasting shifts are faults; isolated impossible values are corrupt readings, already removed by cleaning. Finds the F002 fridge.
2. **Always-on:** overnight (01–05 local) draw >2x the same circuit's median across all flats (and >30 W more). Finds F005's electronics.
3. **Heating:** portable-heater energy in hours with indoor ≥ 22 °C or nobody home. Finds F007.
4. **Timing:** each dishwasher/washer hour moves to the cheapest hour in the next 12 h. Only SEK changes; CO₂e uses the destination hour's carbon factor.

Findings under 20 SEK/yr are hidden.

### Added devices
Residents can add a device the meters don't cover (name, watts, hours a day). It shows up as an extra bar with yearly kWh, SEK and CO₂e, counts toward the flat's total, and the AI coach sees it. Devices are stored per flat in `devices.json`, which git ignores.

### Added flats
New flats can be created with their residents and floor area. They get the next free ID (F009, F010, ...) and are stored in `flats.json`, which git ignores. They have no meter data, so the detectors can't scan them: they hold hand-added devices only. They are left out of the per-student savings figures and the flat ranking. Prices use SE3, the only area in the dataset.

### Flat comparison
Flats are ranked by yearly kWh per resident. A flat at 1.5x the median or more is flagged, together with its biggest circuit (F001: 2.5x, portable heater). The comparison works at flat level only: the data has no per-person readings, and the hackathon rules forbid using other students' personal data without consent.

### Assumptions
- **Circuit types are inferred** from load shapes, because the dataset has no appliance lookup. A01 always-on → fridge/freezer, A02 meal-time spikes → cooking, A03 small and sporadic → small kitchen appliances, A04 evening blocks → dishwasher/washer, A05 follows occupancy → lighting & misc, A06 base load + evening peak → electronics, A07 night-heavy and temperature-linked → portable heater.
- **Price:** (dataset mean spot + 0.312 grid fee + 0.36 energy tax) × 1.25 VAT ≈ 1.44 SEK/kWh. Fixed fees are excluded, because they do not shrink when you save.
- **Annualising:** always-on loads × 8,760 h, heater × 212-day heating season, timing × 365/28. Four autumn weeks are a thin base, so treat results as estimates.
- **Expected = 70 % of potential**, to allow for partial follow-through. Rebound is not modelled.

Sources and the savings slide are in [PITCH.md](PITCH.md).
