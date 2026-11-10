"""#311: conditional update_listener for OptionsFlowWithReload.

HA 2026.11.1+ raises ValueError in async_finish_flow when a flow
inheriting from OptionsFlowWithReload is combined with an entry-level
update_listener. The listener must be skipped on that code path
(OptionsFlowWithReload auto-reloads). The listener is still required
for the older OptionsFlow fallback to preserve #286.
"""

from __future__ import annotations

import ast
from pathlib import Path


def test_needs_manual_reload_false_on_modern_ha():
    """#311: runtime check — modern HA has OptionsFlowWithReload."""
    from custom_components.daikin_cycle_ml import config_flow as cf
    assert cf._OPTIONS_FLOW_BASE.__name__ == "OptionsFlowWithReload", (
        "Container HA must be >= the version where OptionsFlowWithReload "
        "was introduced"
    )
    assert cf.NEEDS_MANUAL_RELOAD is False


def test_needs_manual_reload_is_module_constant():
    """#311: NEEDS_MANUAL_RELOAD is a stable module-level flag."""
    from custom_components.daikin_cycle_ml import config_flow as cf
    assert hasattr(cf, "NEEDS_MANUAL_RELOAD")
    assert isinstance(cf.NEEDS_MANUAL_RELOAD, bool)


def test_setup_entry_listener_is_conditional():
    """#311: structural — add_update_listener inside `if NEEDS_MANUAL_RELOAD`."""
    src = Path(
        "custom_components/daikin_cycle_ml/__init__.py"
    ).read_text()
    tree = ast.parse(src)
    lines = src.splitlines()
    found_guard = False
    found_listener_inside = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AsyncFunctionDef)
            and node.name == "async_setup_entry"
        ):
            for child in ast.walk(node):
                if not isinstance(child, ast.If):
                    continue
                if_test = ast.unparse(child.test)
                if "NEEDS_MANUAL_RELOAD" not in if_test:
                    continue
                found_guard = True
                body_txt = "\n".join(
                    lines[child.lineno - 1:child.end_lineno]
                )
                if (
                    "add_update_listener" in body_txt
                    and "_async_options_updated" in body_txt
                ):
                    found_listener_inside = True
            break
    assert found_guard, (
        "async_setup_entry has no `if NEEDS_MANUAL_RELOAD` guard"
    )
    assert found_listener_inside, (
        "add_update_listener is not inside the NEEDS_MANUAL_RELOAD guard"
    )


def test_async_options_updated_still_exported():
    """#286 stays functional for the fallback path."""
    from custom_components.daikin_cycle_ml import _async_options_updated
    assert callable(_async_options_updated)

def test_helper_skips_when_needs_manual_reload_false(monkeypatch):
    """#311: helper no-ops when OptionsFlowWithReload is active."""
    from custom_components.daikin_cycle_ml import __init__ as init_mod
    monkeypatch.setattr(init_mod, "NEEDS_MANUAL_RELOAD", False)

    class _Entry:
        def __init__(self):
            self.listener_added = False
            self.unload_added = False
        def add_update_listener(self, cb):
            self.listener_added = True
            return cb
        def async_on_unload(self, cb):
            self.unload_added = True

    entry = _Entry()
    init_mod._maybe_register_options_listener(entry)
    assert entry.listener_added is False
    assert entry.unload_added is False


def test_helper_registers_when_needs_manual_reload_true(monkeypatch):
    """#311: helper wires listener when fallback OptionsFlow is active."""
    from custom_components.daikin_cycle_ml import __init__ as init_mod
    monkeypatch.setattr(init_mod, "NEEDS_MANUAL_RELOAD", True)

    class _Entry:
        def __init__(self):
            self.listener_added = False
            self.unload_added = False
        def add_update_listener(self, cb):
            self.listener_added = True
            return ("listener", cb)
        def async_on_unload(self, cb):
            self.unload_added = True
            assert cb == ("listener", init_mod._async_options_updated)

    entry = _Entry()
    init_mod._maybe_register_options_listener(entry)
    assert entry.listener_added is True
    assert entry.unload_added is True
