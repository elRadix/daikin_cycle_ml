# Upgrade Guide

How to update, what happens on its own, and the few changes in the
project's history that needed something from you. What is new in each
release is in the [release notes](https://github.com/elRadix/daikin_cycle_ml/releases)
and the [CHANGELOG](../CHANGELOG.md).

## Contents

- [1. Updating](#1-updating)
- [2. What happens on its own](#2-what-happens-on-its-own)
- [3. Changes that needed action](#3-changes-that-needed-action)
- [4. Coming from an old version](#4-coming-from-an-old-version)
- [5. Going back to an older version](#5-going-back-to-an-older-version)
- [6. If something goes wrong](#6-if-something-goes-wrong)

## 1. Updating

1. **HACS → Daikin Cycle ML → Update** (or copy the new
   `custom_components/daikin_cycle_ml/` for a manual install).
2. **Restart Home Assistant.** A reload of the integration is not enough
   for new translations and new entities.
3. **Refresh the browser once** (`Ctrl`+`Shift`+`R`; in the app, pull
   down) so the native cards load their new version.
4. **YAML cards:** re-paste the YAML from `dashboard/cards/` when the
   release notes list that card; HACS does not update pasted cards.
5. Read the release notes' *After updating* section: it says when a card
   needs re-pasting or an option is worth a look.

Make a Home Assistant backup first if you like; the integration never
needs it to update.

## 2. What happens on its own

- **Database migrations** run once on the first start after an update:
  new columns, rebuilt summaries, rescored history. Each one leaves a marker
  so it never runs twice. They can take a minute on a large database.
  Details: [Database, migrations](DATABASE.md).
- **Options** keep their values. A new option starts at its default; a
  removed one is ignored.
- **Entity ids** stay the same. New entities appear; entities a release
  disables by default stay hidden until you enable them.
- **Native cards** come with the integration and update with it.

## 3. Changes that needed action

In the project's whole history, three releases changed something you
might have relied on. All three migrate on their own; this is what
changed in what you see.

| Release | Change | What to check |
|---|---|---|
| v1.4.0 | Three sensors got English ids: `today` → `cycles_today`, `cop_vandaag` → `cop_today`, `stooklijn_advies` → `heating_curve_advice` | Automations and dashboards using the old ids |
| v1.6.0 | `cop_today` became heating-only; the old blended value is `cop_combined_today`. Options were regrouped (`maintenance` became `advanced`) | Automations reading `cop_today` |
| v1.10.0 | One database per heat pump (`daikin_cycle_ml_<entry>.db`) instead of one shared file | Only with several heat pumps: a repair issue says which entry got the old history; the `assign_legacy_db`, `archive_legacy_db` and `export_legacy_db` services correct it |

## 4. Coming from an old version

Update straight to the latest release: the migrations of every version in
between run in order on the first start. Then:

- check automations against the table in [§3](#3-changes-that-needed-action);
- open **Reconfigure** and pick your exact model if you set it up as
  *Custom* or *Basic profile* before your model was in the list (the list
  now has 61 models and accepts indoor-unit codes);
- add the native cards (Add card → search *Daikin*) and remove YAML cards
  you no longer need.

## 5. Going back to an older version

Not supported. A database migrated by a newer version may not load in an
older one. If you must:

1. **Export what you want to keep:** the `export_cycles` and
   `export_cop_hourly` services write JSON or CSV
   ([Entities §5](ENTITIES.md#5-services)).
2. Note your options (screenshots of Configure).
3. **HACS → Daikin Cycle ML → ⋮ → Redownload** and pick the older version,
   then restart.
4. If the integration does not load: remove it, delete
   `/config/.storage/daikin_cycle_ml_<entry>.db`, restart and add it again.
   History is lost.

A full Home Assistant backup from before the update restores everything,
history included.

## 6. If something goes wrong

**Home Assistant does not start:** rename
`/config/custom_components/daikin_cycle_ml` to `daikin_cycle_ml.disabled`,
restart, read the log, and open an issue with the error.

**The integration does not load:** Settings → Devices & services → Daikin
Cycle ML → ⋮ → Reload; then restart. A `migration_failed` repair or a
database error in the log: see [Troubleshooting §8](TROUBLESHOOTING.md#8-database).

**Entities unavailable or gone:** reload first. Entities a release
disabled by default are under the device's entity list (*+N disabled
entities*).

**Values look wrong after the update:** download the diagnostics
(**Download** / **Copy** at the bottom of a native card) and open an
issue ([what is in the file](DIAGNOSTICS.md)).
