# Dashboard Cards — Daikin Cycle ML

Ready-to-use Lovelace dashboard cards for the **Daikin Cycle ML** integration.

## Available Cards

| Card | Description | Preview | Requires |
|---|---|---|---|
| [**Simple Card**](cards/simple-card/README.md) | Live phase, hydraulic diagram, COP, quality, alerts, stooklijn advice | <img src="cards/simple-card/preview.png" width="320" alt="Simple Card preview"> | v1.4.0+ |
| [**Heating Curve**](cards/heating-curve/README.md) | HP spec-aware visual with COP heatmap, regression & live position | <img src="cards/heating-curve/preview.png" width="320" alt="Heating Curve preview"> | v1.4.0+ |

---

## Requirements

### Backend (integration)

- **daikin_cycle_ml** `>= v1.4.0`

**Core entities** (used by both cards):

- `sensor.daikin_cycle_ml_heating_curve_advice`
- `sensor.daikin_cycle_ml_cycle_state`
- `sensor.daikin_cycle_ml_last_cycle`
- `sensor.daikin_cycle_ml_cop_mean_day`
- `sensor.daikin_cycle_ml_cop_mean_week`

**Simple Card only** (additional):

- `sensor.daikin_cycle_ml_current_cycle`
- `sensor.daikin_cycle_ml_cycles_today`
- `sensor.daikin_cycle_ml_quality_today`
- `sensor.daikin_cycle_ml_cop_today`
- `sensor.daikin_cycle_ml_source_health`
- `sensor.daikin_cycle_ml_learned_thresholds`
- `sensor.daikin_cycle_ml_thermal_power_live` (optional, kW callout)
- 15 binary_sensors (see Simple Card README for the full list)

**Attributes on `sensor.daikin_cycle_ml_cycle_state`:**

- `configured_language` — auto-detected language (`nl` / `en`)
- `configured_model` — HP model key (e.g. `epra12eav3`)
- `configured_source_sensor`, `configured_power_sensor`, `configured_cop_sensor`, `configured_indoor_sensor`

**Attributes on `sensor.daikin_cycle_ml_heating_curve_advice`:**

- `huidige_lwt`, `optimale_lwt`, `besparing_cop_pct`
- `bucket`, `samples`, `buckets` (dict: `{ "<outdoor-bucket>": { cop, n, lwt }, ... }`)
- `reason`, `comfort_impact`, `betrouwbaarheid`

### Frontend (HACS cards)

