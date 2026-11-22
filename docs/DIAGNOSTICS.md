# Diagnostics

The diagnostics file is the single most useful thing to attach to a bug
report. This page explains how to get it, what is in it, what is removed,
and what each section helps to find.

## Contents

- [1. Getting the file](#1-getting-the-file)
- [2. What is removed](#2-what-is-removed)
- [3. Sections](#3-sections)
- [4. What happens to a file you send](#4-what-happens-to-a-file-you-send)

## 1. Getting the file

**Easiest: from a native card.** At the bottom of the Daily summary,
Efficiency or Performance card, under *Diagnostics for a bug report*:

- **Download** saves `daikin_cycle_ml_diagnostics.json`;
- **Copy** puts the same file on the clipboard, ready to paste into a
  [GitHub issue](https://github.com/elRadix/daikin_cycle_ml/issues/new/choose).

The card fetches the file for the heat pump it shows. It leaves out the
blocks Home Assistant adds to every download: `custom_components` (every
other custom integration you have installed, often hundreds of lines),
`integration_manifest` and `setup_times`. An administrator account is
needed, as for Home Assistant's own download.

**From Home Assistant:** Settings → Devices & services → Daikin Cycle ML →
⋮ → *Download diagnostics*. This file also contains the three blocks above;
you can delete them before attaching.

## 2. What is removed

Before the file is written, the integration removes:

- secrets: `api_key`, `token`, `access_token`, `refresh_token`,
  `password`, `username`, `client_secret`;
- your location: `latitude`, `longitude`, `elevation`;
- the notify service (`notify.…` becomes `notify.**REDACTED**`, also
  inside text);
- user names and passwords inside URLs.

The file still contains your entity ids and names, the device name and
the ESPAltherma values. Read it first if that matters to you.

## 3. Sections

| Section | What it shows | Helps to find |
|---|---|---|
| `meta` | integration and Home Assistant version, time of the file, UTC offset, redacted keys | which version produced it |
| `entry` | the setup (data and options, redacted), with `model_code`: the model code you typed in the wizard, if any | wrong source, model or option |
| `source` | the ESPAltherma entity and all its attributes at that moment | missing or renamed values, ESPAltherma version |
| `source_resolution` | how the source is read: auto (with coverage of both sources), monolithic (entity, attribute count, custom map) or individual (prefix, values found) | a source that lacks required values |
| `coordinator` | live state and mode, missing attributes, last sample, COP source, power meter, `cop_cross_check`, `runtime_check`, hot-water and boiler detection | wrong mode, COP from the wrong meter, lost runtime |
| `detector` | the cycle detector: state, mode, start time and run duration, pending mode switch, continued run, defrost hold, rps threshold | runs that do not start, stop or split as expected |
| `store` | counters and the last closed cycle | wrong counts, odd last cycle |
| `baseline` | the ML behaviour baseline per mode and its sample counts | anomaly alerts that fire too early or too often |
| `adaptive` | learned thresholds per mode (short run, good pause, cycles per day) with the samples behind them | thresholds that differ from the options |
| `clusters` | k-means centroids, labels, cycles per cluster, stale models | cluster sensors that look wrong |
| `features` | the feature vector of the last closed cycle with its names | ML input that looks wrong |
| `cop_analysis` | heating-curve advice state, outdoor bands with their best water temperature and COP, band edges, COP today, number of COP samples | curve advice and the Curve tab |
| `database` | path, table counts, daily summaries, migrations, integrity, retention, pending COP samples, last vacuum | database errors, missing history |
| `alerts` | which alerts were sent and when | missing or repeated notifications |
| `bivalent` | hybrid and bivalent detection, boiler signals | boiler time counted as heat-pump time |
| `defrost` | defrosts today, current defrost, 7-day limit | defrost alerts |
| `buh` | the backup heater's current step (0 off, 1, 2) and today's seconds per step | backup-heater alerts and energy |
| `model_profile` | your stored model profile, learned compressor range and learned maximum heat | Performance card limits |
| `entities`, `device` | the integration's entities and device as Home Assistant registered them | missing or disabled entities |
| `runtime`, `sampling` | runtime counters and sampling details | today's runtime and COP sampling |
| `notify_health` | failures per notify target | notifications that stopped |
| `coordinator_timing` | slowest update, per step | a slow or blocked Home Assistant |
| `transitions` | recent detector state changes | short cycling, split runs |
| `repairs` | open repair issues of the integration | setup problems |

## 4. What happens to a file you send

A file attached to an issue or sent in a discussion is added to the test
set with `tools/ingest_diagnostics.py`. That tool anonymises it further:

- entry and device ids become an anonymous id;
- entity ids of other integrations become placeholders
  (`sensor.user_1`);
- IP, MAC and e-mail addresses, the time zone, names and Wi-Fi details
  are removed;
- the three Home Assistant blocks of section 1 are dropped.

The tests replay every file in that set on each change, so a problem found
in your file stays fixed. Reporters are never named in the test set (see
`tests/fixtures/diagnostics/README.md`).
