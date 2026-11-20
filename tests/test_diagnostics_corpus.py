"""Anonymised diagnostics corpus (tests/fixtures/diagnostics).

Real installs, ingested with tools/ingest_diagnostics.py. Every file:

- passes the privacy scan (no IPs, MACs, mail addresses, entry ids,
  user entity ids, friendly names or paths);
- is listed in INDEX.json;
- replays through the integration's own code: attribute compat view,
  model-code resolution, quality score, behaviour values, stored ML
  state (baseline / k-means).

Add a file: python tools/ingest_diagnostics.py <file> --origin user
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.engine.attribute_compat import build_compat_view
from custom_components.daikin_cycle_ml.engine.model_catalog import resolve_model_text
from custom_components.daikin_cycle_ml.engine.quality_scorer import score_cycle
from custom_components.daikin_cycle_ml.ml import kmeans_v2
from custom_components.daikin_cycle_ml.ml.behaviour_baseline import (
    BehaviourBaseline,
    behaviour_values,
)

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "tests" / "fixtures" / "diagnostics"
FILES = sorted(p for p in CORPUS.glob("*.json") if p.name != "INDEX.json")
INDEX = json.loads((CORPUS / "INDEX.json").read_text())

_FOREIGN_ENTITY = re.compile(
    r"\b(?:sensor|binary_sensor|switch|notify|input_number|climate|number|select)"
    r"\.(?!daikin_cycle_ml|user_\d+\b)[a-z0-9_]+"
)
_PII = {
    "ipv4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "mac": re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b"),
    "mail": re.compile(r"[\w.+-]+@(?!example\b)[\w-]+\.[\w.-]+"),
    "ulid": re.compile(r"\b[0-9A-HJKMNP-TV-Z]{26}\b"),
    "config_path": re.compile(r"/config/"),
    "friendly_name_key": re.compile(r'"friendly_name"\s*:'),
    "path_key": re.compile(r'"path"\s*:'),
}


def _load(p: Path) -> dict:
    return json.loads(p.read_text())


def test_corpus_present_and_indexed():
    assert FILES, "corpus is empty"
    assert sorted(r["file"] for r in INDEX) == [p.name for p in FILES]
    for row in INDEX:
        assert row["origin"] in ("user", "maintainer")
        assert len(row["anon_id"]) == 10


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_privacy(path):
    text = path.read_text()
    for name, rx in _PII.items():
        assert not rx.search(text), f"{name} in {path.name}"
    assert not _FOREIGN_ENTITY.search(text), _FOREIGN_ENTITY.search(text).group(0)


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_replay(path):
    doc = _load(path)
    assert doc["corpus_format"] == 1
    attrs = doc["source"]["attributes"]
    view = build_compat_view(attrs)
    assert len(view) >= len(attrs)

    model = doc["entry"]["data"].get("model")
    unit = attrs.get("Unit model")
    if unit:
        match = resolve_model_text(unit)
        if match.kind in ("exact", "alias", "indoor", "ambiguous"):
            assert model in match.candidates or model == match.key, (unit, match)

    last = (doc.get("store") or {}).get("last_cycle")
    if last:
        q = score_cycle(last, doc["entry"]["options"])
        assert 0 <= int(q) <= 100
        vals = behaviour_values(last, cop_avg=last.get("cop_avg"))
        assert vals["duration_s"] == last["duration_s"] or vals["duration_s"] is None

    states = (doc.get("database") or {}).get("model_state") or {}
    base = states.get("baseline_state")
    if isinstance(base, dict):
        bb = BehaviourBaseline.from_dict(base)
        if base.get("type") == "behaviour":
            assert bb._migrated_from_dim is None and bb.modes()
            assert BehaviourBaseline.from_dict(bb.to_dict()).to_dict() == bb.to_dict()
        else:   # v1 state: the relearn replaces it
            assert bb._migrated_from_dim is not None
    km = states.get("kmeans_state")
    if isinstance(km, dict) and km.get("version") == kmeans_v2.KMEANS_VERSION:
        assert len(kmeans_v2.labels(km)) == len(kmeans_v2.centroids(km))


def test_ingest_tool_strips_personal_data(tmp_path):
    sys.path.insert(0, str(ROOT / "tools"))
    import ingest_diagnostics as ing

    entry = "01ABCDEFGHJKMNPQRSTVWXYZ12"
    raw = {
        "home_assistant": {"version": "2026.11.1", "timezone": "Europe/Brussels"},
        "data": {
            "meta": {"integration_version": "9.9.9", "generated_at": "2026-11-20T06:00:00+01:00",
                     "timezone": "Europe/Brussels"},
            "entry": {"entry_id": entry, "title": "x (sensor.my_altherma)",
                      "data": {"model": "erga06eav3", "source_sensor": "sensor.my_altherma"},
                      "options": {"notify_service": "notify.mobile_jan",
                                  "power_sensor_entity": "sensor.heatpump_power"}},
            "source": {"state": "Online", "attributes_full": {
                "IP": "192.168.1.9", "WifiRSSI": "-40dBm", "M5VIN": "5V",
                "friendly_name": "Jan's pump", "Unit model": "EHBX08EF6V", "R1T-Outdoor air temp.": 3.0}},
            "database": {"path": f"/config/.storage/daikin_cycle_ml_{entry}.db",
                         "per_entry": {entry: {"path": "/config/x", "counts": {"cycles": 1}}}},
            "entities": {"entries": [{"entity_id": "sensor.daikin_cycle_ml_cycle_state",
                                      "state": "idle", "attributes": {
                                          "friendly_name": "x", "icon": "mdi:x",
                                          "configured_power_sensor": "sensor.heatpump_power",
                                          "mail": "jan@home.example.org"}}]},
        },
    }
    # paste damage: a stray closing bracket line after home_assistant
    text = json.dumps(raw, indent=2).replace('"timezone": "Europe/Brussels"\n  },',
                                             '"timezone": "Europe/Brussels"\n  }\n  },', 1)
    out = ing.ingest(text, origin="user", out_dir=tmp_path)
    doc = json.loads(out.read_text())
    blob = out.read_text()
    assert entry not in blob and "192.168" not in blob and "Jan" not in blob
    assert "jan@" not in blob and "/config" not in blob and "Brussels" not in blob
    assert "sensor.my_altherma" not in blob and "notify.mobile_jan" not in blob
    assert doc["entry"]["data"]["source_sensor"] == "sensor.user_1"   # title is not kept
    assert doc["entry"]["options"]["power_sensor_entity"] == "sensor.user_2"
    ent = doc["entities"]["sensor:cycle_state"]["attributes"]
    assert ent["configured_power_sensor"] == "sensor.user_2"            # consistent
    assert "IP" not in doc["source"]["attributes"] and "M5VIN" not in doc["source"]["attributes"]
    assert doc["source"]["attributes"]["Unit model"] == "EHBX08EF6V"
    index = json.loads((tmp_path / "INDEX.json").read_text())
    assert index[0]["unit_model"] == "EHBX08EF6V" and index[0]["origin"] == "user"
    again = ing.ingest(text, origin="user", out_dir=tmp_path)            # replaces its row
    assert again == out and len(json.loads((tmp_path / "INDEX.json").read_text())) == 1
    with pytest.raises(ValueError):
        ing.load_lenient("no json here")
