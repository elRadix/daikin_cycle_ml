"""C9: verify all registered services are translated in strings/en/nl."""
from __future__ import annotations

import json
import pathlib

CC = pathlib.Path("custom_components/daikin_cycle_ml")

EXPECTED_SERVICES = {
    "reset_counters",
    "export_cycles",
    "label_cycle",
    "recompute_baseline",
    "run_maintenance",
    "send_test_notification",
    "export_cop_hourly",
    "import_datasheet",
    "remove_user_datasheet",
}


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text())


def test_strings_json_has_all_services():
    data = _load(CC / "strings.json")
    assert set((data.get("services") or {}).keys()) == EXPECTED_SERVICES


def test_en_json_has_all_services():
    data = _load(CC / "translations" / "en.json")
    assert set((data.get("services") or {}).keys()) == EXPECTED_SERVICES


def test_nl_json_has_all_services():
    data = _load(CC / "translations" / "nl.json")
    assert set((data.get("services") or {}).keys()) == EXPECTED_SERVICES


def test_each_service_has_name_and_description():
    for path in [
        CC / "strings.json",
        CC / "translations/en.json",
        CC / "translations/nl.json",
    ]:
        data = _load(path)
        for key in EXPECTED_SERVICES:
            svc = data["services"][key]
            assert svc.get("name"), f"{path}: {key} missing name"
            assert svc.get("description"), f"{path}: {key} missing description"
            assert isinstance(svc.get("fields"), dict), (
                f"{path}: {key} fields not a dict"
            )


def test_en_and_strings_services_identical():
    a = _load(CC / "strings.json")["services"]
    b = _load(CC / "translations" / "en.json")["services"]
    assert a == b


def test_nl_service_field_keys_match_en():
    en = _load(CC / "translations" / "en.json")["services"]
    nl = _load(CC / "translations" / "nl.json")["services"]
    for key in EXPECTED_SERVICES:
        assert set(en[key]["fields"].keys()) == set(nl[key]["fields"].keys()), (
            f"{key}: field keys mismatch"
        )
