# COP & Energy Card

Live COP monitoring card for Daikin Cycle ML. Radial SPF hero gauge, per-mode COP dials, animated RPS-driven fan, and today's energy cascade. Light theme by default, dark theme opt-in, EN/NL auto-detection.

![Showcase](showcase.png)

**Table of Contents**
- [What it shows](#what-it-shows)
- [Requirements](#requirements)
- [Installation](#installation)
- [Variables](#variables)
- [Themes](#themes)
- [Language detection](#language-detection)
- [Section breakdown](#section-breakdown)
- [Entity reference](#entity-reference)
- [Custom entry names](#custom-entry-names)
- [Troubleshooting](#troubleshooting)
- [Data & limitations](#data--limitations)
- [Data flow](#data-flow)

---

## What it shows

| Section | Content |
|---|---|
| **Header** | HP model (auto-detected from `hp_specs`) + specs strip (kW · family · refrigerant) |
| **SPF Hero** | 3-layer radial gauge: 7-grade outer ring, SPF arc, 24h COP polar chart inside. 4 period rows (24h / Week / Month / Year) with sample counts. Deltas row (vs datasheet / 30d trend / week / 365d) |
| **Mode Dials** | 3 mini radial gauges: Heating / DHW / Cooling. Active mode (from `current_cycle.state`) highlighted with tinted background + glow |
| **Live Power** | **Running:** animated 3-blade fan at 12/RPS sec + Electrical → COP → Thermal hero + IN/OUT split bar + COP badge + ΔT/Flow/RPS chips.<br>**Idle:** standby card with ripple icon + last-mode chip |
| **Energy Today** | Single-source energy reads via `thermal_energy_heating_today` attributes. Balance sheet (Elec → COP → Therm), thermal split stacked bar, per-mode detail cards with kWh + implicit COP |

> **vs. the Simple Card:** adds radial SPF gauge with polar 24h chart inside, per-mode mini dials, RPS-driven animated fan, and today's energy cascade with proper thermal split. Removes hydraulic diagram and 15 `binary_sensor` reads.

---

## Requirements

**Backend**
- `daikin_cycle_ml >= v1.19.0`

**Frontend (HACS cards)**

| Card | Repo | Purpose |
|---|---|---|
| **stack-in-card** | [custom-cards/stack-in-card](https://github.com/custom-cards/stack-in-card) | Outer container |
| **mushroom-template-card** | [piitaya/lovelace-mushroom](https://github.com/piitaya/lovelace-mushroom) | Header with icon + title |
| **button-card** | [custom-cards/button-card](https://github.com/custom-cards/button-card) | Body renderer (HTML + SVG) |
| **card-mod** | [thomasloven/lovelace-card-mod](https://github.com/thomasloven/lovelace-card-mod) | Outer border + shadow + theme sync |

*Install each via HACS → Frontend → Explore & Download Repositories. Restart Home Assistant after installing a new frontend card.*

---

## Installation

1. Install the 4 HACS frontend cards (see above).
2. Restart Home Assistant.
3. Hard-refresh browser (`Ctrl`+`Shift`+`R`).
4. Open Lovelace → Edit dashboard → `+ Add Card` → Manual.
5. Open `cop-energy.yaml` (click **Raw** → copy, or right-click → **Save link as**) and copy the entire YAML.
6. Paste it into the manual card editor.
7. *(Optional)* Add a `variables:` block at the top — see [Variables](#variables).
8. Save.

The card auto-detects your HP model, HA language, and entity names. No manual entity-ID edits required if your integration uses the default prefix.

---

## Variables

All variables are optional. Add them at the top of the YAML, before `type:`:

```yaml
type: custom:stack-in-card
variables:
  theme_override: light
  lang_override: ''
```

| Variable | Type | Default | Description |
|---|---|---|---|
| `theme_override` | string | `light` | Force theme: `light`, `dark`, or `auto` (follows OS) |
| `lang_override` | string | `''` | Force language: empty (auto from HA), `en`, or `nl` |

### Examples

**Dark theme:**
```yaml
type: custom:stack-in-card
variables:
  theme_override: dark
```

**Force English labels:**
```yaml
type: custom:stack-in-card
variables:
  lang_override: en
```

**Both:**
```yaml
type: custom:stack-in-card
variables:
  theme_override: dark
  lang_override: en
```

---

## Themes

### Light (default)

| Property | Value |
|---|---|
| **Background** | Soft blue radial `#F5FAFE` → `#DCEBFA` |
| **Primary text** | `#000000` (pure black) |
| **Secondary text**| `#444444` |
| **Border** | 3px solid `#1976D2` |

### Dark (opt-in)
*Set `theme_override: dark` in variables.*

| Property | Value |
|---|---|
| **Background** | Deep navy radial `#001B3D` → `#005a9c` |
| **Primary text** | `#FFFFFF` (pure white) |
| **Secondary text**| `#B0C4DE` |
| **Border** | 3px solid `#00A0E9` |

> The `data-dk-theme` attribute is set on `<html>` by the card's JS, so outer `card-mod` rules match the inner palette immediately — no flash of wrong theme on load.

### Auto
Set `theme_override: auto` to follow `prefers-color-scheme` and HA's `themes.darkMode` setting.

---

## Language detection

**Priority order:**
1. `variables.lang_override` (if `en` or `nl`)
2. `hass.language` (starts with `nl` → Dutch)
3. Default: `en`

| EN | NL (Dutch Translation) |
|---|---|
| HEATING | VERWARMING |
| COOLING | KOELING |
| RUNNING | ACTIEF |
| STANDBY | STANDBY |
| Compressor off | Compressor uit |
| Last | Laatste |
| ENERGY TODAY | ENERGIE VANDAAG |
| THERMAL SPLIT | VERDELING THERMISCH |
| ELECTRICAL | ELEKTRISCH |
| THERMAL | THERMISCH |
| IN | IN |
| OUT | UIT |
| vs datasheet | vs datablad |

---

## Section breakdown

### 1. Header
**Source:** `sensor.daikin_cycle_ml_hp_specs` (state + attributes `kw`, `family`, `refrigerant`)

**Rendered:**
- **Primary:** DAIKIN CYCLE ML · EPRA12EAV3 (uppercase model)
- **Secondary:** 12kW Monoblock · R32 · COP & Energy
- **Icon:** `mdi:heat-pump` in accent color

*Graceful degradation:* Falls back to `Daikin Cycle ML · COP · Energy · live` if `hp_specs` is unavailable or unknown.

### 2. SPF Hero (radial gauge)
**Sources:**
- `sensor.daikin_cycle_ml_spf_season` — main SPF value
- `sensor.daikin_cycle_ml_spf_ytd` — YTD value + `spf_ytd_n` samples
- `sensor.daikin_cycle_ml_scop_running_365d` — 365d rolling
- `sensor.daikin_cycle_ml_cop_curve_recent` — `.points[]` for polar chart
- `cop_mean_{day,week,month}` + `n_samples` for period rows
- `cop_vs_datasheet_pct`, `cop_trend_30d`, `cop_degradation_week_pct` for deltas

**Three concentric layers:**
1. **Outer ring** — 7 colored segments representing grades D → A+++ (`#EF5350` → `#00A0E9`)
2. **Middle arc** — SPF value as thick colored arc, drop-shadow glow in grade color
3. **Inner polar** — 24h heating COP as spider chart (angle = time, radius = COP). Dashed average circle overlay

**Right column:** 4 rows showing 24h · Week · Month · Year with sample counts formatted `244`, `1.4k`, `4.4k`, `4.6k`.

**Footer:** single-line delta row:
```text
vs datasheet -7.4%   30d +11.1%   week +8.7%   365d 5.92
```

### 3. Mode Dials
**Sources:** `cop_heating_day`, `cop_dhw_day`, `cop_cooling_day`, plus `cycle_state` and `current_cycle.state` for active highlight.

**Rendered:** 3 × 80px radial gauges side by side, each showing:
- Arc filled to COP / 8 (max 8)
- COP value in center
- Icon + name below
- Grade label (A+++ / A++ / A+ / A / B / C / D / —)

**Active mode highlight:**
- Background tinted with mode color at 12% opacity
- Border 1.8px mode color
- Soft box-shadow glow behind

*Mode colors:* Heating `#C62828` (red), DHW `#6A1B9A` (purple), Cooling `#38BDF8` (cyan).

### 4. Live Power (Hero)
**Sources:**
- `sensor.daikin_cycle_ml_thermal_power_live` — state (kW) + attributes `input_power_w`, `input_cop`, `input_rps`, `input_dt_k`, `input_flow_lmin`, `calculation_source`
- `sensor.daikin_cycle_ml_electrical_power_estimated` — fallback for `input_power_w`
- `sensor.daikin_cycle_ml_cycle_state` — running or idle
- `sensor.daikin_cycle_ml_current_cycle` — state (mode), `duration_min`, `rps`

**When running**
```text
┌─ RUNNING · 🔥 HEATING ─────── 115.5 min ─┐
│                                          │
│  ⚡ ELECTRICAL  [🌀 fan]  THERMAL        │
│    736 W                 3.98 kW         │
│               25 RPS                     │
│                                          │
│  ⚡ IN (15.6%) ██████░░░░ OUT (84.4%) 🔥│
│                                          │
│           ┌─ COP 5.41 · A++ ─┐           │
│                                          │
│  [ΔT 3.6K] [Flow 15.9 L/m] [RPS 25]     │
└──────────────────────────────────────────┘
```
**Fan animation:**
- 3-blade SVG in mode color
- SMIL `animateTransform` rotation
- Duration = 12 / RPS seconds, clamped [0.3s, 2.5s]
- Static when RPS = 0

**Split bar:** Orange (electrical %) + mode color (thermal %). Labels above show exact percentages — `IN (15.6%)` and `OUT (84.4%)`.

**COP badge:** Pill in mode color with grade, e.g. `COP 5.41 · A++`.

**When standby**
```text
┌──────────────────────────────────────────┐
│                ┌─┐                       │
│                │⏸│ (ripple animation)    │
│                └─┘                       │
│             STANDBY                      │
│          Compressor off                  │
│                                          │
│      🔥 Last: Heating                    │
└──────────────────────────────────────────┘
```
- No fan, no split bar
- Subtle dot-pattern background
- Ripple animation around pause icon
- Last-mode chip shown only when `current_cycle.state` is not idle

### 5. Energy Today
**Source:** Single sensor — `sensor.daikin_cycle_ml_thermal_energy_heating_today` (attributes only). All values from one source of truth:
`heating_th_kwh`, `heating_el_kwh`, `dhw_th_kwh`, `dhw_el_kwh`, `cooling_th_kwh`, `cooling_el_kwh`, `total_th_kwh`, `total_el_kwh`.

**Layout:**
1. **Header** — ENERGY TODAY + total COP (`total_th_kwh / total_el_kwh`)
2. **Balance sheet** — 3-column: ⚡ Elec kWh → ▶ → 🌡 Therm kWh
3. **Thermal split bar** — horizontal stacked bar (heating red / DHW purple / cooling cyan) showing distribution of `total_th_kwh`
4. **Mode detail cards** — one card per active mode:

```text
┌─────────────────────────────┐
│ 🔥 Heat          COP 6.11   │
│ 43.15 kWh Th    5.99 kWh El │
└─────────────────────────────┘
```
*Cooling row appears automatically when `cooling_th_kwh > 0`. Same for DHW when `dhw_th_kwh > 0`.*

---

## Entity reference

Complete list of `daikin_cycle_ml` entities used by the card:

| Entity | Used for | Attributes read |
|---|---|---|
| `sensor.daikin_cycle_ml_hp_specs` | Header model + specs | `state`, `kw`, `family`, `refrigerant` |
| `sensor.daikin_cycle_ml_spf_season` | SPF hero value | `state` |
| `sensor.daikin_cycle_ml_spf_ytd` | Year period row | `state`, `spf_ytd_n` |
| `sensor.daikin_cycle_ml_scop_running_365d` | 365d delta | 
