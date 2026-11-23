# YAML cards: install and shared settings

How to install the seven YAML cards, and the header, variables, language
and theme they share. The three **native cards** need none of this: see
the [dashboard overview](../README.md).

| Card | File | Shows |
|---|---|---|
| [Simple card](simple-card/README.md) | `simple-card/simple-card.yaml` | Live phase, COP, quality, alerts, hydraulic diagram, today, last cycle, heating-curve advice |
| [COP & energy](cop-energy/README.md) | `cop-energy/cop-energy.yaml` | SPF gauge, COP per period and mode, live power flow, energy today |
| [Summary](daily-summary/README.md) | `daily-summary/daily-summary.yaml` | One-page multi-day summary: quality, cycles, duration, events |
| [Daily summary (tabbed)](daily-summary-tabbed/README.md) | `daily-summary-tabbed/daily-summary-tabbed.yaml` | The same per-day data in five tabs with 7 / 15 / 30 day windows and pop-ups |
| [Heating curve](heating-curve/README.md) | `heating-curve/heating-curve.yaml` | Water temperature against outdoor with the measured points, live point, modes, balance |
| [LWT fine-tuning](lwt-fine-tuning/README.md) | `lwt-fine-tuning/card.yaml` | Heating-curve advice, buckets, slope / offset analysis, live LWT |
| [Pattern analysis](pattern-analysis/README.md) | `pattern-analysis/pattern-analysis.yaml` | Run-length distribution, cycles against run length, COP |

## Install

1. Install the three frontend cards below (HACS → Frontend), restart Home
   Assistant and refresh the browser (`Ctrl`+`Shift`+`R`).
2. Open the card's folder and copy the whole YAML file.
3. **Edit dashboard → + Add card → Manual**, paste, **Save**.
4. After an integration update, re-paste the YAML when the release notes
   list the card (HACS does not update pasted cards).

## Requirements

HACS → Frontend:

| Card | Repository | Used for |
|---|---|---|
| stack-in-card | [custom-cards/stack-in-card](https://github.com/custom-cards/stack-in-card) | Outer container |
| button-card | [custom-cards/button-card](https://github.com/custom-cards/button-card) | Header and body (HTML / SVG) |
| card-mod | [thomasloven/lovelace-card-mod](https://github.com/thomasloven/lovelace-card-mod) | Outer border and shadow |

mushroom-template-card is no longer needed: the header is a button-card
in every card. Restart Home Assistant after installing a frontend card and
hard-refresh the browser (`Ctrl`+`Shift`+`R`).

## Header

Every card starts with the same header: an icon, the card title with the
**heat pump model** (from `sensor.daikin_cycle_ml_hp_specs`) and a
subtitle with the family, power and refrigerant, for example
`LWT FINE-TUNING · EPRA12EAV3` / `… · Altherma 3 H MT · 12 kW · R32`.

## Variables

Every card has the same `variables:` block in its header (the first
button-card). The other button-cards of the card reuse it with
`variables: *dcm`, so you edit it in one place:

    - type: custom:button-card
      variables: &dcm
        lang_override: ''         # '' = auto | en | nl | fr
        theme_override: auto      # auto | light | dark
        show_help: true           # false = hide the explanation notes

| Variable | Default | Values | Effect |
|---|---|---|---|
| `lang_override` | `''` | `''`, `en`, `nl`, `fr` | Force the card language; empty = automatic (see below) |
| `theme_override` | `auto` | `auto`, `light`, `dark` | `auto` follows the Home Assistant dark mode |
| `show_help` | `true` | `true`, `false` | Show the hint / explanation notes |

Some cards add their own variables (`default_tab`, `default_window`,
`chart_height`); they are listed in the card's README. Variables on the
outer `stack-in-card` have no effect (button-card reads only its own),
which is why they live in the header.

## Language

English, Dutch and French. Without `lang_override` a card uses:

1. the Home Assistant UI language, when it is English, Dutch or French;
2. otherwise the language of the integration (`configured_language`);
3. otherwise English.

Entity ids in any language work (the cards find the entities by their
translation key). Numbers use the decimal separator of your Home
Assistant number format (`5.27` in English, `5,27` in Dutch and French).

## Theme and dark mode

One palette for all cards, based on Daikin blue `#0097E0`. With the Home
Assistant dark mode on (or `theme_override: dark`) every card switches to
dark backgrounds with light text; the status colours (green good, orange
attention, red problem) stay, slightly brighter for contrast.

| Role | Light | Dark |
|---|---|---|
| Accent | `#0097E0` | `#4FC3F7` |
| Background | `#FFFFFF` / `#F5FAFD` | `#1B1F24` / `#232A33` |
| Text | `#0D47A1` | `#E6F0FA` |
| Secondary text | `#1565C0` | `#90CAF9` |
| Good / attention / problem | `#2E7D32` / `#E65100` / `#C62828` | `#4CAF50` / `#FB8C00` / `#E53935` |

## For developers

The language, theme and header code is the same block in every card,
between `/* DCM-COMMON-BEGIN` and `/* DCM-COMMON-END */`. Edit
`tools/card_common.js` and run `python3 tools/sync_card_common.py`; the
tests fail when a card drifts (`--check`). `tests/test_427_cards_live_states.py`
renders every card in English, Dutch, French and dark mode from the states
the integration writes.
