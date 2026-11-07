# Model Coverage Matrix

Daikin Cycle ML supports **ESPAltherma 2.0 beta** for the 34 real Altherma
models tracked in `docs/MODEL_ATTRIBUTES.json` (SHA 714ad016).

## How coverage is measured

The integration consumes **25 attributes** for full functionality. Four of
these are *intrinsic* — computed by the integration or provided dynamically
by ESPAltherma at runtime — and never appear in `.h` files:

| Intrinsic label | Source |
|---|---|
| `COP` | Computed by the integration from thermal / electrical |
| `Stats: Heat output (kW)` | Computed on the ESPAltherma board (firmware ≥ 2.0.0-beta.19) |
| `Stats: Electrical input estimated (kW)` | Same |
| `Stats: Electricalinput estimated (kW)` | Firmware typo variant, same value |

The remaining **21 operational attributes** are read directly from
ESPAltherma entities. Coverage counts how many of these resolve for a
given model (via direct slug or via `ALIAS_GROUPS` variants).

## In-scope models — 34 real Altherma models

Coverage after v1.20.0 aliases:

| Tier | Models | Coverage |
|---|---|---|
| **Perfect** | 12 models | 21/21 |
| **High** | 19 models | 20/21 (miss `INV frequency 2` — no cascade) |
| **Good** | 1 model (EPSK) | 19/21 (miss `INV frequency 2` + `Indoor ambient`) |
| **Multi-DHW tank** | 2 models | 17/21 (no compressor/inverter) |
| **GEO3** | 1 model | 16/21 (no hybrid features) |

**"Perfect 21/21" models** (all operational attributes present):
- `Altherma(EGSQH-A series 10kW GEO2).h`
- `Altherma(ERGA D EHSH-X P30-50 D series 04-08kW-ECH2O).h`
- `Altherma(ERGA D EHV-EHB-EHVZ DA series 04-08kW).h`
- `Altherma(ERLA03 D EHFH-EHFZ DJ series 3kW).h`
- `Altherma(LT_CA_CB_04-08kW).h`
- `Altherma(LT_CB_04-08kW Bizone).h`
- `Altherma(LT_CB_11-16kW Bizone).h`
- `Altherma(LT_EBLQ-EBLQ-CA series 5-7kW Monobloc).h`
- `Altherma(LT_Multi_DHWHP).h`
- `Altherma(LT_Multi_Hybrid).h`
- `Daikin Mini chiller(EWAA-EWYA D series 9-16kW).h`
- `Daikin Mini chiller(EWAQ-EWYQ B series 4-8kW).h`

## Stats availability

**All 34 in-scope models publish the 4 source attributes** that
ESPAltherma needs to compute Stats:

- `Flow sensor (l/min)`
- `Leaving water temp. after BUH (R2T)` (or R1T variant)
- `Inlet water temp.(R4T)`
- `INV primary current (A)`

**Requirement:** ESPAltherma firmware **v2.0.0-beta.19 or newer**. Older
firmware does not compute Stats and the integration falls back to the
internal `compute_thermal_power_live` + `_compute_electrical_power`
calculation path (less accurate — ~6% COP drift).

HT models (`Altherma(HT ERRQ-ERSQ)` and `Altherma(HT EKHBRD-ERRQ)`) use
a different register protocol and do **not** publish the 4 source values.
They are outside the current support scope.

## Alias groups — canonical to variant mapping

The resolver tries these in order until one matches:

| Canonical | Aliases |
|---|---|
| `Outdoor air temp.(R1T)` | `R1T-Outdoor air temp.`, `Outdoor air temp. (R1T)`, `Outdoor air temp.(C)`, `Outdoor air temp.` |
| `Leaving water temp. after BUH (R2T)` | `Outlet Water BUH Temp. (R2T)`, `[HPSU] Tvbh inflow Temp after Buffer/BUH (R2T)`, `Leaving water temp. before BUH (R1T)` |
| `Inlet water temp.(R4T)` | `Inlet water temp. (water heat exchanger)`, `[HPSU] Tr return Temp (R4T)` |
| `BE COP` | `BE_COP`, `BECOP` |

## What "full native support" means

For an in-scope Altherma model (34 of 40) on ESPAltherma v2.0.0-beta.19+:

- All 12 REQUIRED attributes resolve → no repair issue
- All 21 operational attributes resolve → cycle detection, COP, DHW,
  stooklijn, hybrid, comfort all functional
- 4 intrinsic attributes available → COP cascade uses ESPAltherma's
  on-device computation (accurate within ~0.5%)

For an HT model: different register protocol; not supported.

## Out of scope (documented)

- `DEFAULT.h`, `PROTOCOL_S.h`, `PROTOCOL_S_ROTEX.h` — placeholder files, not real models
- HT models (ERRQ, EKHBRD) — different register protocol, no Stats source values
- Non-DHW models lack `DHW tank temp. (R5T)` — legitimately absent, surfaced in `missing_consumed` but not via repair
- Non-hybrid models lack `Boiler Operation Demand`, `Boiler DHW Demand`, `Hybrid Op. Mode` — legitimately absent
- Single-compressor models lack `INV frequency 2` — no cascade
