# Changelog — Summary Card

## [1.1.1] — 2026-11-19

### Fixed
- Quality per day weighted by cycles: heating and DHW counted equally,
  so 2 DHW runs weighed as much as 5 heating runs (#436)
- Period quality (header, chart average) = average of all cycles, the
  same figure as the Daily summary tabbed card (#436)
- Quality chart: trend moved to the chart header and band labels to the
  legend; inside the plot they covered the y-axis and the latest point
  (#436)

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
- The card was always Dutch: it now follows the shared language rule and
  has French
- Mode labels were cut to five letters ("Verwa", "Heati")
- Defrost events per day from `events_by_day` (real events, not only
  the cycles with a defrost)

## [1.0.0]

Card as shipped before this changelog (see the main
[CHANGELOG](../../../CHANGELOG.md) for its history).
