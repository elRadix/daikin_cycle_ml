# Summary — YAML card

A one-page multi-day summary: quality, cycles, run length and events over the last days. English, Dutch and French, dark mode.

> **Native alternative:** the [Daily summary card](../daikin-daily-summary-card/README.md) covers this card without YAML.

[CHANGELOG](CHANGELOG.md) · [All cards](../../README.md) · [YAML card guide](../README.md)

![Summary card](showcase.png)

## What it shows

| Section | Content |
|---|---|
| Header | Title + subtitle with icon |
| Hero | Model · family · kW + total cycles / hours + average quality + trend |
| Best / Worst day | Top and worst quality day with date + relative time |
| Sparklines | 3 mini-charts: quality · cycles/day · duration/day |
| Quality per day | Line chart with dynamically colored segments (green / orange / red) |
| Cycles per day | Stacked bars per mode (heating / DHW / cooling) with average line |
| Duration per day | Stacked bars in hours with dynamic cap |
| Events per day | BUH and defrost events on a shared time axis |

---

## Color coding

| Element | Color | Meaning |
|---|---|---|
| Heating | Fire red `#E63946` | Compressor heating the house |
| DHW | Light blue `#4FC3F7` | Domestic hot water cycle |
| Cooling | Dark blue `#0D47A1` | Cooling mode |
| BUH | Amber `#E65100` | Backup heater active |
| Defrost | Medium blue `#1976D2` | Defrost cycle |
| Quality good | Green `#2E7D32` | >= 70% |
| Quality mid | Orange `#E65100` | 40-69% |
| Quality low | Red `#C62828` | < 40% |

---

## Features

### Dynamic and smart

- **Auto-scaling charts** — Y-axis, bar width, and label density adapt to
  the number of days (1 to 90+).
- **Nice-number Y-axes** — round values (1, 2, 5, 10, 20, 50, 100).
- **p95-based duration cap** — no false clipping; adapts to the dataset.
- **Outlier detection** — days with more than 24 h runtime are marked.
- **Big-number formatters** — `1234` renders as `1.2k`, `720 h` as `30d`.
- **Auto-hide** — empty modes (for example no cooling) are hidden
  automatically.
- **Smart label density** — at 60+ days only every 7th label is drawn.

### Quality trending

- **Dynamically colored line** — the segment between two points takes the
  color of the average quality (`qColor((a.q + b.q) / 2)`).
