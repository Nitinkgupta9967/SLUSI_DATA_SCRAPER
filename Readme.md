# Soil Health Card Scraper

Scrapes soil nutrient data from the Government of India Soil Health Card portal.
Portal: https://soilhealth.dac.gov.in/slusi-visualisation/

## Setup

```bash
pip install -r requirements.txt
```

## Before Each Session

The portal uses session-locked obfuscated URLs that rotate on every browser session.
Before running, open the portal in Chrome → DevTools (F12) → Network tab and update
two variables at the top of `scrape.py`:

- `WMS_BASE` — copy from any `wms?service=WMS` request URL
- `API_BASE` — copy from any `/public/layers` request URL (everything before `/public/layers`)

## Usage

```bash
# All districts × all cycles × all nutrients
python scrape.py --state Maharashtra

# Specific district, all cycles × all nutrients
python scrape.py --state Maharashtra --district Satara

# Specific district + cycle, all nutrients
python scrape.py --state Maharashtra --district Satara --cycle 2023-24

# Fully specific
python scrape.py --state Maharashtra --district Satara --cycle 2023-24 --nutrient Nitrogen
```

Works for any Indian state, not just Maharashtra.

## Output Files

Two CSV files are saved per district × cycle combination:

| File | Description |
|------|-------------|
| `samples_<State>_<District>_<Cycle>.csv` | One row per soil sample per nutrient |
| `summary_<State>_<District>_<Cycle>.csv` | Low/Medium/High counts per nutrient |

### Sample columns
`State, District, Cycle, Nutrient, Village, Value, Category, Low_Threshold, High_Threshold, Unit, Feature_ID`

### Summary columns
`State, District, Cycle, Nutrient, Low_Count, Medium_Count, High_Count, Total, Low_Threshold, High_Threshold, Unit`

## Notes

- Nutrient thresholds are fixed by GoI Soil Health Card guidelines
- Some cycles (e.g. 2025-26) exist in the portal but have no data yet
- No browser driver required — uses direct API calls only