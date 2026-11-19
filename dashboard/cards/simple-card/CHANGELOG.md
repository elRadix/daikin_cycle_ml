# Changelog — Simple Card

## [1.1.0] — 2026-11-19

### Changed (all cards, #427)
- One header for every card: icon, title with the heat pump model, and
  a subtitle with family, power and refrigerant (button-card; the
  mushroom-template-card header and its Jinja are gone, mushroom is no
  longer needed)
- One `variables:` block in the header (`variables: &dcm`), reused by
  every part of the card (`variables: *dcm`): `lang_override`,
  `theme_override`, `show_help`. Variables on the outer stack-in-card
  never reached the cards
- One language rule: `lang_override`, then the HA UI language, then the
  integration language, then English (English, Dutch, French)
- One palette with dark mode: `theme_override: auto` follows the HA dark
  mode; dark backgrounds and light text, readable status colours
- Numbers use the decimal separator of the HA number format

### Fixed
- ΔT of the last cycle was always "—" (read `avg_dt_k`, the sensor
  exposes `dt_avg_k`)
- "Q" and "Quality" show today's quality score (was the share of good
  cycles); the last-cycle header shows its score when there is no cluster
- Cycle state, mode and heating-curve advice are translated (were
  `running` / `heating` / `keep`); advice colours: keep = green

## [1.0.0]

Card as shipped before this changelog (see the main
[CHANGELOG](../../../CHANGELOG.md) for its history).
