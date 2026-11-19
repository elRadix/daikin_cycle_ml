# Changelog — Daily Summary Card (native)

## [1.0.0] — 2026-11-19

### Added
- First native Lovelace card of Daikin Cycle ML,
  `type: custom:daikin-daily-summary-card`. The integration serves and
  loads it: no HACS frontend cards (button-card, stack-in-card,
  card-mod) and no Lovelace resource needed
- Tabs: **Today** (live run with mode, duration and live score; cycles,
  starts, runtime, COP, quality, backup heater and defrosts of today;
  today's alerts, #425), **Overview**, **Quality**, **Cycles**,
  **Duration**, **Events**; 7 / 15 / 30 days
- Tap a day (chart or best / worst day) for its details per mode
- Visual editor (heat pump, title, first tab, days, tabs, language,
  explanations) and an entry in the card picker
- English, Dutch, French; light and dark theme from Home Assistant
- Entities found through the entity registry: any language, several heat
  pumps (`device_id`)
- Same figures as the other cards: quality = average of all cycles
  (#436), average run = runtime / runs on the day
