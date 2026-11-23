# Frequently asked questions

## Contents

- [General](#general)
- [Models and setup](#models-and-setup)
- [Alerts and advice](#alerts-and-advice)
- [Data](#data)
- [Known limitations](#known-limitations)

## General

**Does it work without ESPAltherma?**
No. Every value comes from ESPAltherma reading the heat pump's X10A port.
There is no cloud client.

**Does it change settings on my heat pump?**
No, it only reads. The Efficiency card can change the setpoint of a climate
entity you link yourself (Daikin Onecta or similar), only when you press
*apply*.

**Can I use it next to the official Daikin integration?**
Yes. Different data sources, different entities.

**Several heat pumps in one Home Assistant?**
Add the integration once per heat pump. In each native card, choose the
heat pump in the card editor.

## Models and setup

**My model is not in the list.**
Type the code you know in the first wizard screen (indoor unit, outdoor
unit or family and size). Without a datasheet, pick the basic profile, or
*Custom* to enter your own data; the Performance card and **Configure →
Model profile** let you add datasheet values later.

**The wizard says values are missing.**
Enable them in the ESPAltherma definition file and reboot the ESP board
([Getting started §1](GETTING_STARTED.md#1-before-you-start)). Missing
optional values (backup heater, pump, setpoint) only switch off what needs
them.

**How do I change a setting after setup?**
Settings → Devices & services → Daikin Cycle ML → **Configure**.
[Getting started §3](GETTING_STARTED.md#3-changing-settings-later).

## Alerts and advice

**Too many cycling alerts.**
Configure → Pendulum: raise `pendulum_cycles_per_hour` (default 4) or
`short_run_threshold_min` (default 20). See
[Getting started §6](GETTING_STARTED.md#6-first-week).

**`ml_anomaly` fires but nothing looks wrong.**
It flags a cycle that behaves unlike your heat pump's usual cycles at that
outdoor temperature (run length, ΔT, compressor speed, COP, water
temperature, heat). The `top_dim` attribute names the value that stood
out. See [Machine Learning](ML.md).

**The heating-curve advice stays on `no_data` or `keep`.**
Read the `reason` attribute: no recent heating, the backup heater running,
the room already warm enough, or the difference too small to act on. The
advice needs a few days of heating in several outdoor bands.

**COP below the datasheet.**
`cop_vs_datasheet_pct` compares your COP with the datasheet at the same
outdoor and water temperature, from a steady hour of heating. A few
percent below is normal; a lasting -10 % or worse is worth a look (flow,
filters, ΔT, defrosts). See [Alerts](ALERTS.md).

**Why doesn't *Send ALL test notifications* show every alert?**
Home Assistant can merge sidebar notifications sent in one burst, so one
of them (`kmeans_retrain_stale`) may not show in the panel. Phone
notifications all arrive.

## Data

**Where is my data?**
In `/config/.storage/` on your Home Assistant: a SQLite database per heat
pump (`daikin_cycle_ml_<entry>.db`, typically 10-40 MB after a year) and
two small stores (alerts, your datasheets). Nothing leaves your Home
Assistant. Backup: [Database §7](DATABASE.md#7-backup-recovery-and-reset).

**Can I export it?**
Yes: the `export_cycles` and `export_cop_hourly` services write JSON or
CSV. See [Entities §5](ENTITIES.md#5-services).

**What is in a diagnostics file?**
See [Diagnostics](DIAGNOSTICS.md).

**Can I go back to an older version?**
Not officially; see [Upgrade §8](UPGRADE.md#8-downgrade-procedure). Export
first.

## Known limitations

- The energy-anomaly baseline is per mode, not corrected for outdoor
  temperature: a cold snap can raise `energy_daily_anomaly`.
- `label_cycle` stores your labels; they are not used for training.
- Some models use the `(R1T)` suffix for up to three values (outdoor air,
  leaving water, room); the alias layer resolves this per model
  ([Model Compatibility §5](MODEL_COMPATIBILITY.md#5-per-model-matrix)).
- An external sensor in the wrong unit (power in kW instead of W) or a COP
  sensor that reads 0 between runs skips samples without an error; check
  units ([Configuration §2](CONFIGURATION.md#2-source-sensor)).
- Altherma HT units are read from their ESPAltherma definition names; no
  HT install has sent diagnostics yet, so field data is welcome.

Full ML limitations: [Machine Learning §9](ML.md#9-limitations).
