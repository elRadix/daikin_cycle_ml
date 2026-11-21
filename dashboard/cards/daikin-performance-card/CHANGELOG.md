# Changelog · Performance card (native)

## [1.1.0] - Unreleased

### Added

- Maximum heat learned from your own runs at full speed for conditions
  the datasheet does not list: the thermal dial says "Learned from your
  runs at full speed", the profile shows the Learned chip with the
  number of samples (#473).

### Changed

- Every datasheet capacity is the maximum heat, also on the Hydrosplit
  EPRA; the nominal kW is only used when the datasheet has no capacity
  (#473).

## [1.0.1] - 2026-11-21

### Fixed

- The maximum heat comes from the datasheet when it lists full-capacity
  points (ERLA, EDLA, ERGA, EBLA, EBLQ, EVLQ), otherwise from the nominal
  kW at A7/W35, so the thermal and electrical dials work without typing
  anything (integration fix, #467). On a part-load datasheet (Hydrosplit
  EPRA) the thermal dial says it compares against the nominal capacity.
- Compressor dial without a known speed range shows only the speed.

## [1.0.0] - 2026-11-21

### Added

- First version (#467): thermal load, compressor speed and electrical
  load against the limits of the model chosen in setup at the current
  outdoor and water temperature; COP against the datasheet; headroom
  before the backup heater; verdict.
- Model profile on the card: fill in or adjust the maximum heat and spec
  COP per point and the compressor range, saved in the integration
  (service `set_model_profile`) and used everywhere; source per value.
- English, Dutch and French; dark mode; phone, tablet and desktop widths
  (tested at 360 to 1920 px).
