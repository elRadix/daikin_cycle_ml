# Diagnostics corpus

Anonymised diagnostics of real installations. They are used for:
- analysis;
- simulations;
- tests (`tests/test_diagnostics_corpus.py`);
- coverage of real-world data (models, ESPAltherma versions, hybrid,
  installs without a DHW tank, basic profile).

## Adding a file (always the same way)

Every diagnostics file that is sent goes through the tool. That covers:
- the "Download diagnostics" file attached to an issue;
- a file pasted in chat;
- prod installs.

Steps:

1. Save the file outside the repository, e.g. `/tmp/diag.json`. A paste
   is fine: the tool repairs stray bracket lines and control characters.
2. Run the tool:

        python tools/ingest_diagnostics.py /tmp/diag.json --origin user --note "short technical note"

3. Check the result:

        pytest --no-cov tests/test_diagnostics_corpus.py

4. Commit the new file and `INDEX.json`.

Use `--origin maintainer` for the maintainer's own installs. The note
describes the installation or the problem, never the person.

## What is kept

- **Installation:**
  - source attributes;
  - options and source resolution;
  - coordinator, detector and store state, including the last cycle;
  - daily summaries;
  - baseline, adaptive, k-means and the stored model states;
  - COP analysis and alert history;
  - entity states with their attributes.
- **Versions:** Home Assistant and integration versions.

## What is removed or replaced

- **Ids:**
  - entry and device ids become a stable 10-character `anon_id` (the
    same installation keeps the same id over time);
  - entity ids that are not the integration's own become
    `sensor.user_N`, consistently within a file.
- **Network and board:** IP, MAC and e-mail addresses; Wi-Fi and board
  data (IP, WifiRSSI, FreeMem, Uptime, M5*); friendly names.
- **Other:** paths, time-zone names, notify targets and setup times.

Reporter names or handles are never stored: not in a file, not in the
index, not in a commit message.

## Index

`INDEX.json` has one row per file. Each row holds:
- file, anon_id, origin, note;
- model, unit model, integration and HA version;
- source type and chosen source;
- hybrid / bivalent, DHW present, power meter;
- cycle and COP sample counts;
- generated_at.