| Card | Repo | Purpose |
|---|---|---|
| `stack-in-card` | [custom-cards/stack-in-card](https://github.com/custom-cards/stack-in-card) | Wrapper |
| `mushroom-template-card` | [piitaya/lovelace-mushroom](https://github.com/piitaya/lovelace-mushroom) | Header |
| `button-card` | [custom-cards/button-card](https://github.com/custom-cards/button-card) | SVG content |
| `card-mod` | [thomasloven/lovelace-card-mod](https://github.com/thomasloven/lovelace-card-mod) | Border + shadow styling |

Install each via **HACS → Frontend → Explore & Download Repositories**.
Restart Home Assistant after installing a new frontend card.

---

## Installation

1. Install the four HACS frontend cards (see above).
2. Restart Home Assistant.
3. Hard-refresh the browser (`Ctrl+Shift+R`).
4. Open **Lovelace → Edit dashboard → + Add Card → Manual**.
5. Open the card's own README (via the **Available Cards** table) and copy
   the entire YAML from its `*.yaml` file.
6. Paste the YAML into the manual card editor.
7. **Save.**

Cards auto-detect your HP model, integration language, and configuration — no
manual entity-ID edits required if your integration uses the default
`daikin_cycle_ml` prefix.

---

## Features

### 🎨 Visual

- **COP heatmap** — 2D Carnot-based grid behind the plot (red → yellow → green)
- **HP spec-aware axes** — Y-axis auto-scales to your heat pump's LWT range
- **Auto-zoom** — X-axis focuses on bucket spread when data is available
- **Live dot** — Pulsing last-cycle outdoor × current LWT position with animated ring
- **Bucket bubbles** — Size = sample count · Color = COP quality · Labels = n + COP
- **Regression curve** — Linear fit through buckets with formula label
- **Zone overlays** — Defrost (hachure), warm tint, heating OFF, BUH assist band
- **Hydraulic loop** *(Simple Card)* — Animated supply/return, live rps fan, ΔT bubble

### ⚙️ Auto-discovery

- Reads `configured_model` to select HP specs from a lookup table (14 models: EPRA / ERLA, 04–16 kW)
- Reads `configured_*` sensors for the config footer
- Graceful fallbacks when attributes are missing

### 🌐 Bilingual (NL / EN)

- Language detected from the `configured_language` attribute
- All labels translated via the internal `t('key')` helper
- Fallback to English when the attribute is missing or unknown

### 📐 Info panels

- **Specs box** — model, family, kW, refrigerant, LWT/outdoor ranges, thresholds, regression formula, samples, buckets
- **Config footer** — auto-discovered sensors (source, power, COP, indoor)
- **Regression + samples counter**
- **COP trend** — 24h vs 7d rolling comparison

---

## Data & limitations

### HP specs are indicative

`HP_SPECS` values (kW, nominal COP, LWT ranges, refrigerant) are **indicative**
and derived from public Altherma 3 datasheets. Verify against your own unit
before relying on the thresholds for control decisions.

### `buckets` structure

The Heating Curve card reads `buckets` from
`sensor.daikin_cycle_ml_heating_curve_advice`. Keys follow
`bucket_for_outdoor()` in the integration:

- `-10-` — outdoor < -10 °C
- `-10--8`, `-8--6`, `-2-0`, `0-2`, `2-4`, ..., `18-20` — 2 °C buckets
- `20+` — outdoor >= 20 °C
- `unknown` — dropped

Each bucket value is `{ cop: float, n: int, lwt: float|None }`.

### Live dot uses last completed cycle

`_attrs_current_cycle` does not expose `outdoor_temp` in v1.4.x — the live dot
therefore reads `outdoor_temp` from `sensor.daikin_cycle_ml_last_cycle`.

### Not yet available

DHW and historical overlays are **not** in this release — the integration does
not expose `dhw_buckets` / `history_buckets` yet.

---

## Customization

### Simple Card — change language

The Simple Card has **three language modes**, controlled by two variables that
must be kept in sync:

| Variable | Location | Values |
|---|---|---|
| `lang_override` | `mushroom-template-card` block (Jinja) | `''` / `'nl'` / `'en'` |
| `LANG_OVERRIDE` | `button-card` block (JS) | `''` / `'nl'` / `'en'` |

- `''` — **auto** (follow `configured_language` from the integration)
- `'nl'` — **force Dutch**
- `'en'` — **force English**

To force a language, set both variables to the same value. Example — force Dutch:

```jinja
{% set lang_override = 'nl' -%}
```

```js
var LANG_OVERRIDE = 'nl';
```

If the two variables differ, the header and body will show different
languages. Keep them identical.

### Heating Curve — change language

The Heating Curve card resolves language automatically from the integration's
`configured_language` attribute. To force a specific language, find this
line inside the card's `custom_fields.content` JS block:

```js
var cfgLang = String(attr(S_STATE,'configured_language','en')).toLowerCase();
var LANG = (cfgLang === 'nl') ? 'nl' : 'en';
```

Replace the second line with a hardcoded value:

```js
var LANG = 'en';   /* or 'nl' */
```

### Theme colours

All colours are defined inline in each card's YAML. Key palette:

| Element | Colour | Hex |
|---|---|---|
| Primary (Daikin blue) | Border, accents | `#0097E0` |
| Dark blue | Headers | `#003366` |
| Mid blue | Secondary text | `#00539F` |
| Daikin red | Heating, critical alerts | `#E60012` |
| Amber | Warnings | `#F5A623` |
| Green | Success, OK state | `#4CAF50` |
| Purple | DHW phase | `#9b59b6` |

Search-and-replace any hex in the YAML to change the palette.

### Entity IDs

If your integration entities don't match the default prefix
(`sensor.daikin_cycle_ml_*` / `binary_sensor.daikin_cycle_ml_*`), update the
`var S = { ... }` / `var B = { ... }` objects near the top of each card's JS
block.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Card renders as plain YAML text | HACS frontend cards not installed. See **Requirements**. |
| `Custom element doesn't exist: stack-in-card` | Frontend card not loaded — restart HA, hard-refresh browser. |
| Body shows empty / blank | Check the browser console for JS errors. Verify entity IDs match. |
| `ButtonCardJSTemplateError` | A helper function referenced by the card is missing — ensure the YAML matches the current version from this repo. |
| COP shows `—` | No COP sample collected yet — check `sensor.daikin_cycle_ml_cop_today` in **Developer Tools → States**. |
| Language not switching | Verify both override variables are set to the same value. Values are case-sensitive lowercase `'nl'` / `'en'`. |
| Header in NL, body in EN (or vice versa) | Override variables are out of sync. Set both to identical values. |
| Colours look washed out | Some browsers block CSS gradients in `card_mod` under strict mode. Remove the outer `card_mod.style` block if needed. |
| Preview image missing | Take a fresh screenshot of the card (~800×600) and save it as `preview.png` in the card's folder. |

---

## Adding a new card

1. Create a new folder under `cards/<your-card-name>/`.
2. Add `<your-card-name>.yaml` — the full Lovelace YAML.
3. Add `README.md` — purpose, dependencies, install steps, entity list.
4. Add `preview.png` — a screenshot of the rendered card (~800×600).
5. Add a row to the **Available Cards** table at the top of this file.