- **Zone bands** — green / orange / red background bands for context.
- **Purple dashed line** — average over the whole period: the average
  score of all cycles (#436), the same figure as the tabbed card.
- **Quality per day** — the average score of the cycles that started that
  day, heating and DHW weighted by their number of cycles (#436).
- **Trend indicator** — `+5%` in the chart header shows the first-half vs
  second-half delta. The band names are in the legend below the chart.
- **Value labels** — at 21 days or fewer every dot shows its value.

### Interactive

- **SVG `<title>` tooltips** — hover bars and points for full data.
- **Responsive** — adapts to mobile, tablet, and desktop.
- **Chip legends** — color coding as scannable pills.

### Robust

- **Try/catch wrapper** — shows a readable summary error instead of
  crashing.
- **Full fallbacks** — `null` / `unknown` / `unavailable` render as `—`.
- **24/7-aware** — works with continuous operation (large totals, many
  cycles).

---

## Variables, language and theme

The variables are in the header of the card (the first button-card,
`variables: &dcm`); the other parts of the card reuse them with
`variables: *dcm`. Edit them there; a `variables:` block on the outer
`stack-in-card` has no effect.

    - type: custom:button-card
      variables: &dcm
        lang_override: ''
        theme_override: auto
        show_help: true

| Variable | Default | Values | Effect |
|---|---|---|---|
| `lang_override` | `''` | `''`, `en`, `nl`, `fr` | Force the language; empty = HA UI language, then the integration language, then English |
| `theme_override` | `auto` | `auto`, `light`, `dark` | `auto` follows the Home Assistant dark mode |
| `show_help` | `true` | `true`, `false` | Show the hint / explanation notes |

Language: English, Dutch or French; without `lang_override` the HA UI
language, then the integration language (`configured_language`), then
English. Numbers use the decimal separator of your HA number format.
Theme: one palette for all cards, dark backgrounds and light text in dark
mode. The header shows the heat pump model, family and power. Details:
[shared card settings](../README.md).

| Element | NL | EN | FR |
|---|---|---|---|
| Date format | `7 okt · wo` | `7 Oct · Wed` | `7 oct. · mer.` |
| Sections | `Cycli per dag` | `Cycles per day` | `Cycles par jour` |
| Legend | `Verwarming / DHW` | `Heating / DHW` | `Chauffage / ECS` |
| Relative time | `2d geleden` | `2d ago` | `2 j avant` |

---

## Installation

### Requirements

HACS frontend cards (install via **HACS → Frontend**):

| Card | Purpose |
|---|---|
| `stack-in-card` | Wrapper for the cards (border, gradient) |
| `button-card` | Body with `custom_fields` for the JS template |
| `card_mod` | CSS styling (border, gradients, colors) |

Integration:

- **Daikin Cycle ML** 1.24 or newer (re-paste the YAML after an update)
- Sensor `sensor.daikin_cycle_ml_daily_summary_recent` must exist
- Optional: `sensor.daikin_cycle_ml_hp_specs` for model info in the hero

### Step 1: Install the frontend cards

Via **HACS → Frontend → Explore & Download Repositories**:

- `custom-cards/stack-in-card`
- `custom-cards/button-card`
- `thomasloven/lovelace-card-mod`

Restart Home Assistant after installation. Hard-refresh the browser
(`Ctrl+Shift+R`).

### Step 2: Add the card

**Method A — raw configuration editor (recommended):**

1. Open the Lovelace dashboard in edit-mode.
2. **+ Add card → Manual**.
3. Paste the full YAML from `daily-summary.yaml`.
4. Save.

**Method B — YAML file:** add it to `ui-lovelace.yaml` or a dashboard YAML
under `views[].cards[]`.

### Step 3: Configure (optional)

Entity ids are found automatically, in any language and after a rename
(by translation key). Language, theme and hints are the header variables
(see [Variables, language and theme](#variables-language-and-theme)).

---

## Entity mapping

The card is 100% read-only. It reads from:

### `sensor.daikin_cycle_ml_daily_summary_recent`

| Attribute | Used for |
|---|---|
| `state` | Total cycles |
| `days_available` | Day count |
| `latest_day`, `oldest_day` | Date range in the hero |
| `days[]` | Per-day data: `cycles`, `dur_min`, `quality_avg`, `buh`, `defrost`, `mode` |
| `events_by_day` | Real defrost events and BUH minutes per day (preferred over the per-cycle counts) |
| `totals_by_mode` | Heating / DHW / Cooling totals |

### `sensor.daikin_cycle_ml_hp_specs`

| Attribute | Used for |
|---|---|
| `model` | Hero: for example `EPRA12EAV3` |
| `family` | Hero: for example `Monoblock` |
| `kw` | Hero: for example `12 kW` |

If an attribute is missing, the card shows `—` and keeps working.

---

## Troubleshooting

### `ButtonCardJSTemplateError`

A JS error occurred inside the template. Open the browser console (F12),
find the line number, and compare with the original template. The template
has a try/catch wrapper, so most errors are caught and shown as a summary
error instead of a blank card.

### Card shows `—` everywhere

Entity not found or attributes missing. Verify via **Developer Tools →
Template**:

```jinja
{{ states('sensor.daikin_cycle_ml_daily_summary_recent') }}
{{ state_attr('sensor.daikin_cycle_ml_daily_summary_recent', 'days') | length }}
```

- Empty result → check the integration, restart HA.
- Populated result → entity ID mismatch in the card.

### Charts overlap or text disappears

`button-card` inherits `white-space: nowrap`. Make sure
`white-space: normal !important` is present on `.d-sec`, `.d-hdr`, and the
outer `<div>` in the JS template.

### Quality section missing

`quality_avg` is `null` for all days. Wait until cycles with a quality
score have completed — the value is computed at every full cycle.

---

## Customization

### Colors

Search in the JS template for:

```js
var C = {
  heating: '#E63946',
  dhw:     '#4FC3F7',
  cooling: '#0D47A1',
  buh:     '#E65100',
  defrost: '#1976D2',
  quality: '#2E7D32',
  gem:     '#6A1B9A'
};
```

### Add a language

Add a new language to the `STR` object:

```js
var STR = {
  nl: { /* ... */ },
  en: { /* ... */ },
  de: {
    summary: 'ZUSAMMENFASSUNG',
    days: 'Tage',
    cycles: 'Zyklen',
    /* ... full mirror of the NL keys ... */
  }
};
```

Add `'de'` to the language list in `tools/card_common.js`, run
`python3 tools/sync_card_common.py` and set `lang_override: 'de'`.

### Adjust the cap

The dynamic duration cap:

```js
var c2Cap = Math.max(4, Math.min(24, roundNice(Math.max(p95 * 1.15, 4))));
```

- `4` — minimum cap (hours)
- `24` — maximum cap (physical limit)
- `p95 * 1.15` — 15% margin above the 95th percentile

---

## Data sources

The card is 100% read-only. No writes, no services, no state changes.

```
Daikin HP -> ESPAltherma -> sensor.althermasensors
              |
       Daikin Cycle ML integration
              |
       SQLite DB (.storage/daikin_cycle_ml.db)
              |
   daily_summary_recent (attribute)
              |
           This card
```

Retention: cycles 90 d (prod 365) · daily summary permanent · COP samples
365 d.

---

## License

MIT — free to use, modify, and share. Part of the
[Daikin Cycle ML](https://github.com/elRadix/daikin_cycle_ml) integration.
