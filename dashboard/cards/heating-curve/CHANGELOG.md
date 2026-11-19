# Changelog — Heating Curve Card

## [1.1.1] — 2026-11-19

### Added
- Tap a bucket point for a pop-up: bucket, COP, average LWT, samples and
  whether it is the current bucket. Works on touch; closes on a tap or
  after 6 s and stays open when the card refreshes (#431)

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

### Changed
- The measured buckets are drawn as points only (no halo bubbles, no COP
  pills); bucket, COP, LWT and samples are in the tooltip
- The live point blinks
### Fixed
- During DHW (and BUH) the card kept rendering: the integration keeps
  the measured curve data while the advice is suppressed
- The advice state is translated

## [1.0.0]

Card as shipped before this changelog (see the main
[CHANGELOG](../../../CHANGELOG.md) for its history).
