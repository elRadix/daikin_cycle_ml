# Changelog · Efficiency card (native)

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
