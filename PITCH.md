# WasteWatt: pitch notes

## One line
WasteWatt reads a flat's per-circuit electricity data, finds the waste a student would never spot, and says what to do this week, in kroner.

## User and problem
- **User:** a student in a shared flat in Sweden. Main heat is district heating, but electricity covers the fridge, cooking, laundry, electronics and the portable heater.
- **Problem:** the bill is one number. Nobody knows that the fridge broke two weeks ago or that a PC runs all night. Sorting this out is nobody's job.
- **Baseline:** 870 kWh of electricity per student per year (organiser dataset, 25 residents, cleaned and annualised).

## What the demo shows (click path)
1. `F002`: the fridge suddenly draws 2.2x its normal power from 15 Oct. That is a fault, not a bad reading, so tell the landlord.
2. `F005`: an electronics circuit draws 128 W all night, 3.9x similar flats. Something is left on.
3. `F007`: 95 % of the heater's energy goes into a room that is already at 22 °C or more.
4. Every flat: delay-start the dishwasher/washer from 20:00 to the cheapest hour (same energy, lower price).
5. "Get my plan": Gemini turns the flat's report into at most 5 steps, biggest saving first.

## Where the AI is
- **Anomaly detection without labels.** The dataset has no appliance types. WasteWatt infers them from load shapes, finds lasting level shifts (faults), compares each circuit with the same circuit in similar flats (peer baseline), and checks heater use against indoor temperature and occupancy.
- **A trust layer before the maths.** Cleaning fixes about 1,100 defects in 37,715 readings: duplicates, Wh/kWh mixing, comma decimals, impossible values and orphan IDs. Missing data stays missing; it is never counted as zero.
- **Gemini coach** (`gemini-3.6-flash`). It explains the findings in plain language and answers free questions. It may use only the report's numbers.

## Business model
- **Customer:** student-housing landlords, often with electricity included in the rent (for example SSSB, AF Bostäder). They pay the bill and own the broken fridge, so a fault alert saves them money directly.
- **Price:** 10 SEK per flat per month (120 SEK/yr). Expected saving is about 590 SEK per flat per year (190 SEK × 25 students / 8 flats), so the customer saves roughly 5x what they pay.
- **Cost to serve:** the analysis is plain Python. One coach answer is a few thousand tokens, well under 1 SEK at Gemini 3.6 Flash list prices ($1.50 / $7.50 per million input/output tokens from 2027, half that until then).
- **Later:** smart plugs for automatic night-off, and landlord dashboards for fault tickets.

## Savings slide: per student per year

| | kWh | SEK | kg CO₂e |
|---|---:|---:|---:|
| Baseline electricity use | 870 | ≈1,250 | ≈32 |
| Technical potential | 155 | 271 | 6.6 |
| **Expected (70 % follow-through)** | **108** | **190** | **4.6** |

Expected saving ≈ **12 % of each student's electricity**. The average hides a skewed split: three flats have one large leak (fault, always-on device, overheating). Every flat gains about 125–195 SEK/yr from timing alone.

**How the numbers are made** (run `python3 analyze.py` to reproduce):
- kWh: four weeks of cleaned October data, annualised. Always-on loads × 8,760 h. Heater × 212-day heating season (Oct–Apr, an assumption; October is milder than winter, so this is conservative). Timing × 365/28.
- SEK: kWh × (dataset mean spot 0.48 + grid fee 0.31 + energy tax 0.36) × 1.25 VAT ≈ 1.44 SEK/kWh. Timing savings use only the hourly spot difference × VAT.
- CO₂e: kWh × the dataset's mean carbon factor (37 g/kWh). For timing it uses the destination hour's factor.

**Sources**
- Energy tax 2026: 36.0 öre/kWh excl. VAT. [Skatteverket, Skatt på el](https://www.skatteverket.se/foretag/skatterochavdrag/punktskatter/energiskatter/skattpael)
- Grid transfer fee: 39.0 öre/kWh incl. VAT (31.2 excl.), single tariff. [Vattenfall Eldistribution, prislista säkringsabonnemang 2025 privat](https://www.vattenfalleldistribution.se/globalassets/1.-privat/abonnemang-och-avgifter/om-avtal-och-avgifter/elnatsavgifter/prislista-sakringsabonnemang-2025-01-privat.pdf)
- 1 °C lower ≈ 5 % less heating energy (rule of thumb attributed to Energimyndigheten). [Varberg Energi, energispartips](https://varbergenergi.se/nyheter/energispartips)
- Spot prices, carbon factors and consumption: the organiser's synthetic participant dataset (`data/README.md`). These are not real market or meter data.

**Uncertainty, stated up front:** four autumn weeks do not establish a year, the data is synthetic, appliance types are inferred, the 70 % follow-through factor is an assumption, and rebound (e.g. buying a bigger TV with the savings) is not modelled. Treat the slide as a well-founded estimate, not a measurement.

## 3-minute script
- **0:00 Hook:** "Your flat has a fridge that broke two weeks ago. Nobody knows, and you pay for it every hour."
- **0:20 Problem:** one number on the bill, no idea where it goes, nobody's job.
- **0:40 Demo:** F002 fault → F005 always-on → F007 heater → "Get my plan".
- **1:50 Savings slide:** 108 kWh, 190 SEK, 4.6 kg CO₂e per student per year, with sources. Name the uncertainty yourself.
- **2:20 Business:** landlords pay 10 SEK/flat/month and save about 5x that. Fault alerts reach the person who owns the fridge.
- **2:45 Close:** "WasteWatt finds the waste you can't see and tells you the one thing to do about it."
