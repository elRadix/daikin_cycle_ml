"""The bug report form asks what we need and cannot go stale.

Issue #487 arrived with "1.22.1 (latest)" (the first option of a version
dropdown that had not changed since 1.22.1) and no description at all (the
form had lost its text fields). The version list is now rebuilt from
manifest.json + CHANGELOG.md by tools/sync_issue_template.py; this test
fails as soon as a release bumps the version without running it.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FORM = ROOT / ".github/ISSUE_TEMPLATE/bug_report.yml"
TOOL = ROOT / "tools/sync_issue_template.py"


def _fields() -> dict[str, dict]:
    data = yaml.safe_load(FORM.read_text(encoding="utf-8"))
    return {f["id"]: f for f in data["body"] if "id" in f}


def test_latest_version_in_the_form_is_the_integration_version():
    version = json.loads((ROOT / "custom_components/daikin_cycle_ml/manifest.json").read_text())["version"]
    opts = _fields()["integration_version"]["attributes"]["options"]
    assert opts[0] == f"{version} (latest)"
    assert sum("(latest)" in o for o in opts) == 1 and opts[-1].startswith("Older")
    assert len(opts) == len(set(opts)) >= 3


def test_sync_tool_reports_no_drift():
    proc = subprocess.run([sys.executable, str(TOOL), "--check"], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stdout


def test_sync_tool_check_fails_on_a_stale_list(tmp_path, monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location("sync_issue_template", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    stale = tmp_path / "bug_report.yml"
    stale.write_text(FORM.read_text(encoding="utf-8").replace(
        mod.options_block(), mod.BEGIN + '        - "1.22.1 (latest)"\n' + mod.END), encoding="utf-8")
    monkeypatch.setattr(mod, "FORM", stale)
    assert mod.main(["--check"]) == 1
    assert mod.main([]) == 0 and mod.main(["--check"]) == 0      # the tool repairs it


def test_form_asks_what_happens_and_what_was_expected():
    fields = _fields()
    for key in ("what_happens", "expected"):
        assert fields[key]["type"] == "textarea" and fields[key]["validations"]["required"] is True
    assert {"area", "when", "ha_version", "model", "espaltherma_version", "source_type", "logs", "extra"} <= set(fields)
    assert fields["area"]["validations"]["required"] is True and fields["logs"]["attributes"]["render"] == "shell"
    assert "# PART" not in FORM.read_text(encoding="utf-8")


def test_feature_request_form():
    data = yaml.safe_load((FORM.parent / "feature_request.yml").read_text(encoding="utf-8"))
    ids = {f["id"]: f for f in data["body"] if "id" in f}
    assert data["labels"] == ["enhancement"] and ids["problem"]["validations"]["required"] is True
    assert {"idea", "model", "extra"} <= set(ids)
