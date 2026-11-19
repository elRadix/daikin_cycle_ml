# Changelog — Pattern Analysis Card

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
- On opening, the first tab could be highlighted while another tab was
  shown: clicks are now handled from the clicked element (touch devices
  kept a stale hover on the previous tab) and the tab / window are kept
  per card instead of one global for all cards
- Durations read "1u48" in every language; the distribution buckets
  were Dutch in English; the COP tab titles and mode labels are
  translated

## [1.0.0]

Card as shipped before this changelog (see the main
[CHANGELOG](../../../CHANGELOG.md) for its history).
