# Security Policy

## Supported Versions

Only the latest stable release of Daikin Cycle ML receives security
updates. Pre-release builds (vX.Y.Z-pre.N) are for testing only and
are not covered by this policy.

| Version | Supported          |
| ------- | ------------------ |
| 1.7.x   | :white_check_mark: |
| 1.6.x   | :x:                |
| < 1.6   | :x:                |

## Reporting a Vulnerability

**Please do NOT open a public GitHub issue for security
vulnerabilities.** Public disclosure before a fix is available puts
all users at risk.

Report privately via one of:

1. **GitHub Security Advisories** (preferred):
   https://github.com/elRadix/daikin_cycle_ml/security/advisories/new

2. **Email**: open a minimal public issue asking for a private
   contact channel, or use the GitHub Advisory form above.

Please include in your report:

- Affected version(s) of Daikin Cycle ML
- A clear description of the vulnerability
- Reproduction steps or a minimal proof-of-concept
- Your impact assessment: confidentiality / integrity / availability
- Any suggested mitigation, if you have one

If you are unsure whether something is a vulnerability, err on the
side of reporting it privately first. False positives cost us very
little; a leaked 0-day costs users a lot.

## Response Timeline

This is a solo-maintained project. Realistic targets:

| Stage                          | Target      |
| ------------------------------ | ----------- |
| Initial acknowledgement        | 72 hours    |
| Triage and severity rating     | 7 days      |
| Fix or mitigation              | 30 days     |
| Public disclosure              | after fix   |

If a fix will take longer than 30 days, you will be informed and we
will agree on a coordinated disclosure date.

## Scope

### In scope

- All Python source under `custom_components/daikin_cycle_ml/`
- GitHub Actions workflows under `.github/workflows/`
- Direct dependencies declared in `pyproject.toml` /
  `requirements_test.txt`
- The REST endpoint exposed at
  `/api/daikin_cycle_ml/cop_hourly`
- The SQLite persistence layer at
  `.storage/daikin_cycle_ml.db`

### Out of scope

- **Home Assistant Core** itself -- report upstream at
  https://github.com/home-assistant/core/security
- **Transitive dependencies of Home Assistant** (for example
  `cryptography`, `pyjwt`) -- report upstream. Daikin Cycle ML does
  not control these versions.
- **Third-party HACS frontend cards** used alongside this
  integration (button-card, mushroom, stack-in-card, card_mod)
- **User misconfiguration** (wrong sensor entity, disabled
  authentication on the HA instance, etc.)
- **Physical or local-network attacks** against the Home Assistant
  host -- outside the integration's threat model
- **Denial of service via the user's own HA automation** calling
  services in a tight loop

## Security Model

Daikin Cycle ML is a **local-only** Home Assistant custom
integration. The threat model assumes:

- The Home Assistant host is trusted (same trust level as any HA
  custom component).
- The source sensor entity (`sensor.althermasensors` or equivalent)
  is trusted to produce well-formed attributes. Malformed attributes
  are handled defensively but are not treated as adversarial input.
- The Home Assistant HTTP endpoint is protected by HA's own
  authentication layer.

Concrete characteristics:

- **No outbound network calls.** No HTTP client, no telemetry, no
  cloud dependency. The integration is classified as
  `iot_class: calculated`.
- **One authenticated REST endpoint.**
  `GET /api/daikin_cycle_ml/cop_hourly` is registered with
  `requires_auth = True` and is served only to authenticated HA
  users.
- **No dynamic code execution.** No `eval`, `exec`, `subprocess`,
  `pickle`, or unsafe `yaml.load` anywhere in the codebase.
- **SQL is parameterised.** Every query that touches user-supplied
  data uses positional parameters. The only identifier
  interpolation (`ALTER TABLE ... ADD COLUMN {name}` and
  `SELECT COUNT(*) FROM {table}`) is guarded by hardcoded tuples
  or explicit whitelists.
- **Local persistence only.** All state is written to
  `.storage/daikin_cycle_ml.db` (SQLite) and Home Assistant's
  internal Store. No data leaves the host.

An independent security audit of v1.7.1 (2026-10-07) examined 15
attack-surface paths and found zero critical, high, or medium
findings. Low-severity process gaps were remediated via PRs #46
(pre-commit hooks) and #47 (workflow permissions).

## Known Limitations

We document these openly rather than claim perfect coverage:

- **No encryption at rest.** The SQLite database and Home Assistant
  Store rely on OS-level file permissions for confidentiality.
- **No rate-limiting on the REST endpoint.** HA's global
  rate-limiting and authentication layer apply, but the endpoint
  itself does not add per-user quotas.
- **No SBOM published.** Supply-chain transparency is tracked as a
  backlog item (LOW-03 from the v1.7.1 audit).
- **No formal STRIDE threat model.** The security posture above is
  the current best-effort description; a structured threat model is
  a backlog item.

## Credits

We thank the following researchers for responsible disclosure:

- *(none yet -- be the first)*

---

_Last updated: 2026-10-07 (v1.7.1)_
