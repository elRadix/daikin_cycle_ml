# Daikin Cycle ML — Dashboard Cards

A curated collection of Lovelace cards for the
[Daikin Cycle ML](https://github.com/elRadix/daikin_cycle_ml) integration.

Each card is self-contained, uses the standard 25 entities exposed by the
integration, and works on Home Assistant 2026.9+.

---

## Cards

| Card | Description | Preview |
|---|---|---|
| [**Simple Card**](cards/simple-card/README.md) | One-glance overview: live phase, hydraulic diagram, COP, quality, alerts, stooklijn advice. Daikin-blue theme. | ![preview](cards/simple-card/preview.png) |

---

## Dependencies

All cards in this folder rely on **HACS frontend cards** (install via
HACS -> Frontend -> Explore & Download Repositories):

- [`stack-in-card`](https://github.com/custom-cards/stack-in-card) — outer container that stacks cards vertically
- [`mushroom-template-card`](https://github.com/piitaya/lovelace-mushroom) — header with icon + title + subtitle
- [`button-card`](https://github.com/custom-cards/button-card) — dynamic HTML render
- [`card-mod`](https://github.com/thomasloven/lovelace-card-mod) — inline CSS injection

The first three are needed for layout. `card-mod` is used for the outer
frame border and gradient.

---

## Language

Every card exposes a `LANG` variable at the top of its JavaScript block:

```js
var LANG = 'nl';   /* 'nl' | 'en' */
```

Change to `'en'` for English. See the individual card READMEs for the
exact line and behaviour.

---

## Installation (general)

1. Make sure the **Daikin Cycle ML** integration is installed and running.
2. Install the four HACS frontend cards listed above.
3. Restart Home Assistant.
4. Hard-refresh the browser (Ctrl+Shift+R).
5. Open the folder of the card you want and follow its `README.md`.
6. Add the YAML via **Edit Dashboard -> + Add Card -> Manual**.

---

## Folder structure

```
dashboard/
├── README.md                     <- you are here
└── cards/
    └── simple-card/
        ├── README.md             <- card documentation
        ├── simple-card.yaml      <- the Lovelace YAML
        └── preview.png           <- screenshot
```

---

## Contributing

Adding a new card:

1. Create `dashboard/cards/<your-card>/` with:
   - `README.md` — installation + dependencies + language toggle
   - `<your-card>.yaml` — the Lovelace YAML
   - `preview.png` — 800x600 screenshot or GIF
2. Add a row to the **Cards** table above.

---

## License

Same as the parent project — MIT.
