# Changelog — Daily Summary Tabbed Card

## [1.1.1] — 2026-11-19

### Fixed
- Period quality (Overview, Quality tab) = average of all cycles, the
  same figure as the Daily summary card (#436)
- Average run per day divides by the runs on the day (`runs`, with the
  open run and runs crossing midnight), so it no longer exceeds the
  longest run (#436)

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
- `show_hints` is now `show_help` (the old name still works)
### Fixed
- "cycli" in English, untranslated Today tiles in French; the event
  charts get the real per-day events (`events_by_day` is now exposed by
  the integration)

## [1.0.0]

Card as shipped before this changelog (see the main
[CHANGELOG](../../../CHANGELOG.md) for its history).
