# Model Compatibility

Which Daikin Altherma models work with Daikin Cycle ML, which ESPAltherma
definition labels are required, and how the compatibility matrix is
regenerated.

- **Covers:** canonical sensors, variant unions, 40-model coverage matrix, decoy register, whitespace contract, regeneration workflow, CI gate
- **For:** contributors adding model support, users diagnosing missing_attributes repairs, maintainers regenerating after upstream moves
- **Version:** v1.14.0

Cross-references: [DATABASE.md](DATABASE.md) (cop_samples semantics), [CONFIGURATION.md](CONFIGURATION.md) (attribute mapping), [DEVELOPMENT.md](DEVELOPMENT.md) (CI workflows).

---

## 1. Why this document exists

Daikin's ESPAltherma project publishes definition files (definitions/*.h)
per heat-pump family. Each definition contains a LabelDef struct init per
ESPAltherma attribute. Users uncomment the labels they need. The union of
commented + uncommented labels is the compatibility set Daikin Cycle ML
must accept.

The integration resolves those labels through engine/attribute_compat.py
(ALIAS_GROUPS). The engine works with CANONICAL labels. ESPAltherma
upstream sometimes renames a label (v1 beta renamed
"Outdoor air temp.(R1T)" to "R1T-Outdoor air temp." for 34 of 40 models
in the #150 window). ALIAS_GROUPS bridges both spellings so users on
either upstream beta stay functional.

This document is the source of truth for:

- Which canonical labels the integration needs
- Which models publish them (per label)
- Which models have known gaps (partial support)
- How the compatibility matrix stays current

---

## 2. Canonical sensors

11 labels are canonical. The engine uses them by name; ALIAS_GROUPS
maps known alternates. Every label here is covered by
tests/test_model_compat.py.

| Canonical label | Purpose |
|---|---|
| Operation Mode | Cycle classification (heating/cooling/DHW/defrost) |
| Thermostat ON/OFF | Demand detection |
| Defrost Operation | Cycle exclusion gate |
| Leaving water temp. before BUH (R1T) | Heat-side primary signal (dT, COP) |
| Leaving water temp. after BUH (R2T) | BUH state and post-BUH temperature |
| Inlet water temp.(R4T) | Return water (heating dT cold side) |
| Outdoor air temp.(R1T) | Weather normalization (Carnot, SPF) |
| Refrig. Temp. liquid side (R3T) | Physics sanity check |
| DHW tank temp. (R5T) | DHW-side dT cold side |
| Flow sensor (l/min) | Thermal power calculation |
| INV frequency (rps) | Compressor workload |

---

## 3. Variant union

ESPAltherma v1 (translated labels, punctuation drift) and v2 (English-
only) produce different attribute spellings for the same physical
sensor. The compat layer materializes every alias spelling as soon as
one member of the alias group is present, and it tolerates whitespace
and punctuation drift.

Concrete examples from ALIAS_GROUPS:

| Canonical | Known alternates (v1, translations, renames) |
|---|---|
| Leaving water temp. before BUH (R1T) | Leaving water temp.(R1T), Leaving water temp. (R1T), Vorlauf vor BUH (R1T), [HPSU] Tv inflow Temp (R1T) |
| Inlet water temp.(R4T) | Inlet water temp. (R4T), Inlet water temp.(C), [HPSU] Tr return Temp (R4T), Inlet temperature(R4T) |
| Outdoor air temp.(R1T) | R1T-Outdoor air temp., Outdoor air temp. (R1T), Outdoor air temp.(C) |
| DHW tank temp. (R5T) | DHW tank temp.(R5T), DHW temperature(R5T) |
| Operation Mode | Betriebsart, Mode de fonctionnement |
| Thermostat ON/OFF | Thermostat EIN/AUS |
| Defrost Operation | Abtauung |

The alias list is authoritative in engine/attribute_compat.py
(ALIAS_GROUPS). Adding a new alias is a code change, not a doc change.

---

## 4. Mandatory attributes and coverage

The engine requires 12 attributes for full heating support, imported
from const.REQUIRED_ATTRIBUTES (see const.py). The full list is:

- Operation Mode
- I/U operation mode
- 3way valve(On:DHW_Off:Space)
- Defrost Operation
- Leaving water temp. after BUH (R2T)
- Inlet water temp.(R4T)
- Outdoor air temp.(R1T)
- Flow sensor (l/min)
- Water pump operation
- BUH Step1
- BUH Step2
- LW setpoint (main)

24 of 31 heating models cover all 12. The remaining 7 have documented
gaps (see section 6). The partition is enforced by tests:

- tests/test_model_compat.py::test_required_attrs_fully_covered (24 tests)
- tests/test_model_compat.py::test_partial_models_match_expected (7 tests)
- tests/test_model_compat.py::test_heating_partition_complete (1 test)

If upstream removes a required label for a full model, CI fails before
merge. This is the fail-safe against the #150 class.

---

## 5. Per-model matrix

6 key R-label attributes, alias-aware. Y means the model publishes at
least one known spelling of that label. Regenerated from
docs/MODEL_ATTRIBUTES.json.

| Model | Before BUH R1T | After BUH R2T | Inlet R4T | DHW R5T | Outdoor R1T | Flow |
|---|---|---|---|---|---|---|
| 4(EPSK-EPSKS EPBX-EPSX-EPVX-EPVZ series 04...) | Y | Y | - | Y | Y | Y |
| EBLA-EDLA D series 4-8kW Monobloc | Y | Y | Y | Y | Y | Y |
| EBLA-EDLA D series 9-16kW Monobloc | Y | Y | Y | Y | Y | Y |
| EGSAH-X-EWSAH-X-D series 6-10kW GEO3 | Y | Y | Y | Y | Y | Y |
| EGSQH-A series 10kW GEO2 | Y | Y | Y | Y | Y | Y |
| EPGA D EAB-EAV-EAVZ D(J) series 11-16kW | Y | Y | Y | Y | Y | Y |
| EPRA D ETSH-X 16P30-50 D series 14-16kW-ECH2O | - | - | Y | Y | Y | Y |
| EPRA D ETV16-ETB16-ETVZ16 D series 14-16kW | Y | Y | Y | Y | Y | Y |
| EPRA D_D7 ETSH-X 16P30-50 E_E7 series 14-1... | Y | Y | Y | Y | Y | Y |
| EPRA D_D7 ETV16-ETB16-ETVZ16 E_E7 series 1... | Y | Y | Y | Y | Y | Y |
| EPRA E ETSH-X 16P30-50 E series 8-12kW-ECH2O | Y | Y | Y | Y | Y | Y |
| EPRA E ETV16-ETB16-ETVZ16 E_EJ series 8-12kW | Y | Y | Y | Y | Y | Y |
| ERGA D EHSH-X P30-50 D series 04-08kW-ECH2O | - | - | Y | Y | Y | Y |
| ERGA D EHV-EHB-EHVZ DA series 04-08kW | Y | Y | Y | Y | Y | Y |
| ERGA D EHV-EHB-EHVZ DJ series 04-08 kW | Y | Y | Y | Y | Y | Y |
| ERGA E EHSH-X P30-50 E_EF series 04-08kW-E... | Y | Y | Y | Y | Y | Y |
| ERGA E EHV-EHB-EHVZ E_EJ series 04-08kW | Y | Y | Y | Y | Y | Y |
| ERLA D EBSH-X 16P30-50 D SERIES 11-16kW-ECH2O | Y | Y | Y | Y | Y | Y |
| ERLA D EBV-EBB-EBVZ D SERIES 11-16kW | Y | Y | Y | Y | Y | Y |
| ERLA03 D EHFH-EHFZ DJ series 3kW | Y | Y | Y | Y | Y | Y |
| HT EKHBRD-ERRQ series 11-16kW protocol S | - | - | - | - | - | - |
| HT EKHBRD-ERRQ series 11-16kW | - | - | - | - | - | - |
| HT ERRQ-ERSQ outdoor unit 11-16kW | - | - | - | - | - | - |
| Hybrid | - | - | Y | Y | - | Y |
| LT_CA_CB_04-08kW | Y | Y | Y | Y | Y | Y |
| LT_CA_CB_11-16kW | Y | Y | Y | Y | Y | Y |
| LT_CB_04-08kW Bizone | Y | Y | Y | Y | Y | Y |
| LT_CB_11-16kW Bizone | Y | Y | Y | Y | Y | Y |
| LT_EBLQ-EBLQ-CA series 5-7kW Monobloc | - | - | Y | Y | Y | Y |
| LT_EBLQ-EDLQ-CA series 11-16kW Monobloc | Y | Y | Y | Y | Y | Y |
| LT_Multi_DHWHP | Y | Y | Y | Y | Y | Y |
| LT_Multi_Hybrid | Y | Y | Y | Y | Y | Y |
| CKHWS-BJV3(Multi DHW tank 2) | Y | Y | Y | Y | Y | Y |
| DEFAULT | - | - | Y | Y | - | - |
| Daikin Mini chiller(EWAA-EWYA D series 4-8kW) | Y | Y | Y | Y | Y | Y |
| Daikin Mini chiller(EWAA-EWYA D series 9-16kW) | Y | Y | Y | Y | Y | Y |
| Daikin Mini chiller(EWAQ-EWYQ B series 4-8kW) | - | - | Y | Y | Y | Y |
| EKHWET-BAV3(Multi DHW tank) | Y | Y | Y | Y | Y | Y |
| PROTOCOL_S | - | - | - | - | - | - |
| PROTOCOL_S_ROTEX | - | Y | - | - | - | - |


## 6. Special-case models

### 6.1 Cooling-only (3 models)

Daikin Mini Chiller (EWAA-EWYA D 4-8kW, EWAA-EWYA D 9-16kW,
EWAQ-EWYQ B 4-8kW). Publish R4T, R5T, flow, and refrigerant labels
but no heating/BUH attributes. Supported for cooling; skipped from the
heating coverage check.

### 6.2 DHW-tank only (2 models)

CKHWS-BJV3 (Multi DHW tank 2) and EKHWET-BAV3 (Multi DHW tank).
Multi-DHW tanks, no compressor cycle. Publish only tank temperatures.

### 6.3 Alternative protocols (2 models)

PROTOCOL_S.h and PROTOCOL_S_ROTEX.h publish a distinct label set
(entirely different attribute names). Used for protocol-S installations.
The integration detects schema via detect_schema() and reports missing
required attributes as a repair issue, not a crash.

### 6.4 Empty template (1 model)

DEFAULT.h is a skeleton with no labels. Parsed but contributes zero
attributes. Skipped from all coverage checks.

### 6.5 Partial heating models (8 models)

Documented gaps per model. Maintained in tests/test_model_compat.py
(PARTIAL_MODELS dict). Any change must be justified by re-analysis of
the upstream .h file:

- Altherma 4 (EPSK-EPSKS EPBX-EPSX-EPVX-EPVZ 04-14kW): missing R4T.
  Header: "the indoor unit's inlet (R4T) is not on the wire".
- Altherma (EPRA D ETSH-X 16P30-50 D 14-16kW ECH2O): missing R2T.
  Water heat exchanger in outdoor unit, no BUH-only sensor.
- Altherma (ERGA D EHSH-X P30-50 D 04-08kW ECH2O): missing R2T. Same reason.
- Altherma (HT EKHBRD-ERRQ 11-16kW protocol S): missing 11 of 12 required.
  HT-protocol exposes a minimal set; setup reports missing_attributes.
- Altherma (HT EKHBRD-ERRQ 11-16kW): missing all 12. HT-protocol variant.
- Altherma (HT ERRQ-ERSQ outdoor unit 11-16kW): missing 8 of 12. Outdoor-only
  definition — no water-side sensors (inlet, flow, BUH, 3-way, pump).
  Hydrobox labels live in the EKHBRD-ERRQ variants above.
- Altherma (Hybrid): missing R2T and outdoor R1T. Hybrid uses a different
  cold-side sensor; R1T outdoor not published on the wire.
- Altherma (LT_EBLQ-EBLQ-CA 5-7kW Monobloc): missing R2T. CA-series
  Monobloc without BUH after sensor.

---

## 7. Decoy register

These labels resemble canonical sensors but are NOT. Never promote them
to canonical, never substring-match on R4T/R5T/R1T to find them.

| Decoy | Why it looks right | Why it is wrong |
|---|---|---|
| Heat exchanger mid-temp.(R5T) | Contains R5T | Refrigerant mid-temp, not DHW tank |
| O/U Heat Exch. Temp.(R4T) | Contains R4T | Refrigerant heat exchanger, not inlet water |
| Indoor ambient temp. (R1T) | Contains R1T | Indoor ambient, not outdoor air |
| Leaving water temp. before BUH (R1T) | Contains R1T | Leaving water, not outdoor air |

The 4th is canonical for a DIFFERENT sensor (the leaving-water side).
It appears in CANONICAL_LABELS and is not a decoy in that context. When
searching for "the R1T attribute", always use exact match against the
canonical name; never grep for 'R1T'.

tests/test_model_compat.py::test_decoy_not_canonical guards the first 3.

---

## 8. Whitespace and punctuation contract

normalize_key() (engine/attribute_compat.py) collapses whitespace and
tolerates punctuation drift. Concretely:

- Multiple spaces = one space
- " (R4T)" and "(R4T)" are equivalent
- "[HPSU] Tr return Temp (R4T)" resolves via ALIAS_GROUPS, not via regex

The parser (tools/parse_espaltherma_defs.py) preserves raw label text
from .h files. Whitespace normalization happens at resolution time, not
at parse time. This means MODEL_ATTRIBUTES.json is a faithful index of
upstream spelling; the compat layer handles drift.

---

## 9. Regeneration workflow

When ESPAltherma upstream publishes new definitions:

    git clone --depth 1 --branch beta \
      https://github.com/raomin/ESPAltherma /tmp/espaltherma-beta

    python3 tools/parse_espaltherma_defs.py \
      --source /tmp/espaltherma-beta \
      --branch beta \
      --out docs/MODEL_ATTRIBUTES.json

    pytest tests/test_model_compat.py -q --no-cov

If all 130 tests pass, commit the regen. If any fail, the change is
either a new label (extend ALIAS_GROUPS) or a renamed/removed label
(investigate). Never edit MODEL_ATTRIBUTES.json by hand.

For minor upstream moves (SHA change, no label diff), the weekly drift
workflow opens an issue automatically (see section 10).

---

## 10. CI gate

Two workflows in .github/workflows/model-compat.yml:

### pr-gate

Triggered when a PR touches:
- docs/MODEL_ATTRIBUTES.json
- tools/parse_espaltherma_defs.py
- engine/attribute_compat.py
- const.py (REQUIRED_ATTRIBUTES)

Steps:
1. Clone ESPAltherma at _meta.branch
2. Re-parse into /tmp/regen.json
3. Assert set(tracked.labels) == set(regen.labels)
4. Assert 11 canonical labels resolvable
5. Assert 3 decoys not canonical
6. Assert 40 models present
7. Assert SHA in _meta.commit matches the cloned SHA

Fails the PR if any assertion fails. Human must fix ALIAS_GROUPS or
regen in the PR branch.

### weekly-drift

Cron: Monday 06:00 UTC.

1. git ls-remote refs/heads/beta -> upstream_sha
2. Read _meta.commit from MODEL_ATTRIBUTES.json -> pinned_sha
3. If equal: exit 0 (silent)
4. If different: open (or update) issue labeled model-compat

The issue is idempotent: an existing open issue with the same label is
edited, not duplicated. The workflow never auto-merges or auto-regenerates.

---

## 11. Changelog

| Version | Change |
|---|---|
| v1.12.9 (PR B) | First tracked MODEL_ATTRIBUTES.json + parser + 130 tests + CI gate + weekly drift |
| (pre-v1.12.9) | Untracked manual extraction, no CI coverage |

---

## Bundled model datasheet reference

Public Daikin datasheet values for the 53 technical model codes plus 1 commercial alias (ERGA08EVH7 -> ERGA08EAV3). COP values are nominal (EN 14511). Where a value is not cleanly published across regional datasheets it is marked `—`.

### LT monobloc — EBLQ CV3 (R-410A)

| Model | COP A7/W35 | COP A7/W55 | Nom. heating (kW) | Max LWT |
|---|---|---|---|---|
| EBLQ05CV3 | 5.00 | 3.58 | 4.40 | 55 °C |
| EBLQ07CV3 | 4.52 | 3.42 | 7.00 | 55 °C |
| EBLQ11CV3 | 4.61 | 3.55 | 11.2 | 55 °C |
| EBLQ14CV3 | 4.30 | 3.32 | 14.5 | 55 °C |
| EBLQ16CV3 | 4.26 | 3.26 | 16.0 | 55 °C |

### HT split — EKHBRD + ERRQ (R-410A)

| Model | COP A7/W55 | COP A7/W80 | COP A7/W35 | Nom. heating (kW) |
|---|---|---|---|---|
| EKHBRD011 + ERRQ011 | 2.97 | 2.50 | 4.20 | 11.3 |
| EKHBRD014 + ERRQ014 | 2.89 | 2.48 | 3.72 | 14.5 |
| EKHBRD016 + ERRQ016 | 2.73 | 2.41 | 3.72 | 16.0 |

### HT outdoor — ERRQ-ERSQ (R-410A)

| Model | COP A7/W55 | COP A7/W80 | Nom. heating (kW) | Power input (kW) |
|---|---|---|---|---|
| ERRQ011-ERSQ011 | 3.08 | 2.50 | 11.0 | 3.57 |
| ERRQ014-ERSQ014 | 3.00 | 2.48 | 14.0 | 4.66 |
| ERRQ016-ERSQ016 | 2.88 | 2.41 | 16.0 | 5.57 |

### Altherma 4 H — EPSK AW1 (R-290)

| Model | COP A7/W35 | SCOP | Max LWT |
|---|---|---|---|
| EPSK06AW1 | 5.19 | — | 70 °C |
| EPSK08AW1 | 5.01 | — | 70 °C |
| EPSK10AW1 | 4.94 | — | 70 °C |
| EPSK12AW1 | 5.50 | 5.14 | 70 °C |
| EPSK14AW1 | 5.50 | 4.96 | 70 °C |

### LT monobloc — EDLA D3V3 (R-32)

| Model | COP A7/W35 | COP A7/W55 | Nom. heating (kW) | Max LWT |
|---|---|---|---|---|
| EDLA09D3V3 | 4.91 | 3.71 | 9.4 | 65 °C |
| EDLA11D3V3 | 4.83 | 3.66 | 11.0 | 65 °C |
| EDLA14D3V3 | 4.87 | 3.64 | 14.0 | 65 °C |
| EDLA16D3V3 | 4.53 | 3.51 | 16.0 | 65 °C |

### LT monobloc — EBLA EV3 (R-32)

| Model | COP A7/W35 | COP A7/W55 | Nom. heating (kW) | Max LWT |
|---|---|---|---|---|
| EBLA04EV3 | 5.10 | 3.65 | 4.3 | 65 °C |
| EBLA06EV3 | 4.85 | 3.50 | 6.0 | 65 °C |
| EBLA08EV3 | 4.60 | 3.50 | 7.3 | 65 °C |

### LT split — ERGA EAV3 (R-32)

| Model | COP A7/W35 | COP A7/W55 | Max LWT |
|---|---|---|---|
| ERGA04EAV3 | 5.10 | 3.65 | 65 °C |
| ERGA06EAV3 | 4.85 | 3.50 | 65 °C |
| ERGA08EAV3 | 4.60 | 3.50 | 65 °C |

### LT split high capacity — EPGA DAV3 (R-32)

| Model | COP A7/W35 | COP A7/W55 | Max LWT |
|---|---|---|---|
| EPGA10DAV3 | 5.15 | 3.88 | 60 °C |
| EPGA11DAV3 | 5.15 | 3.88 | 60 °C |
| EPGA14DAV3 | 4.99 | 3.65 | 60 °C |
| EPGA16DAV3 | 4.78 | 3.71 | 60 °C |

### HT split — EPRA18 (R-32)

| Model | COP A7/W35 | COP A7/W55 |
|---|---|---|
| EPRA18EAV3 | 5.00 | — |

### Excluded families — reference only

GEO2 and GEO3 are ground-source (brine) and remain outside `MODEL_CHOICES` per project scope (`test_no_model_expects_brine`).

| Model | COP B0/W35 | COP B0/W55 |
|---|---|---|
| EGSQH10A9W | 4.35 | 3.29 |
| EGSAH06D9W | 4.51 | — |
| EGSAH10D9W | 4.70 | — |

Chillers (EWAA/EWYA/EWAQ/EWYQ), Hybrid, Multi, DHW tanks and PROTOCOL_S templates are not single-model heat pumps and are not listed here.

## Runtime COP curve coverage

The `data/datasheets.json` file drives the `cop_vs_datasheet_low` alert and the `cop_vs_datasheet_pct` sensor. Coverage per model:

| Curve status | Models | Behavior |
|---|---|---|
| **full** (6-9 points, incl. `hc`) | `erla11dav3`, `erla14dav3`, `erla16dav3`, `epra08eav3`, `epra10eav3`, `epra12eav3` | T_out-aware: interpolates COP at actual outdoor temp |
| **partial** (2 points, A7/W35 + A7/W55) | `erga04eav3`, `erga06eav3`, `erga08eav3`, `ebla04ev3`, `ebla06ev3`, `ebla08ev3`, `epga11dav3`, `epga14dav3`, `epga16dav3` | Linear interpolation between two known points |
| **nom_cop only** (1 point or empty) | Rest of bundled models | Falls back to A7/W35 comparison — alert may false-positive at outdoor temperatures below 0 °C |

### Supplying your own datasheet

For `nom_cop only` models the alert uses A7/W35 as reference regardless of outdoor temperature. To make it T_out-aware, supply your model's COP table via the `daikin_cycle_ml.upload_datasheet` service (see `services.yaml`). User-supplied data overrides bundled data.


## Changing your model

Your model code is **config entry data** (setup-time configuration), not
a runtime option. Changing it is a reconfiguration, not an options
change — this follows Home Assistant's
[config entry data vs. options](https://developers.home-assistant.io/docs/config_entries_config_flow_handler/)
guideline.

### How to change your model

1. Go to **Settings → Devices & Services → Daikin Cycle ML**
2. Click **Reconfigure** on your entry
3. Choose **Source sensor and model only (quick)** — the fast path
   (or **Full wizard (all settings)** if you also want to review
   sensors, thresholds, or notifications)
4. Pick the new model from the dropdown
5. Save — the integration reloads automatically

The model controls:

- Behavioural profile (`MODEL_PROFILES` — thresholds, cycle targets)
- Datasheet curve lookup (`cop_vs_datasheet_pct`,
  `cop_vs_datasheet_low` alert)
- Wizard defaults for new setups

### Why not the OptionsFlow?

OptionsFlow manages `entry.options` (runtime behaviour: notifications,
thresholds). The model is `entry.data` (setup configuration) — the two
are intentionally separate per Home Assistant guidelines. A model change
invalidates cached profiling and datasheet lookups, so it requires a
full reload — which reconfigure handles natively.


## Sources & attribution

Attribute name mapping and model definitions are derived from upstream [ESPAltherma beta/definitions](https://github.com/raomin/ESPAltherma/tree/beta/definitions) by [@raomin](https://github.com/raomin) (MIT-licensed). Our datasheet COP curves are compiled from official Daikin service manuals and available for reuse with attribution (see `data/datasheets.json` `_meta`).
