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
    """#311: async_setup_entry delegates to _maybe_register_options_listener."""
    src = Path(
        "custom_components/daikin_cycle_ml/__init__.py"
    ).read_text()
    tree = ast.parse(src)
    lines = src.splitlines()

    # a) async_setup_entry calls the helper
    setup_calls_helper = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AsyncFunctionDef)
            and node.name == "async_setup_entry"
        ):
            body = "\n".join(lines[node.lineno - 1:node.end_lineno])
            if "_maybe_register_options_listener(entry)" in body:
                setup_calls_helper = True
            break

    # b) helper guards on NEEDS_MANUAL_RELOAD and wires listener
    helper_has_guard = False
    helper_has_listener = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == "_maybe_register_options_listener"
        ):
            body = "\n".join(lines[node.lineno - 1:node.end_lineno])
            if "NEEDS_MANUAL_RELOAD" in body:
                helper_has_guard = True
            if (
                "add_update_listener" in body
                and "_async_options_updated" in body
            ):
                helper_has_listener = True
            break

    assert setup_calls_helper, (
        "async_setup_entry does not call _maybe_register_options_listener"
    )
    assert helper_has_guard, (
        "helper does not guard on NEEDS_MANUAL_RELOAD"
    )
    assert helper_has_listener, (
        "helper does not wire add_update_listener(_async_options_updated)"
    )


def test_async_options_updated_still_exported():
    """#286 stays functional for the fallback path."""
    from custom_components.daikin_cycle_ml import _async_options_updated
    assert callable(_async_options_updated)

def test_helper_skips_when_needs_manual_reload_false(monkeypatch):
    """#311: helper no-ops when OptionsFlowWithReload is active."""
    import importlib
    init_mod = importlib.import_module("custom_components.daikin_cycle_ml")
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
    import importlib
    init_mod = importlib.import_module("custom_components.daikin_cycle_ml")
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
