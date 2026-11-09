"""Regression test for v1.23.0 HT attribute aliases (#189)."""
from custom_components.daikin_cycle_ml.engine.attribute_compat import build_compat_view

def test_ht_hydrobox_aliases() -> None:
    """Verify [Hydrobox] prefixes map correctly to canonical keys."""
    attrs = {
        "[Hydrobox] Leaving water temp. (R1T)": 35.0,
        "[Hydrobox] Inlet water temp. (R4T)": 30.0,
        "[Hydrobox] Compressor frequency": 45.0,
    }
    view = build_compat_view(attrs)
    assert view["Leaving water temp. before BUH (R1T)"] == 35.0
    assert view["Inlet water temp.(R4T)"] == 30.0
    assert view["INV frequency (rps)"] == 45.0

def test_ht_alternate_frequency_aliases() -> None:
    """Verify generic compressor frequency / Hz aliases map correctly."""
    attrs = {
        "Frequency (Hz)": 65.0,
    }
    view = build_compat_view(attrs)
    # Both should map to the canonical INV frequency key
    assert view["INV frequency (rps)"] == 65.0
