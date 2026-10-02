# 🔥 Heating Curve Card

**Version:** 1.0.0  
**Requires:** daikin_cycle_ml ≥ v1.4.0  
**HA Core:** 2026.9+

A production-ready Lovelace dashboard card visualizing the heating curve of
your Daikin Altherma heat pump. Spec-aware, bilingual, auto-discovering, and
designed to work out of the box with **zero hardcoded entity IDs**.

---

## ⚠️ Read this first — Common failure points

**Before you install, review these pitfalls.** 90% of "the card is broken"
reports stem from one of these issues.

| # | Pitfall | Symptom | Prevention |
|---|---|---|---|
| 1 | **Missing HACS cards** | Blank card, console error `custom element doesn't exist` | Install all 4 HACS cards **before** pasting YAML |
| 2 | **Missing `card-mod`** | Card renders but no border/background/colors | Install `card-mod` via HACS |
| 3 | **Integration < v1.4.0** | All values show `—`, no auto-discovery | Upgrade integration to v1.4.0+ |
| 4 | **YAML indentation corrupted** | `ButtonCardJSTemplateError` in console | Paste raw, don't edit manually |
| 5 | **Variable used before declaration** | `ButtonCardJSTemplateError` naming a var | Don't reorder JS code — it's sequenced |
| 6 | **Power sensor typo** | Thermal kW shows `—` always | Check `configured_power_sensor` points to real entity |
| 7 | **Timezone mismatch (integration bug)** | `cop_mean_day` stays `unknown` | See [known integration bug](#known-integration-bugs) |
| 8 | **Card loaded before HACS ready** | JS errors only on first load | Hard refresh (Ctrl+Shift+R) after install |
| 9 | **Language mismatch** | Card in EN while you speak NL | Match integration `notification_language` to your preference |
| 10 | **Missing attributes on old integration** | Specs box shows `GENERIC` | Fallbacks are built in — no action needed |
| 11 | **`last_cycle` state = `unknown`** | Specs box shows `—` for last cycle | Bug in integration — attributes still work |
| 12 | **Empty `buckets`** | Plot shows only zones | Wait for more cycles — needs ≥ 2 buckets for regression |

**Golden rule:** Always check the **browser console (F12)** first. 90% of
failures produce a clear error message there.

---

## 📖 Table of contents

- [Read this first — Common failure points](#️-read-this-first--common-failure-points)
- [Features](#-features)
- [Requirements](#-requirements)
- [Installation](#-installation)
- [How to use](#-how-to-use)
- [Language settings](#-language-settings)
- [Auto-discovery](#-auto-discovery)
- [Understanding the plot](#-understanding-the-plot)
- [Configuration](#-configuration)
- [Known integration bugs](#-known-integration-bugs)
- [Troubleshooting](#-troubleshooting)
- [FAQ](#-faq)
- [Changelog](#-changelog)

---

## ✨ Features

### 🎨 Visual
- **COP heatmap** — 2D Carnot-based grid behind the plot (red → yellow → green)
- **Heating curve** — HP spec-aware linear regression through bucket data
- **Running average** — weighted moving average overlay (dashed blue)
- **Bucket bubbles** — size = sample count · color = COP quality · labels = n + COP
- **Zone overlays** — defrost (hachure), warm tint, heating OFF, BUH assist band
- **Live dot** — pulsing current outdoor × LWT position with animated ring
- **Collision-aware callout** — auto-positions across 12 candidates to avoid overlapping data
- **Animated buckets** — staggered fade-in on load (0.12s between buckets)

### 📊 Diagnostics
- **Carnot efficiency** — actual vs theoretical maximum COP
- **Heat balance** — demand (flow × ΔT) vs supply (P × COP)
- **Defrost impact** — estimated runtime loss and event count
- **BUH/Defrost timeline** — 24h horizontal strip with hour markers
- **Mode breakdown** — per-mode COP sparkline (heating / DHW / cooling)
- **Rolling trend** — 24h vs 7d COP comparison with arrow indicator

### ⚙️ Auto-discovery
- **HP model** — reads `configured_model`, maps to 14-spec lookup table
- **Sensors** — reads all `configured_*` attributes for footer display
- **No hardcoded entity IDs** — one YAML works across multiple installations
- **Graceful fallbacks** — degrades cleanly when attributes missing (v1.2.0 compatible)

### 🌐 Bilingual
- **Auto-detects language** from `configured_language` attribute
- **NL / EN** fully supported
- **All labels translated** via `t('key')` helper
- **Fallback to English** when attribute missing or unknown

---

## 📦 Requirements

### Backend (integration)

| Component | Version | Required |
|---|---|---|
| **daikin_cycle_ml** | `>= v1.4.0` | ✅ Yes |

**Required entities:**

| Entity ID | Type | Purpose |
|---|---|---|
| `sensor.daikin_cycle_ml_heating_curve_advice` | sensor | Curve data + buckets |
| `sensor.daikin_cycle_ml_cycle_state` | sensor | Config attributes (auto-discovery) |
| `sensor.daikin_cycle_ml_last_cycle` | sensor | Last cycle stats |
| `sensor.daikin_cycle_ml_current_cycle` | sensor | Live cycle: duration / DT / rps |
| `sensor.daikin_cycle_ml_cop_today` | sensor | Today's COP |
| `sensor.daikin_cycle_ml_cop_mean_day` | sensor | Rolling 24h COP |
| `sensor.daikin_cycle_ml_cop_mean_week` | sensor | Rolling 7d COP |
| `sensor.daikin_cycle_ml_cop_curve_recent` | sensor | Mode breakdown data |
| `sensor.daikin_cycle_ml_thermal_power_live` | sensor | Live thermal kW |

**Required attributes on `sensor.daikin_cycle_ml_cycle_state`:**

| Attribute | Example | Purpose |
|---|---|---|
| `configured_language` | `"nl"` / `"en"` | Language detection |
| `configured_model` | `"epra12eav3"` | HP specs lookup |
| `configured_source_sensor` | `"sensor.althermasensors"` | Footer display |
| `configured_power_sensor` | `"sensor.warmtepomp_power"` | Footer display |
| `configured_cop_sensor` | `"sensor.altherma_global_cop"` | Footer display |
| `configured_indoor_sensor` | `"sensor.avg_home"` | Footer display |

### Frontend (HACS cards)

Install **all four** via HACS → Frontend:

| Card | Repository | Required |
|---|---|---|
| `stack-in-card` | [custom-cards/stack-in-card](https://github.com/custom-cards/stack-in-card) | ✅ |
| `mushroom-template-card` | [piitaya/lovelace-mushroom](https://github.com/piitaya/lovelace-mushroom) | ✅ |
| `button-card` | [custom-cards/button-card](https://github.com/custom-cards/button-card) | ✅ |
| `card-mod` | [thomasloven/lovelace-card-mod](https://github.com/thomasloven/lovelace-card-mod) | ✅ |

⚠️ **Order matters:** Install HACS cards **before** pasting the YAML. Otherwise
the card will render blank until the next hard refresh.

### Optional

None. The card **degrades gracefully** when data is missing:
- `cop_curve_recent.points` empty → mode breakdown section hidden
- `heating_curve_advice.buckets` empty → shows zones + heatmap only
- `thermal_power_live` unavailable → balance panel shows `—`
- `configured_*` attributes missing → footer shows `—`, model defaults to `GENERIC`

---

## 🚀 Installation

### Step 1 — Verify prerequisites

```jinja
{## Open: Developer Tools → Template #}

{## Integration version — must be 1.4.0 or higher #}
{{ state_attr('sensor.daikin_cycle_ml_cycle_state','configured_model') }}
{{ state_attr('sensor.daikin_cycle_ml_cycle_state','configured_language') }}

{## Core entities must exist #}
{{ states('sensor.daikin_cycle_ml_heating_curve_advice') }}
{{ states('sensor.daikin_cycle_ml_cycle_state') }}
```

**Expected:** Real values. If any show `unknown` or `None`, fix the integration
first.

### Step 2 — Install HACS cards

For each card in [Requirements → Frontend](#frontend-hacs-cards):

1. Open **HACS → Frontend**
2. Search for the card name
3. Click **Download**
4. **Reload the browser** (Ctrl+Shift+R) after all 4 are installed

⚠️ **Common failure:** Installing cards but not refreshing browser → blank
render.

### Step 3 — Copy the YAML

Copy the entire content of [`heating-curve.yaml`](heating-curve.yaml).

⚠️ **Do not edit** the JS block after pasting — the code is sequenced and
reordering causes `ButtonCardJSTemplateError`.

### Step 4 — Add to Lovelace

1. Open your dashboard
2. Click **⋮ → Edit dashboard**
3. Click **+ Add card → Manual**
4. Paste the YAML
5. Click **Save**

### Step 5 — Verify

- ✅ Card renders without JS errors
- ✅ Header shows `🔵 DAIKIN CYCLE ML`
- ✅ Subtitle shows in your language (NL or EN)
- ✅ Specs box shows your HP model

**If anything fails:** open browser console (F12) → check for errors.

---

## 🎯 How to use

### The plot

Main plot shows the **relationship between outdoor temperature and supply
water temperature** (LWT). Each bubble is a **bucket** — a range of outdoor
temperatures where the heat pump has accumulated samples.

**Reading the plot:**

| Element | Meaning |
|---|---|
| **X-axis** | Outdoor temperature (°C) |
| **Y-axis** | Supply water temperature / LWT (°C) |
| **Red gradient line** | HP spec limit (datasheet curve) |
| **Blue dashed line** | Running average through buckets |
| **Bubbles** | Observed operating points |
| **Live dot** | Current outdoor × LWT position |

### The zones

| Zone | Visual | Meaning |
|---|---|---|
| **❄ DEFROST** | Blue hachure, left | Outdoor < +5°C — defrost cycles active |
| **BUH ASSIST** | Red band, top | LWT > 55°C — backup heater may kick in |
| **Warm** | Subtle blue tint | Mild weather (12-20°C) — efficient zone |
| **HEATING OFF** | Grey, right | Outdoor > +20°C — no heating demand |

### The bubbles

Each bubble represents a **bucket** of outdoor temperatures:

| Bubble element | Meaning |
|---|---|
| **Size** | Sample count (bigger = more data) |
| **Color** | COP quality: 🟢 ≥ 4 · 🟠 2.5-4 · 🔴 < 2.5 |
| **Number inside** | Exact sample count |
| **COP label above** | Average COP for this bucket |
| **Range label** | Outdoor range (e.g., `12-14°C`) |

### The live dot

When the heat pump is active, a pulsing **blue dot** shows the **current**
operating point.

**Callout contents:**

- `XX,X° OUT` — current outdoor temperature
- `XX,X° LWT` — current supply temperature
- `X,XX kW` — live thermal power (if available)

The callout **auto-positions** across 12 candidate locations to avoid
overlapping with bubbles and pills. A **dashed leader line** appears when the
callout is far from the dot (> 50px).

### The BUH/Defrost strip

Beneath the plot, a 24h horizontal strip shows:

- **⚡ BUH lane** (orange) — when backup heater was active
- **❄️ DEF lane** (blue) — when defrost was active
- **Red dashed line** = current hour

### The diagnostics panel

Three compact cards below the strip:

| Card | Value | Meaning |
|---|---|---|
| **CARNOT EFF.** | Actual COP ÷ Carnot max | Efficiency % of theoretical limit |
| **HEAT BALANCE** | Supply - Demand | Positive = surplus, negative = deficit |
| **DEFROST IMPACT** | % of cycle time | Runtime lost to defrost |

### The mode breakdown

For each **active mode** (heating / DHW / cooling) with data in
`cop_curve_recent.points`:

- **Sparkline** = COP over the last 48h
- **Cycles** = number of samples
- **Avg / Last** = mean and most recent COP value

Empty modes are **hidden** — you only see what's active.

### The specs box

Bottom of the card shows detected HP model + operating range + regression formula.

**Format:**
```
⚙ EPRA12EAV3 · MONOBLOCK · 12 kW · R32
LWT 25–60°C · outdoor -25…+35°C · nominal COP 4.2
defrost < +5°C · BUH > 55°C · heating OFF > +20°C
📈 Regression: LWT = 73.8 − 1.86 × T_buiten · samples: 6 · buckets: 5
```

### The KPI tiles

Bottom row shows:

| Tile | Value | Color |
|---|---|---|
| **LWT NOW** | Current supply temp | Red |
| **LWT OPT** | Optimal supply temp | Green |
| **SAVINGS** | Estimated COP savings % | Green if positive |
| **COP TREND** | 24h vs 7d comparison | Green/red/grey |

---

## 🌐 Language settings

### Automatic detection

The card **automatically detects** language from your integration settings.

**How it works:**

1. You set language in the integration OptionsFlow:
   ```
   Settings → Devices & Services → Daikin Cycle ML → Configure
     → Notification language: [nl] [en]
   ```

2. Integration exposes `configured_language` attribute on
   `sensor.daikin_cycle_ml_cycle_state`

3. Card reads this attribute and switches all labels

**No manual switch needed** — change integration language and card follows
within one state-refresh (~30s).

### Fallback behavior

| Scenario | Result |
|---|---|
| Integration on `nl`, attribute present | 🇳🇱 Nederlands |
| Integration on `en`, attribute present | 🇬🇧 English |
| Attribute missing (v1.2.0) | 🇬🇧 English (fallback) |
| Attribute is `null` | 🇬🇧 English |
| Unknown value (e.g., `"fr"`) | 🇬🇧 English |
| Attribute is `"NL"` (uppercase) | 🇳🇱 Nederlands (normalized) |

### Force language manually

If you want the card in a **different language** than the integration, edit
the YAML.

**Find in the JS:**
```js
var cfgLang = String(attr(S_STATE,'configured_language','en')).toLowerCase();
var LANG = (cfgLang === 'nl') ? 'nl' : 'en';
```

**Replace with:**
```js
var LANG = 'nl';   // ← forced Dutch
```

⚠️ **Downside:** you lose auto-detection. The card ignores integration
settings.

### Adding a new language

1. Add a new key to the `STR` object in JS:
   ```js
   var STR = {
     nl: { ... },
     en: { ... },
     fr: {                              // ← new
       defrost:'❄ DÉGIVRAGE',
       heatingOff:'CHAUFFAGE OFF',
       // ... all keys
     }
   };
   ```

2. Update detection logic:
   ```js
   var LANG = (STR[cfgLang] ? cfgLang : 'en');
   ```

---

## ⚙️ Auto-discovery

### How it works

The card reads its **configuration from the integration** — no hardcoded
entity IDs.

**Step 1 — Integration publishes config**

Integration writes config attributes to `sensor.daikin_cycle_ml_cycle_state`:

```yaml
sensor.daikin_cycle_ml_cycle_state:
  attributes:
    configured_language: en
    configured_model: epra12eav3
    configured_source_sensor: sensor.althermasensors
    configured_power_sensor: sensor.warmtepomp_power
    configured_cop_sensor: sensor.altherma_global_cop
    configured_indoor_sensor: sensor.avg_home
    configured_entry_id: 01M3...
```

**Step 2 — Card reads attributes**

```js
var cfgModel = String(attr(S_STATE,'configured_model','')).toLowerCase();
var cfgSource = attr(S_STATE,'configured_source_sensor',null);
// etc.
```

**Step 3 — Card maps model to specs**

```js
var HP_SPECS = {
  'epra04': { kw: 4,  lwtMin: 25, lwtMax: 55, nomCop: 4.6, ... },
  'epra06': { kw: 6,  lwtMin: 25, lwtMax: 55, nomCop: 4.5, ... },
  // ...
  'erla16': { kw: 16, lwtMin: 25, lwtMax: 65, nomCop: 4.1, ... }
};
var hp = HP_SPECS[cfgModel.substring(0,6)] || DEFAULT;
```

### Supported models

| Model prefix | kW | Family | LWT max | Nominal COP |
|---|---|---|---|---|
| `epra04` – `epra08` | 4–8 | Monoblock | 55°C | 4.4–4.6 |
| `epra11` – `epra12` | 11–12 | Monoblock | 60°C | 4.2–4.3 |
| `epra14` – `epra16` | 14–16 | Monoblock | 65°C | 4.0–4.1 |
| `erla04` – `erla08` | 4–8 | Split | 55°C | 4.5–4.8 |
| `erla11` – `erla12` | 11–12 | Split | 60°C | 4.3–4.4 |
| `erla14` – `erla16` | 14–16 | Split | 65°C | 4.1–4.2 |

### Adding a new model

Edit `HP_SPECS` in the JS:

```js
'epra20': { kw: 20, lwtMin: 25, lwtMax: 65, nomCop: 3.9, family: 'Monoblock', ref: 'R32' },
```

The card auto-detects via `configured_model.substring(0,6)`.

### Debug auto-discovery

```jinja
{## Developer Tools → Template #}
Model:    {{ state_attr('sensor.daikin_cycle_ml_cycle_state','configured_model') }}
Language: {{ state_attr('sensor.daikin_cycle_ml_cycle_state','configured_language') }}
Source:   {{ state_attr('sensor.daikin_cycle_ml_cycle_state','configured_source_sensor') }}
Power:    {{ state_attr('sensor.daikin_cycle_ml_cycle_state','configured_power_sensor') }}
COP:      {{ state_attr('sensor.daikin_cycle_ml_cycle_state','configured_cop_sensor') }}
Indoor:   {{ state_attr('sensor.daikin_cycle_ml_cycle_state','configured_indoor_sensor') }}
```

---

## 🔧 Configuration

### Colors

The card uses the **Daikin theme**:

| Color | Hex | Usage |
|---|---|---|
| **Daikin blue** | `#0097E0` | Card border, header, chips |
| **Deep blue** | `#003366` | Titles, axis labels |
| **Mid blue** | `#00539F` | Secondary text |
| **Light blue** | `#E6F4FB` | Card gradient |
| **Daikin red** | `#E60012` | BUH, MAX LWT, critical |

**Semantic colors** (data-driven):

| Color | Meaning |
|---|---|
| 🟢 Green `#4CAF50` | Good COP (≥ 4) · Optimal |
| 🟠 Orange `#F5A623` | Moderate COP (2.5-4) · BUH |
| 🔴 Red `#E60012` | Poor COP (< 2.5) · Critical |
| 🟣 Purple `#9B59B6` | DHW mode |
| 🔵 Blue `#3498DB` | Cooling mode |

### Layout

The SVG canvas auto-sizes to available data. Sections **hide** when empty:

- **Mode breakdown** hidden if no points in `cop_curve_recent`
- **Legend** hidden if fewer than 2 active modes
- **BUH/Defrost markers** hidden if no events
- **Callout** repositions across 12 candidates to avoid overlap

### Transparency tuning

| Element | Default opacity | Where to adjust |
|---|---|---|
| Heatmap | 0.18 | Search `opacity="0.18"` in heatmap group |
| Callout box | 0.82 | Search `fill-opacity="0.82"` in callout |
| Bucket bubble | 0.55 | Search `fill-opacity="0.55"` in bucket loop |
| COP pill | 0.88 | Search `opacity="0.88"` in COP pill |

**Common adjustment:** make the callout more transparent by changing
`fill-opacity="0.82"` to `0.65` or `0.5`.

---

## 🐛 Known integration bugs

These are **integration-side** issues (not card bugs). The card works around
them but the underlying sensors stay `unknown`.

### Bug 1 — `cop_mean_day/week/month` stay `unknown`

**Symptom:**
```yaml
sensor.daikin_cycle_ml_cop_mean_day:
  state: unknown
  n_hours: 0
  n_samples: 0
  by_mode: {}
```

**Root cause:** rollup query timezone mismatch. Integration stores samples in
local epoch but queries with UTC cutoff.

**Impact on card:** `COP TREND` tile shows `—`.

**Workaround:** card falls back to `cop_today` in KPI tiles.

**Report status:** [Open issue on GitHub](https://github.com/elRadix/daikin_cycle_ml/issues)

### Bug 2 — `last_cycle` state stays `unknown`

**Symptom:**
```yaml
sensor.daikin_cycle_ml_last_cycle:
  state: unknown
  duration_min: 77.02      # ← data present
  mode: dhw                # ← data present
  cluster: unknown         # ← string, not null
```

**Root cause:** score = `None` when K-means has no centroids. Cluster label
falls back to string `"unknown"` instead of `null`.

**Impact on card:** cycle score not shown. Attributes still work for
BUH/defrost strip + thermal kW.

**Workaround:** card reads attributes directly, ignoring score state.

### Bug 3 — `quality_today` stays `unknown`

**Symptom:**
```yaml
sensor.daikin_cycle_ml_quality_today:
  state: unknown
  good_cycles: 0
  bad_cycles: 0
  good_ratio_pct: null
```

**Root cause:** cascade from Bug 2. Cycles without score are not counted.

**Impact on card:** quality % not shown.

**Workaround:** KPI tiles hide the quality metric when `ratio === null`.

### Bug 4 — `cluster` attribute is string `"unknown"`

**Symptom:**
```yaml
cluster: unknown    # string, not null
```

**Impact on card:** the check `lastClus !== 'unknown'` catches it — no visual
bug. But the attribute is semantically wrong for other consumers.

**Workaround:** card normalizes via `String(lastClus).toLowerCase() !== 'unknown'`.

**All 4 bugs have been reported and are pending fixes in integration v1.4.1+.**

---

## 🔍 Troubleshooting

### Card doesn't load

**Symptom:** Blank card or JS error in console.

**Causes:**
1. Missing HACS card dependency
2. YAML paste corrupted (missing quotes, indentation)
3. Browser cache out of sync

**Fix:**
```
1. Open browser console (F12)
2. Look for: "custom element doesn't exist"
3. Install missing card via HACS
4. Hard refresh (Ctrl+Shift+R)
```

### All values show `—`

**Symptom:** Every value is a dash.

**Cause:** Integration not v1.4.0 or entities unavailable.

**Fix:**
```jinja
{## Developer Tools → Template #}
{{ states('sensor.daikin_cycle_ml_heating_curve_advice') }}
{{ state_attr('sensor.daikin_cycle_ml_cycle_state','configured_model') }}
{{ state_attr('sensor.daikin_cycle_ml_cycle_state','configured_language') }}
```

Expected: real values. If `unknown` → integration issue.

### Wrong language

**Symptom:** Card shows English while integration is Dutch.

**Cause:** `configured_language` attribute not exposed.

**Fix:**
```jinja
{{ state_attr('sensor.daikin_cycle_ml_cycle_state','configured_language') }}
```
If `None` → upgrade integration to v1.2.0+.

### Model detection fails

**Symptom:** Specs box shows `GENERIC · 12 kW`.

**Cause:** `configured_model` attribute missing or unknown prefix.

**Fix:**
```jinja
{{ state_attr('sensor.daikin_cycle_ml_cycle_state','configured_model') }}
```
If `None` → integration < v1.2.0.
If unknown model → add to `HP_SPECS` table (see [Adding a new model](#adding-a-new-model)).

### No buckets visible

**Symptom:** Empty plot with only zones and heatmap.

**Cause:** Fewer than 1 bucket in `heating_curve_advice.buckets`.

**Fix:** Wait for more cycles. The card shows zones + heatmap regardless.

**Minimum for regression line:** 2 buckets. **Minimum for accurate fit:** 5+
buckets across different outdoor temperatures.

### Live dot missing

**Symptom:** No blue pulsing dot.

**Cause:** Missing `huidige_lwt` (in `heating_curve_advice`) or `outdoor_temp`
(in `current_cycle` or `last_cycle`).

**Fix:**
```jinja
{{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice','huidige_lwt') }}
{{ state_attr('sensor.daikin_cycle_ml_last_cycle','outdoor_temp') }}
```
Both must be numeric.

### Callout overlaps data

**Symptom:** White box hides a bucket.

**Cause:** Extremely dense data or small viewport.

**Fix:** The collision algorithm already tries 12 positions. As last resort, it
clamps inside plot bounds. If still overlapping, adjust `GAP` in the JS:

```js
var GAP = 12;   // try 8 or 16
```

Or reduce callout width:
```js
var callW = 100;  // try 90 or 80
```

### COP trend shows `—`

**Symptom:** `COP TREND` tile shows `—`.

**Cause:** `cop_mean_day` and `cop_mean_week` both `unknown` (see
[Known integration bugs](#-known-integration-bugs)).

**Fix:** Wait for integration fix, or use `cop_today` as a manual fallback:

```js
// In the KPI tile code, replace:
var copDay = st('sensor.daikin_cycle_ml_cop_mean_day', null);

// With:
var copDay = st('sensor.daikin_cycle_ml_cop_mean_day', null) 
          || st('sensor.daikin_cycle_ml_cop_today', null);
```

### `ButtonCardJSTemplateError`

**Symptom:** Console error naming a JS variable.

**Cause:**
1. Variable used before declaration (reordering JS)
2. Syntax error introduced during copy-paste
3. Unescaped character in string literal

**Fix:**
- Revert to the original YAML from `heating-curve.yaml`
- **Do not** reorder lines in the JS
- If you must edit, test in browser console first:

```js
// Paste the whole [[[ ... ]]] block content in console
// Fix any syntax errors there before re-pasting
```

### Card renders but styling is missing

**Symptom:** Card works but no border, gradient, or colors.

**Cause:** `card-mod` not installed or not loaded.

**Fix:**
1. Install `card-mod` via HACS
2. Hard refresh browser
3. Verify in Developer Tools → Console:
   ```js
   customElements.get('card-mod')
   // Should return: class CardMod extends HTMLElement
   ```

### Buckets show stale values

**Symptom:** Bubble values don't update after new cycles.

**Cause:** Card caches last render. Lovelace state-refresh timing.

**Fix:**
- Lovelace refreshes on state change automatically
- If stuck, press Ctrl+Shift+R (hard refresh)
- Check the underlying sensor:
  ```jinja
  {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice','buckets') }}
  ```

---

## ❓ FAQ

### Can I use this card with a different heat pump brand?

**No.** The card is designed for **Daikin Altherma** heat pumps. The zone
thresholds (defrost, BUH, heating OFF) are Daikin-specific.

You could adapt it by:
1. Changing the `HP_SPECS` table for your brand
2. Adjusting zone thresholds (`hp.defrostBelow`, `hp.buhAbove`, `hp.offAbove`)
3. Translating the labels

But the integration `daikin_cycle_ml` is Daikin-specific.

### Can I use this card without `thermal_power_live`?

**Yes.** The card falls back gracefully:
- Live dot callout shows `—` for kW
- Heat balance diagnostics shows `—`
- Everything else works

### Why does the curve go flat at 60°C?

The flat section is the **HP spec maximum** — the point where the compressor
is fully saturated. Above this point (below +7°C outdoor), the heat pump cannot
produce hotter water regardless of demand.

This is **not** a measured value — it's the datasheet limit drawn as reference.

### Why is the live callout sometimes to the left of the dot?

The callout uses **collision-aware positioning**. It tries 12 candidate
positions and picks the one with least overlap with:
- Bucket bubbles
- COP pills
- Range labels
- MAX/MIN LWT chips
- BUH assist chip

A **dashed leader line** appears when the callout is far from the dot (> 50px).

### Can I hide the mode breakdown section?

**Yes.** Delete the relevant block in the JS, or wrap it in a config flag:

```js
var SHOW_MODES = false;   // add at top
if (SHOW_MODES && showModeSection) {
  // ... existing mode breakdown code
}
```

### Why does the regression formula show unusual numbers?

The formula is a **linear fit through your actual bucket data**. If you have:
- Only 2 buckets → very rough fit
- Buckets all on one side → extrapolation is unreliable
- Few samples per bucket → high variance

**Rule of thumb:** wait for 5+ buckets across a wide outdoor range before
trusting the formula.

### Can I export the data as CSV or JSON?

**Not currently.** The card is SVG-only. To export:
1. Use `devtools → template` to read raw attributes
2. Or query SQLite directly:
   ```bash
   docker exec homeassistant sqlite3 \
     /config/.storage/daikin_cycle_ml.db \
     "SELECT * FROM cop_samples WHERE ts > strftime('%s','now') - 86400*7;"
   ```

### Why is the DHW mode sometimes invisible?

DHW cycles are **short** (20-40 min) and often cluster in the morning. If your
`cop_curve_recent.points` has only 1-2 DHW points, the mode breakdown tile
still appears but shows a single large value instead of a sparkline.

Wait for more cycles to build the trend.

### Can I add multiple heat pumps?

**Yes, but requires editing.** The card uses fixed entity IDs
(`sensor.daikin_cycle_ml_*`). For multi-instance setups:

1. Duplicate the YAML
2. Replace all `sensor.daikin_cycle_ml_` with `sensor.daikin_cycle_ml_2_` (or
   whatever your second integration uses)
3. Adjust `S_STATE` for auto-discovery

The integration does not currently support multi-instance discovery.

---

## 📝 Changelog

### v1.0.0 — Initial release
- Heating curve with HP spec-aware visuals
- COP heatmap (Carnot-model based)
- Auto-discovery of model + sensors
- Bilingual NL/EN via integration language
- DHW / cooling mode breakdown (dynamic)
- Running average overlay
- BUH/Defrost timeline strip
- Carnot efficiency diagnostics
- Heat balance diagnostics
- Defrost impact diagnostics
- Collision-aware live dot callout
- Animated bucket appearance (staggered fade-in)
- Inline average label (no more legend overlap)
- All pitfalls documented

---

## 🤝 Contributing

Issues and PRs welcome on GitHub. For language additions, model support, or
feature requests, please open an issue with the `dashboard` label.

**When reporting a bug, include:**
- HA Core version
- Integration version
- Browser console errors (F12 → Console tab)
- Screenshot of the issue
- Output of the debug template:
  ```jinja
  Model:    {{ state_attr('sensor.daikin_cycle_ml_cycle_state','configured_model') }}
  Language: {{ state_attr('sensor.daikin_cycle_ml_cycle_state','configured_language') }}
  State:    {{ states('sensor.daikin_cycle_ml_heating_curve_advice') }}
  Buckets:  {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice','buckets') }}
  ```

---

## 📄 License

Same as the parent project — see repository root for LICENSE.