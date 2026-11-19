# Changelog — LWT Fine-Tuning Card

## [1.0.1] — 2026-11-19

### Fixed
- The card re-renders on every Home Assistant state change
  (`triggers_update: all`). It no longer jumps back to the first tab:
  the tab you picked is kept, and `default_tab` is used only until the
  first click (#427)
- An open pop-up is shown again after a re-render for the rest of its
  6 seconds, with fresh values (#427)

### Changed
- Colours: optimal LWT = green, lower LWT = blue, raise LWT = red, in the
  Advice banner and the Analysis offset (#427)

## [1.0.0] — 2026-11-13

Initial release as standalone card in `dashboard/cards/lwt-fine-tuning/`.

### Features
- Four-tab hub layout: **Advice / Buckets / Analysis / Live**
- Hero banner driven by `delta_c` with correct COP interpretation
  (negative delta = lower setpoint = COP savings, not "too cold")
- **Buckets tab**: interactive per-bucket LWT curve with auto-zoom,
  optimal zone band shading, click-for-popup with COP + samples
- **Live tab**: animated real-time marker on LWT range,
  green optimal zone, setpoint + goal dashed lines, auto-scaled
- **Analysis tab**: slope / tracking-error / step-size grid + offset advice
- Auto-locale (EN/NL) with `variables.lang_override` escape hatch
- State-aware "waiting" messages (DHW active / Defrost active / unavailable)
- Header shows Daikin model dynamically if `*_hp_specs` or `*_wp_specs` present
- Multi-line explanation notes per tab, optionally hidden via `show_help: false`

### Configuration variables
- `lang_override`: `'en'` or `'nl'` (default: auto-detect)
- `default_tab`: `'advice'` | `'buckets'` | `'analysis'` | `'live'`
- `show_help`: `true` | `false` (default: true)

### Fixed
- Header title fully EN-localised (no mixed language)
- Delta direction bug: note text agrees with hero banner
- Multi-line note wrapping (`<br><br>` paragraphs)
- Popup placement: falls back below/above when out of viewport

### Known limitations
- Requires ≥2 outdoor-temperature buckets before the chart renders
- Requires `card_mod` + `button-card` + `mushroom-template-card` + `stack-in-card`
- Live tab requires `huidige_lwt` attribute to be present (emitted only during active heating)
