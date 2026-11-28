# Period reports

Week, month, year and heating-season reports of your heat pump, stored
for good and compared with the previous period or the same period a year
earlier. Shown by the [Reports card](../dashboard/cards/daikin-reports-card/README.md),
available to automations through a sensor and a service.

## Contents

- [1. What is in a report](#1-what-is-in-a-report)
- [2. Periods](#2-periods)
- [3. How a day is checked](#3-how-a-day-is-checked)
- [4. Comparing periods](#4-comparing-periods)
- [5. Degree days](#5-degree-days)
- [6. When reports are built](#6-when-reports-are-built)
- [7. Using the reports](#7-using-the-reports)
- [8. Limits](#8-limits)

## 1. What is in a report

Per mode (heating, hot water, cooling) and for the whole heat pump
(`all`):

| Group | Values |
|---|---|
| Energy | Electricity and heat (kWh), COP = heat ÷ electricity over the days that passed the checks |
| Running | Running time, starts, runs, mean run, starts per running hour, duty cycle |
| Quality | Mean cycle quality (weighted by starts), compressor speed |
| Temperatures | Outdoor mean / coldest / warmest, leaving and return water, ΔT, flow (weighted by running time) |
| Weather | Degree days in every scheme ([§5](#5-degree-days)), COP per 2 K outdoor band |
| Events | Backup-heater minutes, defrosts and defrost time, alerts per type, ML anomalies |
| Coverage | Days in the period, days recorded, days with running, days that passed the checks, failed checks per type |

## 2. Periods

| Period | Key | Bounds |
|---|---|---|
| Week | `2026-W48` | ISO week, Monday to Sunday, local time |
| Month | `2026-11` | Calendar month |
| Year | `2026` | Calendar year |
| Heating season | `2026/27` | From the first day of *Season start month* (Configure → Advanced → Season, default October) for twelve months |

A day is final two days after it ended (late cycle closes and hourly
rollups have landed by then); a period is final once it is over and all its
days are final. Final rows are never rewritten, except by a full rebuild.

## 3. How a day is checked

Every mode of every day is checked; a failing day is stored with its
checks and listed in the card, but the first five checks keep its energy
out of the period COP and out of the comparisons.

| Check | Fails when |
|---|---|
| `no_energy` | More than 10 minutes running with less than 0.05 kWh electricity |
| `cop_out_of_range` | COP below 1, or above 0.65 × Carnot × 1.05 at the day's outdoor and water temperature |
| `heat_mismatch` | The COP samples cover 70 % of the running time and their heat (flow × ΔT) differs more than 15 % from the heat meter |
| `power_mismatch` | Same, for the electrical power |
| `outlier` | The COP is more than 3 MAD from the median of 30 or more earlier days in the same 2 K outdoor band |
| `runtime_bounds` | Running time longer than the day |
| `low_coverage` | Source data for less than 80 % of the day (Home Assistant or ESPAltherma was off) |
| `clock` | The day is not 23, 24 or 25 hours long (clock problem) |

## 4. Comparing periods

The reference is the previous period (week 47 for week 48) or the same
period a year earlier (week 48 of last year; week 53 compares with week 52
when last year had none).

- **Change** of every value, in % or, for quality and the backup-heater
  share, in points.
- **COP, same weather**: both COPs over the outdoor bands both periods
  have (at least two), so a colder month is not a worse heat pump.
- **kWh per degree day**: electricity ÷ degree days (from 10 degree days
  up), the weather-normalised energy use.
- **Trend** over the last 12 periods: the slope of COP, kWh per degree
  day, quality, run length and starts per hour (rising / falling / steady).

Verdicts:

| Metric | Good | Watch | Act |
|---|---|---|---|
| COP (same weather when available) | down less than 3 % | 3-10 % lower | more than 10 % lower |
| kWh per degree day | up less than 5 % | 5-15 % higher | more than 15 % higher |
| Quality | down less than 3 points | 3-10 points lower | more than 10 points lower |
| Mean run | down less than 10 % | 10-30 % shorter | more than 30 % shorter |
| Starts per running hour | up less than 20 % | 20-50 % more | more than 50 % more |
| Backup-heater share | up less than 1 point | 1-5 points | more than 5 points |

The overall verdict is the worst of these. When either period has data on
fewer than 80 % of its days, every verdict reads **incomplete**: the
numbers are shown, never judged as if the period were full.

## 5. Degree days

Every scheme is stored for every day; the comparisons use the one set in
**Configure → Advanced → Season → Degree days**. *Automatic* follows the
country of Home Assistant.

| Scheme | Country | Method |
|---|---|---|
| `nl18` | Netherlands (automatic) | 18 °C − daily mean |
| `nl18w` | Netherlands | Same, × 1.1 November-February, × 0.8 April-September |
| `be1515` | Belgium (automatic) | 15 °C − equivalent temperature (0.6 × today + 0.3 × yesterday + 0.1 × the day before) |
| `be165` | Belgium | Same, base 16.5 °C (Synergrid) |
| `fr18` | France (automatic) | 18 °C − (Tmin + Tmax) ÷ 2 (DJU) |
| `fr17`, `fr15` | France | Base 17 °C or 15 °C |
| `cdd18` | All | Cooling degree days: daily mean − 18 °C |

Other countries use `nl18`. The temperature is the outdoor sensor of the
heat pump, averaged over the whole day; days from before this feature use
the hours the compressor ran.

## 6. When reports are built

- **After the update**, once on the first start, from all history the
  integration still has: daily cycle totals (kept for good), energy and
  runtime per day (400 days), COP samples and hourly COP (365 days). Older
  days get the cycle values only; their coverage shows it.
- **Every night** after the 03:00 maintenance: the days since the last
  build and their periods. The current week / month / year grows until it
  ends.
- **On request**: `daikin_cycle_ml.rebuild_reports` (now), with `full: true`
  to clear and rebuild everything (days older than the kept history are then
  lost).

The tables `daily_stats` and `period_reports` are described in
[Database §2.8](DATABASE.md#28-daily_stats).

## 7. Using the reports

- **Reports card**: `type: custom:daikin-reports-card`
  ([manual](../dashboard/cards/daikin-reports-card/README.md)).
- **Sensor `last_month_report`**: the COP of the last finished month; its
  attributes hold `period`, `el_kwh`, `th_kwh`, `el_per_dd`,
  `cop_vs_previous_pct`, `cop_vs_last_year_pct`, `verdict_vs_previous`,
  `verdict_vs_last_year` and more ([Entities](ENTITIES.md#24-cop)). See the
  [monthly report recipe](RECIPES.md#monthly-report-to-your-phone).
- **Service `get_report`** (*Return response* in Developer tools):

```yaml
action: daikin_cycle_ml.get_report
data:
  period_type: month
  period: "2026-11"
  mode: heating
  compare: last_year
```

- **Service `export_reports`**: days or periods as JSON or CSV, for a
  spreadsheet.

## 8. Limits

- Costs are not part of the reports (tariffs differ too much).
- COP needs electrical energy: without a power sensor or ESPAltherma
  power values, reports show running, temperatures and events only.
- A heat pump replaced or set up again starts a new history.
