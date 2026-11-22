# Changelog · Efficiency card (native)

## [1.3.1] - 2026-11-22

### Fixed

- With several heat pumps on one Home Assistant (one Daikin Cycle ML
  entry each) and no `device_id` in the card, each sensor was looked up on
  its own, so one card could mix two heat pumps. All sensors now come from
  one heat pump (the first one found); `device_id` picks another.
- The defrost / backup-heater verdict said "Good: no defrost and no backup
  heater today" when there was no data for today at all (sensors still
  unknown, or not found); it now says there is no data yet.

## [1.3.0] - 2026-11-22

### Added

- `climate_entity`: your Daikin climate entity of the leaving water or its
  offset. The Advice tab shows it with − / + one step and **Apply the
  advice**; without it the tab asks for it (#491).
- `room_entity`: a room sensor or room thermostat (temperature and
  setpoint) for the comfort check and the advice; the Advice tab asks for
  a room when there is none (#491).
- Curve tab: every dot has a pop-up in the chart, next to the dot, that
  explains it. The live dot's pop-up is open from the start (water, heat,
  COP and the distance to the fitted curve). The last 48 h are drawn as
  rings, one per hour, newest darkest, with a key line under the legend
  (#491).

### Fixed

- The page no longer jumps back to the top when a sensor updates: the
  card updates only what changed instead of drawing itself again from
  scratch, so the scroll position, the focus and the open view stay
  (#488).
- "Raise the curve: the room stays below its setpoint" next to
  "Comfortable: room 22.5 ° for 22 °": the advice never contradicts the
  comfort check any more, and its tiles show the advised value only when
  the advice is to change (#491).
- The target ΔT stayed at 5 K although the integration was set up with
  a good dT threshold of 4 K (underfloor heating): without the card option
  `target_dt` the card now uses the integration's setting (#492).
- Advanced: liquid − leaving water below −3 K fell off the chart; the
  axis follows the values with round steps, and a negative difference
  reads "below the leaving water" (#491).
- Curve legend: dots for the points, lines for the lines, and every point
  colour listed (COP ≥ 5, 3.5–5, below 3.5, no COP) (#491).

## [1.2.0] - 2026-11-21

### Added

- **What needs attention** at the top of Advice: every check of every tab
  that is ⚠️ or ⛔, worst first, each with its explanation and a link to
  the tab with the graph (#475).
- Dots on the tabs that have something needing attention.

### Fixed

- The header badge said "⛔ Act" while Advice only showed "Keep the
  curve": the badge took checks of other tabs that no tab listed. The
  badge, the tab dots and the list now come from one list; the badge
  shows the count and opens Advice (#475).
- Tiles in two columns on a phone-width card (no "EXPECTE D" breaks).
- Backup-heater text rewritten in EN / NL / FR: it gives 1 kWh of heat per
  kWh, the heat pump 3 to 5, and the usual causes (the Dutch text was not
  correct Dutch).

## [1.1.0] - 2026-11-21

### Added

- Card option **Target ΔT** (`target_dt`, 2-15 K, default 5): the ΔT your
  installer set. The flow graph's target line, the verdicts (low below
  60 % of it, high above it + 3 K) and the help use it. A 3 K
  installation was flagged against a fixed 5 K before (#466)
- Units above the graph axes (°C, rps / W, l/min / ΔT K) and a legend
  entry for every line of the flow graph, with the side of its axis

### Fixed

- On a wide desktop card the graphs were scaled up about 3x, with very
  thick lines and large text. They are now drawn at the card's own width
  and redraw when the card resizes (#466)
- When the history starts inside the chosen time range, the time axis
  starts there instead of squeezing the data against the right edge

## [1.0.1] - 2026-11-21

### Fixed

- COP against the datasheet outside the datasheet points (for example a
  model with A7 values only, at 3 °C outdoor): the nearest point is now
  scaled with the Carnot ratio instead of reused as is, which judged the
  COP too harshly in cold weather (#435 diagnostics)

## [1.0.0] - 2026-11-21

### Added

- First release of `custom:daikin-efficiency-card`, served by the
  integration (no HACS frontend cards needed). Merges the LWT
  fine-tuning, COP & energy and heating-curve YAML cards.
- Live hero: COP (10-min mean), electrical power, heat output and an
  overall status.
- Tabs: Live (setpoint tracker, water, compressor, flow / ΔT, comfort
  and advanced refrigerant graphs with a 30 min / 3 h / 24 h range),
  Today, Efficiency, Curve (heating curve, 24 h backup heater / defrost
  strip, Carnot efficiency, heat balance, defrost, specifications) and
  Advice.
- Every graph and tab has a verdict (good / watch / act / info) on the
  current state, within the datasheet limits of the configured model,
  and a help section that explains the graphs with those limits.
- English, Dutch and French; light and dark theme; visual editor.
