# Changelog · Efficiency card (native)

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
