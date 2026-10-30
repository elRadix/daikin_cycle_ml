"""R551 (v112.7): schema.sql <-> async_ensure CREATE TABLE parity guard.

Compares the column set of the two sources of DDL for cop_samples.
Any divergence between schema.sql (authoritative) and the runtime
CREATE TABLE in db.py async_ensure_cop_samples_table (fallback path)
is caught here -- no test-time DB instantiation needed.
"""
import ast
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCHEMA_PATH = _REPO_ROOT / "custom_components" / "daikin_cycle_ml" / "storage" / "schema.sql"
_DB_PATH = _REPO_ROOT / "custom_components" / "daikin_cycle_ml" / "storage" / "db.py"


def _extract_columns_from_create_sql(sql: str) -> set[str]:
    open_match = re.search(r"\(", sql)
    if not open_match:
        return set()
    start = open_match.end()
    depth = 1
    end = len(sql)
    for i in range(start, len(sql)):
        ch = sql[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                end = i
                break
    body = sql[start:end]
    cols: set[str] = set()
    for line in body.split(","):
        line = line.strip()
        if not line:
            continue
        upper = line.upper()
        if upper.startswith(("PRIMARY KEY", "UNIQUE", "FOREIGN KEY", "CONSTRAINT", "CHECK")):
            continue
        cm = re.match(r'"?(\w+)"?\s+', line)
        if cm:
            cols.add(cm.group(1).lower())
    return cols


def _extract_create_sql_from_schema() -> str | None:
    sql = _SCHEMA_PATH.read_text()
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS cop_samples\s*\(([\s\S]*?)\n\);",
        sql,
    )
    if not m:
        return None
    return "CREATE TABLE IF NOT EXISTS cop_samples (" + m.group(1) + ")"


def _extract_create_sql_from_async_ensure() -> str | None:
    """AST: Python concatenates adjacent string literals into one Constant."""
    src = _DB_PATH.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if (isinstance(node, ast.AsyncFunctionDef)
                and node.name == "async_ensure_cop_samples_table"):
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Attribute)
                        and sub.func.attr == "execute"
                        and sub.args
                        and isinstance(sub.args[0], ast.Constant)
                        and isinstance(sub.args[0].value, str)
                        and "CREATE TABLE IF NOT EXISTS cop_samples" in sub.args[0].value):
                    return sub.args[0].value
    return None


def test_schema_sql_and_async_ensure_create_match():
    schema_sql = _extract_create_sql_from_schema()
    assert schema_sql is not None, "cop_samples CREATE not found in schema.sql"
    ensure_sql = _extract_create_sql_from_async_ensure()
    assert ensure_sql is not None, "async_ensure CREATE not found in db.py"
    schema_cols = _extract_columns_from_create_sql(schema_sql)
    ensure_cols = _extract_columns_from_create_sql(ensure_sql)
    assert schema_cols, "schema.sql: parsed zero columns"
    assert ensure_cols, "async_ensure: parsed zero columns"
    assert schema_cols == ensure_cols, (
        f"schema.sql vs async_ensure drift.\n"
        f"  schema-only: {sorted(schema_cols - ensure_cols)}\n"
        f"  ensure-only: {sorted(ensure_cols - schema_cols)}\n"
        f"  both:        {sorted(schema_cols & ensure_cols)}"
    )


def test_schema_sql_cop_samples_has_boiler_active():
    sql = _extract_create_sql_from_schema()
    assert sql is not None
    cols = _extract_columns_from_create_sql(sql)
    assert "boiler_active" in cols, f"boiler_active missing: {sorted(cols)}"


def test_async_ensure_create_has_all_schema_columns():
    ensure_sql = _extract_create_sql_from_async_ensure()
    assert ensure_sql is not None
    cols = _extract_columns_from_create_sql(ensure_sql)
    required = {
        "id", "ts", "cop", "lwt", "outdoor", "r1t", "r4t", "flow_lmin",
        "power_stable", "mode", "source", "mode_original",
        "is_transition_artifact", "boiler_active",
    }
    missing = required - cols
    assert not missing, f"async_ensure CREATE missing columns: {sorted(missing)}"
