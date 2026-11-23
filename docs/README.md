# Documentation

Guides and reference for Daikin Cycle ML. Start with the question you
have; every page has its own table of contents.

## Where do I start?

| I want to... | Read |
|---|---|
| Install and set up, with screenshots | [Getting started](GETTING_STARTED.md) |
| A quick answer | [FAQ](FAQ.md) |
| Fix something that does not work | [Troubleshooting](TROUBLESHOOTING.md) |
| Change an option | [Configuration](CONFIGURATION.md) |
| Know what a sensor or service does | [Entities](ENTITIES.md) |
| Understand a notification | [Alerts](ALERTS.md) |
| Add a card to a dashboard | [Cards](../dashboard/cards/README.md) |
| Copy an automation | [Recipes](RECIPES.md) |
| Update, or go back a version | [Upgrade](UPGRADE.md) and the [CHANGELOG](../CHANGELOG.md) |
| Check my heat pump model | [Model compatibility](MODEL_COMPATIBILITY.md) |
| Send a bug report | [Diagnostics](DIAGNOSTICS.md) |
| Contribute | [Development](DEVELOPMENT.md) |

## User guides

| Page | Contents |
|---|---|
| [Getting started](GETTING_STARTED.md) | The ESPAltherma values to enable, every setup-wizard screen, the options menu, the first hour, day and week, hybrid and bivalent systems |
| [FAQ](FAQ.md) | Short answers and the known limitations |
| [Configuration](CONFIGURATION.md) | Source types, wizard paths, every option with its default, COP sources, model profile, reconfigure, cookbook, scheduled jobs |
| [Alerts](ALERTS.md) | The 21 alerts with level, group, repeat window and trigger; delivery, quiet hours, switching alerts off, testing |
| [Troubleshooting](TROUBLESHOOTING.md) | Symptom tables: setup, detection, values, COP, alerts, hybrid, database, cards, reporting |
| [Recipes](RECIPES.md) | Automations ready to paste |
| [Upgrade](UPGRADE.md) | Updating, what migrates on its own, the changes that needed action, going back |

## Reference

| Page | Contents |
|---|---|
| [Entities](ENTITIES.md) | Every sensor, binary sensor, service and repair issue |
| [Machine learning](ML.md) | Quality score, behaviour baseline and `ml_anomaly`, adaptive thresholds, clusters, energy anomaly |
| [Database](DATABASE.md) | Files, tables, `model_state` keys, maintenance, migrations, backup, queries |
| [Diagnostics](DIAGNOSTICS.md) | The diagnostics file: sections, what is removed, how a sent file is anonymised |
| [Model compatibility](MODEL_COMPATIBILITY.md) | ESPAltherma names per model, the alias layer, the per-model matrix, bundled datasheets |
| [Model coverage](MODEL_COVERAGE.md) | Per-model coverage of the values read on ESPAltherma 2.0 |
| [Development](DEVELOPMENT.md) | Environment, tests, quality gates, CI, workflow, quality scale, releases |

## Data files

| File | Contents |
|---|---|
| [`cycle-thresholds.json`](cycle-thresholds.json) | Cycle, pendulum and quality defaults and the sanity gates (kept equal to the code by a test) |
| [`MODEL_ATTRIBUTES.json`](MODEL_ATTRIBUTES.json) | ESPAltherma v1 definition names per model (pinned commit) |
| [`ESPALTHERMA_V2_CATALOG.json`](ESPALTHERMA_V2_CATALOG.json) | ESPAltherma v2 names per definition (pinned commit) |

## Design notes

| Page | Contents |
|---|---|
| [design/ml-winter-simulation.md](design/ml-winter-simulation.md) | The 3-month winter simulation behind ML v2 |
| [design/368-energy-balance-simulation.md](design/368-energy-balance-simulation.md) | Heat-loss and energy-balance feasibility (#368, #490) |
| [design/a3-tick-metrics.md](design/a3-tick-metrics.md) | Coordinator tick metrics in the diagnostics |
