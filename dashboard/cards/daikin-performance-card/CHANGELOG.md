# Changelog · Performance card (native)

## [1.2.0] - Unreleased

### Fixed

- An EPRA12 at -1 °C / 30 °C making 5.7 kW at 36 rps showed 104 %, "NO
  HEADROOM" and "the backup heater has to help". Daikin's datasheet
  capacities are rating points, not the maximum: the maximum heat is now
  estimated from Daikin's maximum at A7/W35 (else the nominal kW), with
  the datasheet and learned capacities as a minimum, for every model
  (#478). The same case now shows about 62 % and 3.5 kW in reserve.
- "At its limit" only when the water stays more than 2 K below its target
  at a confirmed top speed; the backup heater comes from its own signal
  ("backup heater on while the heat pump has reserve").
- Heat above the maximum raises the maximum to what the unit does.

### Changed

- Dials: **Capacity used**, **Electrical power** (against Daikin's maximum
  power input where published), **COP vs rating point**; the learned
  compressor maximum reads "highest speed seen so far"; source chip
  **Estimate** in the model profile; reserve instead of headroom.
- Three README images: phone, model profile, dark.

## [1.1.0] - 2026-11-21

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
