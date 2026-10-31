"""Test compliance with HA 2026+ standards."""
import ast
import pathlib

def test_config_entry_functions_return_none():
    p = pathlib.Path(__file__).parent.parent / "custom_components" / "daikin_cycle_ml" / "__init__.py"
    tree = ast.parse(p.read_text())
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name in ("async_setup_entry", "async_unload_entry", "async_migrate_entry"):
            assert ast.unparse(node.returns) == "None", f"{node.name} must return None"
            for body_node in node.body:
                if isinstance(body_node, ast.Return) and isinstance(body_node.value, ast.Constant):
                    assert body_node.value.value not in (True, False), f"{node.name} must not return bool"

def test_show_form_has_step_id():
    p = pathlib.Path(__file__).parent.parent / "custom_components" / "daikin_cycle_ml" / "config_flow.py"
    tree = ast.parse(p.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "async_show_form":
            has_step_id = any(kw.arg == "step_id" for kw in node.keywords)
            assert has_step_id, f"async_show_form missing step_id at line {node.lineno}"

def test_no_deprecated_reload_and_abort():
    p = pathlib.Path(__file__).parent.parent / "custom_components" / "daikin_cycle_ml" / "config_flow.py"
    text = p.read_text()
    assert "async_update_reload_and_abort" not in text, "Found deprecated async_update_reload_and_abort"
