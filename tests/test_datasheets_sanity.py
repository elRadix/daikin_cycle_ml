"""Sanity check: datasheet nominal kw matches model name digits."""
import json
import pathlib
import re


def test_epra_kw_matches_model_name():
    p = pathlib.Path(__file__).parent.parent / 'custom_components/daikin_cycle_ml/data/datasheets.json'
    data = json.loads(p.read_text())
    for model, spec in data['models'].items():
        m = re.match(r'epra(\d\d)', model)
        if m:
            expected_kw = float(m.group(1))
            # 04 -> 4.0
            assert abs(spec['kw'] - expected_kw) < 0.1, f"{model} has kw={spec['kw']}, expected {expected_kw}"
