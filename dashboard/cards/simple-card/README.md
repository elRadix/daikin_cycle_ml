# Simple Card

A compact, one-glance Lovelace card for **Daikin Cycle ML**. Daikin-blue
theme, hydraulic diagram, phase indicator, live alerts, and stooklijn
advice. Auto-detects the integration language (EN / NL) and supports a
manual override.

![preview](preview.png)

---

## What it shows

| Section | Content |
|---|---|
| **Header** | Title + live subtitle |
| **Hero** | Current phase (IDLE / HEATING / DHW / DEFROST / BUH / COOLING) + animated fan at live rps + COP + Quality |
| **Alerts** | Only when active - colour-coded by severity (crit / warn / info) |
| **Diagram** | Hydraulic loop: warmtepomp -> afgifte, with live rps / kW / dT |
| **Tiles** | COP - Runs today/target - Quality % - Source age |
| **2-col detail** | "Vandaag" (avg duration, avg off, longest, short runs) next to "Laatste cyclus" (duration, dT, rps, mode) |
| **Stooklijn** | Current advice state + bucket + savings % + reliability |
| **Explain** | One-line legend for non-obvious values |

All **25 entities** from the integration are used. Missing values render
as an em-dash placeholder (no errors, no broken layout).

---

## Dependencies

Install each via **HACS -> Frontend -> Explore & Download Repositories**:

| Card | Purpose | HACS repo |
|---|---|---|
| `stack-in-card` | Outer container that vertically stacks the cards | `custom-cards/stack-in-card` |
| `mushroom-template-card` | Header with icon + title + subtitle | `piitaya/lovelace-mushroom` |
| `button-card` | Dynamic HTML render (the entire body) | `custom-cards/button-card` |
| `card-mod` | Inline CSS (border + gradient on the outer frame) | `thomasloven/lovelace-card-mod` |

**Minimum versions**: any recent release (2025 or newer).

---

## Installation

1. **Install the four dependencies** (see above) via HACS.
2. **Restart Home Assistant** - required after installing a new frontend card.
3. Hard-refresh the browser (Ctrl+Shift+R).
4. Open a dashboard in edit mode, click **+ Add Card**.
5. Choose **Manual** (bottom of the card picker).
6. Copy the entire contents of `simple-card.yaml` and paste it.
7. Click **Save**.

If the card looks unstyled or empty:

- Hard-refresh the browser again.
- Open **Developer Tools -> Console** in the browser for JS errors.
- Verify all four frontend cards are listed under
  **Settings -> Dashboards -> Resources**.

---

## Configuration

### Language

The card has **three language modes**, controlled by two variables that
must always be kept in sync:

| Variable | Location | Purpose |
|---|---|---|
| `lang_override` | `mushroom-template-card` block (Jinja) | Controls the header subtitle |
| `LANG_OVERRIDE` | `button-card` block (JavaScript) | Controls the entire body |

Both accept the same values:

| Value | Behaviour |
|---|---|
| `''` (empty string) | **Auto** - follow `configured_language` from the integration |
| `'nl'` | **Force Dutch** - ignore integration setting |
| `'en'` | **Force English** - ignore integration setting |

**Example - force Dutch:**

In the mushroom block:

```jinja
{% set lang_override = 'nl' -%}
```

In the button-card JS block:

```js
var LANG_OVERRIDE = 'nl';
```

**Warning:** if the two variables are set to different values, the header
and body will display in different languages. Keep them identical.

**Supported languages:** `nl` (Nederlands), `en` (English).

**To add a new language:**

1. Copy the `en` block inside the `STR` object (in the JS) and rename the
   key to your language code (e.g. `de`).
2. Translate every value in the copied block.
3. Extend the `LANG` resolution so it recognises your new code:
   `(LANG_OVERRIDE === 'de' || ...) ? LANG_OVERRIDE : (...)`
4. Add the same language branch to the Jinja subtitle in the mushroom block.

### Theme colours

All colours are defined inline in the YAML. Key palette:

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
(`sensor.daikin_cycle_ml_*` / `binary_sensor.daikin_cycle_ml_*`), update
the two `var S = {...}` / `var B = {...}` objects near the top of the JS
block. The `UPD` variable points to the HACS update entity.

---

## Entities used

### Sensors (9)

