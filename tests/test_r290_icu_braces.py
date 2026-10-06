"""R290 - HA translations use ICU MessageFormat (IntlMessageFormat).

Hassfest 2026.10 rule: all braces in translations must be valid
ICU placeholders matching [a-zA-Z_][a-zA-Z0-9_]*.

- No literal braces.
- No escaped braces ('{ ' / ' }' variants) - Hassfest rejects them.
- No double braces ({{ / }}) - frontend rejects them (MALFORMED_ARGUMENT).
"""
import json
import pathlib
import re

FILES = [
    "custom_components/daikin_cycle_ml/strings.json",
    "custom_components/daikin_cycle_ml/translations/en.json",
    "custom_components/daikin_cycle_ml/translations/nl.json",
]

_LB = chr(123)
_RB = chr(125)
_PLACEHOLDER = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")


def _has_raw_brace(val):
    v = _PLACEHOLDER.sub("", val)
    return _LB in v or _RB in v


def _iter_strings(step):
    for k in ("title", "description"):
        if isinstance(step.get(k), str):
            yield k, step[k]
    for section in ("data", "data_description"):
        for k, v in (step.get(section) or {}).items():
            if isinstance(v, str):
                yield f"{section}.{k}", v


def test_no_invalid_braces_in_config_steps():
    root = pathlib.Path(__file__).resolve().parents[1]
    for rel in FILES:
        data = json.loads((root / rel).read_text(encoding="utf-8"))
        for step_name, step in (data.get("config", {}).get("step") or {}).items():
            for field, val in _iter_strings(step):
                if _has_raw_brace(val):
                    raise AssertionError(
                        f"{rel}: config.step.{step_name}.{field} has invalid ICU braces: {val!r}"
                    )


def test_no_double_braces_anywhere_in_translations():
    root = pathlib.Path(__file__).resolve().parents[1]
    for rel in FILES:
        raw = (root / rel).read_text(encoding="utf-8")
        bad_open = _LB + _LB
        bad_close = _RB + _RB
        if bad_open in raw or bad_close in raw:
            raise AssertionError(f"{rel}: literal double braces present in translations")
