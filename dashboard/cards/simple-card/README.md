# Simple Card

A compact, one-glance Lovelace card for **Daikin Cycle ML**. Daikin-blue
theme, hydraulic diagram, phase indicator, live alerts, and stooklijn
advice.

![preview](preview.png)

---

## What it shows

| Section | Content |
|---|---|
| **Header** | Title + live subtitle |
| **Hero** | Current phase (IDLE / HEATING / DHW / DEFROST / BUH / COOLING) + animated fan at live rps + COP + Quality |
| **Alerts** | Only when active — colour-coded by severity (crit / warn / info) |
| **Diagram** | Hydraulic loop: warmtepomp -> afgifte, with live rps / kW / dT |
| **Tiles** | COP - Runs today/target - Quality % - Source age |
| **2-col detail** | "Vandaag" (avg duration, avg off, longest, short runs) next to "Laatste cyclus" (duration, dT, rps, mode) |
| **Stooklijn** | Current advice state + bucket + savings % + reliability |
| **Explain** | One-line legend for non-obvious values |

All **25 entities** from the integration are used. Missing values render
as `—` (no errors, no broken layout).

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
2. **Restart Home Assistant** — required after installing a new frontend card.
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

Open `simple-card.yaml`, find the following line inside the **button-card**
JavaScript block (near the top of `custom_fields.content`):

```js
var LANG = 'nl';  /* 'nl' | 'en' */
```

Change to `'en'` for English. All labels, phases, and alerts translate
automatically.

**Supported languages:** `nl` (Nederlands), `en` (English).

To add a new language: copy the `en` block inside the `STR` object and
extend with your own language code. Then change `LANG` accordingly.

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
- `sensor.daikin_cycle_ml_today`
- `sensor.daikin_cycle_ml_quality_today`
- `sensor.daikin_cycle_ml_cop_vandaag`
- `sensor.daikin_cycle_ml_source_health`
- `sensor.daikin_cycle_ml_learned_thresholds`
- `sensor.daikin_cycle_ml_stooklijn_advies`

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

## Customisation tips

### Hide the diagram

Find the block starting with `/* DIAGRAM */` and remove the lines that
append `s` (the SVG) and the wrapping `<div class="d-sec">`.

### Disable alerts

Replace the `if(alerts.length>0){ ... }` block with an empty string
`''` if you prefer a pure-information card.

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
| `Custom element doesn't exist: stack-in-card` | Frontend card not loaded — restart HA, hard-refresh browser. |
| Body shows empty / blank | Check browser console for JS errors. Verify entity IDs match. |
| COP shows `—` | No COP sample collected yet — check `sensor.daikin_cycle_ml_cop_vandaag` in **Developer Tools -> States**. |
| Language not switching | Verify `var LANG = 'en';` has no typo — check capital letters. |
| Colours look washed out | Some browsers block CSS gradients in `card_mod` under strict mode. Remove the outer `card_mod.style` block if needed. |
| Preview image missing | `preview.png` is a 1x1 placeholder — replace with a real screenshot. |

---

## Preview generation

To regenerate the preview image for this README:

1. Open the card in a dashboard.
2. Take a screenshot of the card area (~800x600).
3. Save as `preview.png` in this folder.
4. Optional: compress with TinyPNG or PNG-Crush before committing.
