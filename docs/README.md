# Documentation

Guides and reference for Daikin Cycle ML. Start with the question you
have; every page has its own table of contents at the top.

## Where do I start?

| I want to... | Read |
|---|---|
| Install the integration and run the setup wizard | [Configuration](CONFIGURATION.md) §2–§3 |
| Know what a sensor, binary sensor or service means | [Entities](ENTITIES.md) |
| Understand why I got a notification, or tune an alert | [Alerts & Notifications](ALERTS.md) |
| Understand the quality score, learned thresholds or the ML anomaly alert | [Machine Learning](ML.md) |
| Check whether my heat pump model is supported | [Model Compatibility](MODEL_COMPATIBILITY.md) and [Model Coverage](MODEL_COVERAGE.md) |
| Fix something that doesn't work (no cycles, wrong COP, empty cards) | [Troubleshooting](TROUBLESHOOTING.md) |
| Know what changes when I update | [Upgrade Guide](UPGRADE.md) and the [CHANGELOG](../CHANGELOG.md) |
| Query or back up the database | [Database](DATABASE.md) |
| Add a dashboard card | [Shared card settings](../dashboard/cards/README.md) (header, language, dark mode, variables), then the card's own folder in [`dashboard/cards/`](../dashboard/cards/) (README + CHANGELOG) |
| Contribute code or run the tests | [Development](DEVELOPMENT.md) |

## User guides

| Page | Contents |
|---|---|
| [Configuration](CONFIGURATION.md) | Source sensor requirements (ESPAltherma v1 single sensor or v2 entities, AUTO mode), the setup wizard step by step, the options menu (device, sensors incl. power / BUH power / COP sensor, thresholds, notifications, maintenance), reconfigure flows, bivalent / hybrid systems and DHW detection, and a cookbook of common setups. |
| [Entities](ENTITIES.md) | Every sensor and binary sensor with its unit, state class and attributes (cycle state, last cycle with `quality_penalties`, today's runtime / starts / defrosts / BUH, COP day / week / month, SPF, heating-curve advice, learned thresholds, alerts today), the services, the repair issues, and automation examples. |
| [Alerts & Notifications](ALERTS.md) | All alert types and what triggers each one (short run, short off, pendulum, BUH excessive, defrost excessive, COP low / below datasheet, ML anomaly, ...), delivery (persistent notification, notify service), aggregation windows, quiet hours, alert groups, per-alert toggles and message templates. |
| [Machine Learning](ML.md) | The cycle feature vector, the per-mode EWMA baseline and the anomaly z-score, adaptive thresholds (short run, good off, cycles per day), k-means clustering, energy anomaly, retrain schedules, and the **quality score** with its proportional penalty table and examples. |
| [Troubleshooting](TROUBLESHOOTING.md) | Step-by-step checks for setup problems, cycles not detected, missing attributes, alert issues, entity and dashboard problems (cards, languages), database errors, and the log messages that matter. |
| [Upgrade Guide](UPGRADE.md) | Version-by-version breaking changes, migration paths, deprecated options, database migrations, entity renames and how to recover after a downgrade. |

## Reference

| Page | Contents |
|---|---|
| [Database](DATABASE.md) | The SQLite file (`/config/.storage/daikin_cycle_ml_<entry>.db`): every table and column, `model_state` keys, retention and vacuum, all data migrations (v17–v32, quality rescore) with their markers, backup and recovery, disk usage. |
| [Model Compatibility](MODEL_COMPATIBILITY.md) | Which ESPAltherma values the integration reads, the name variants per model (alias layer), the ESPAltherma v1 definition names vs the v2 catalog names (`I/U` / `O/U`, §9.1), the per-model matrix, regeneration workflow and the CI gate, plus the bundled datasheet reference. |
| [Model Coverage](MODEL_COVERAGE.md) | Per-model coverage of the values the integration consumes on ESPAltherma 2.0 (how many resolve directly or through an alias, and what a missing one disables). |
| [Development](DEVELOPMENT.md) | Local and cloud dev setup, running the test suite, CI workflows and quality gates (100 % coverage, ruff, mypy strict, pylint, markdown, model-compat), Integration Quality Scale status, scope boundaries and the release procedure. |

## Data files

| File | Contents |
|---|---|
| [`cycle-thresholds.json`](cycle-thresholds.json) | All cycle-detection, pendulum and quality defaults in one place (kept in sync with the code by a drift test). |
| [`MODEL_ATTRIBUTES.json`](MODEL_ATTRIBUTES.json) | ESPAltherma v1 definition names per model (parsed from `definitions/*.h`, pinned commit). |
| [`ESPALTHERMA_V2_CATALOG.json`](ESPALTHERMA_V2_CATALOG.json) | ESPAltherma v2 names (MQTT keys / Home Assistant ids) per definition from `data/catalog_names.txt`, plus the firmware-computed values (pinned commit). |

## Design notes

| Page | Contents |
|---|---|
| [design/a3-tick-metrics.md](design/a3-tick-metrics.md) | Decision record for the coordinator tick metrics in diagnostics (sample rate, tick duration, slowest-tick phases). |
