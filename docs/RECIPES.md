# Recipes

Ready-to-paste automations. Entity ids assume the default device name
(`Daikin Cycle ML`) and an English Home Assistant; on a Dutch or French
install the ids follow the translated names
(`sensor.daikin_cycle_ml_cyclus_status`, ...). Search the entity list by
the end of the id (for example `heating_curve_advice`) when an example
does not match.

More examples:
the [Configuration cookbook](CONFIGURATION.md#6-cookbook).

## Contents

- [Heating-curve advice to your phone](#heating-curve-advice-to-your-phone)
- [Every cycle in the logbook](#every-cycle-in-the-logbook)
- [Daily summary to your phone](#daily-summary-to-your-phone)
- [Monthly report to your phone](#monthly-report-to-your-phone)
- [Alert when ESPAltherma stops updating](#alert-when-espaltherma-stops-updating)
- [Energy dashboard](#energy-dashboard)

## Heating-curve advice to your phone

```yaml
alias: "Daikin: heating-curve advice to phone"
mode: single
triggers:
  - trigger: state
    entity_id: sensor.daikin_cycle_ml_heating_curve_advice
    to: ["lower_lwt", "raise_lwt"]
conditions:
  - condition: template
    value_template: >-
      {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice', 'betrouwbaarheid') | float(0) >= 0.6 }}
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: "Heat pump advice"
      message: >-
        {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice', 'state_label') }}
        · setpoint {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice', 'huidige_setpoint') }}
        → {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice', 'doel_setpoint') }} °C
```

`betrouwbaarheid` is the confidence of the advice (0-1).

## Every cycle in the logbook

```yaml
alias: "Daikin: log cycles"
mode: queued
max_exceeded: silent
triggers:
  - trigger: state
    entity_id: sensor.daikin_cycle_ml_last_cycle
actions:
  - action: logbook.log
    data:
      name: "Heat pump cycle"
      message: >-
        {{ state_attr('sensor.daikin_cycle_ml_last_cycle', 'duration_min') }} min
        · quality {{ states('sensor.daikin_cycle_ml_last_cycle') }}
        · ΔT {{ state_attr('sensor.daikin_cycle_ml_last_cycle', 'dt_avg_k') }} K
        · {{ state_attr('sensor.daikin_cycle_ml_last_cycle', 'mode') }}
```

## Daily summary to your phone

The integration can send its own periodic status update (Configure →
Notifications). For a custom message:

```yaml
alias: "Daikin: daily summary"
mode: single
triggers:
  - trigger: time
    at: "22:00:00"
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: "Heat pump today"
      message: >-
        {{ states('sensor.daikin_cycle_ml_cycles_today') }} cycles
        · COP {{ states('sensor.daikin_cycle_ml_cop_today') }}
        · heating {{ states('sensor.daikin_cycle_ml_electrical_energy_heating_today') }} kWh
```

## Monthly report to your phone

The sensor `last_month_report` changes once a month, after the night the
month is closed ([Reports](REPORTS.md)):

```yaml
alias: "Daikin: monthly report"
mode: single
triggers:
  - trigger: state
    entity_id: sensor.daikin_cycle_ml_last_month_report
    attribute: period
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: "Heat pump {{ state_attr('sensor.daikin_cycle_ml_last_month_report', 'period') }}"
      message: >-
        COP {{ states('sensor.daikin_cycle_ml_last_month_report') }}
        ({{ state_attr('sensor.daikin_cycle_ml_last_month_report', 'cop_vs_last_year_pct') }} % vs last year)
        · {{ state_attr('sensor.daikin_cycle_ml_last_month_report', 'el_kwh') }} kWh
        · {{ state_attr('sensor.daikin_cycle_ml_last_month_report', 'verdict_vs_previous') }}
```

## Alert when ESPAltherma stops updating

```yaml
alias: "Daikin: source stale"
mode: single
triggers:
  - trigger: state
    entity_id: binary_sensor.daikin_cycle_ml_source_stale
    to: "on"
    for: "00:02:00"
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: "ESPAltherma not updating"
      message: "No new values from the heat pump: check the ESP board."
```

## Energy dashboard

The electrical and thermal energy sensors (`..._electrical_energy_heating_today`,
`..._dhw_today`, `..._cooling_today`, `..._total_today`, `..._thermal_energy_*`)
are `total_increasing` and reset at midnight, so the Energy dashboard reads
them directly: **Settings → Dashboards → Energy → Add consumption**. Use a
real power meter as the main source when you have one; these sensors split
it per mode.