- `sensor.daikin_cycle_ml_cycle_state`
- `sensor.daikin_cycle_ml_current_cycle`
- `sensor.daikin_cycle_ml_last_cycle`
- `sensor.daikin_cycle_ml_cycles_today`
- `sensor.daikin_cycle_ml_quality_today`
- `sensor.daikin_cycle_ml_cop_today`
- `sensor.daikin_cycle_ml_source_health`
- `sensor.daikin_cycle_ml_learned_thresholds`
- `sensor.daikin_cycle_ml_heating_curve_advice`

### Binary sensors (15)

- `binary_sensor.daikin_cycle_ml_compressor_running`
- `binary_sensor.daikin_cycle_ml_heating_active`
- `binary_sensor.daikin_cycle_ml_cooling_active`
- `binary_sensor.daikin_cycle_ml_dhw_active`
- `binary_sensor.daikin_cycle_ml_defrost_active`
- `binary_sensor.daikin_cycle_ml_buh_active`
- `binary_sensor.daikin_cycle_ml_short_run`
- `binary_sensor.daikin_cycle_ml_short_off`
- `binary_sensor.daikin_cycle_ml_pendulum_hourly`
- `binary_sensor.daikin_cycle_ml_pendulum_daily`
- `binary_sensor.daikin_cycle_ml_dhw_pendulum`
- `binary_sensor.daikin_cycle_ml_high_cycle_rate`
- `binary_sensor.daikin_cycle_ml_setpoint_oscillating`
- `binary_sensor.daikin_cycle_ml_source_stale`
- `binary_sensor.daikin_cycle_ml_missing_attributes`

### Update

- `update.daikin_cycle_ml_update`

---

## i18n keys reference

All user-facing strings live in the `STR` object inside the JS block,
grouped by language (`nl`, `en`). Keys:

| Key group | Purpose |
|---|---|
| `sub`, `phase`, `cop`, `runs`, `q`, `src` | Hero block labels |
| `today`, `last`, `dur`, `avgDur`, `avgOff`, `longest`, `sr`, `mode` | Detail sections |
| `dt`, `rps`, `kw`, `outdoor` | Diagram labels |
| `stooklijn`, `state`, `bucket`, `savings`, `comfort`, `reliability` | Stooklijn section |
| `hydKring`, `hpEmitter`, `heatPump`, `emitter`, `supplyLabel`, `returnLabel` | Hydraulic diagram section |
| `lvlCrit`, `lvlWarn`, `lvlInfo` | Alert level headers |
| `noAlert`, `alertOne`, `alertMore`, `explain` | Alert / footer text |
| `phases` (nested object) | Phase names |

The `phases` object is nested. When adding a new language, keep the same
nested structure.

---

## Customisation tips

### Hide the diagram

Find the block starting with the comment `DIAGRAM` in the JS and remove
the lines that append `s` (the SVG) plus the wrapping `<div class="d-sec">`.

### Disable alerts

Replace the block that starts with:

```js
if(alerts.length>0){
```

...with an empty string `''` if you prefer a pure-information card.

### Change the fan animation speed

The `fanDur()` function maps rps to animation duration:

```js
if(r>=75) return '0.4s';
if(r>=40) return '0.8s';
if(r>=15) return '1.5s';
if(r>0)   return '3s';
```

Adjust thresholds or durations as desired.

### Make it read-only (no blinking alerts)

Remove `animation: efp 1.6s ease-in-out infinite;` from the alert
container style.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Card renders as plain YAML text | HACS frontend cards not installed. See **Dependencies**. |
| `Custom element doesn't exist: stack-in-card` | Frontend card not loaded - restart HA, hard-refresh browser. |
| Body shows empty / blank | Check browser console for JS errors. Verify entity IDs match. |
| COP shows a dash placeholder | No COP sample collected yet - check `sensor.daikin_cycle_ml_cop_today` in **Developer Tools -> States**. |
| Language not switching | Verify both `lang_override` (Jinja) and `LANG_OVERRIDE` (JS) are set to the same value. Check for typos - the values are case-sensitive and must be lowercase `'nl'` or `'en'`. |
| Header in NL, body in EN (or vice versa) | `lang_override` and `LANG_OVERRIDE` are out of sync. Set both to identical values. |
| Colours look washed out | Some browsers block CSS gradients in `card_mod` under strict mode. Remove the outer `card_mod.style` block if needed. |
| Preview image missing | Take a fresh screenshot of the card (~800x600) and save it as `preview.png` in this folder. |

---

## Preview generation

To regenerate the preview image for this README:

1. Open the card in a dashboard.
2. Take a screenshot of the card area (~800x600).
3. Save as `preview.png` in this folder.
4. Optional: compress with TinyPNG or PNG-Crush before committing.