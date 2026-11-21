# Changelog · Performance card (native)

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
