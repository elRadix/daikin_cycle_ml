"""Test manifest categories compliance with HA standards."""
import json
import pathlib


def test_manifest_has_valid_categories():
    manifest_path = pathlib.Path(__file__).parent.parent / "custom_components" / "daikin_cycle_ml" / "manifest.json"
    data = json.loads(manifest_path.read_text())

    assert "categories" in data, "manifest.json must contain 'categories'"
    assert isinstance(data["categories"], list), "'categories' must be a list"

    # Real HA category enum, derived from homeassistant/components/
    # homeassistant/strings.json (verified: NO "sensor")
    valid_categories = {
        "adc", "analytics", "automation", "car", "climate", "cover",
        "device_tracker", "doorbell", "energy", "event", "fan", "health",
        "humidifier", "light", "lock", "media_source", "multimedia",
        "network", "notifier", "number", "remote", "siren",
        "switch", "system", "weather", "update"
    }

    for cat in data["categories"]:
        assert cat in valid_categories, f"Invalid category: {cat}"

    # Specifiek voor Daikin Cycle ML
    assert "climate" in data["categories"]
    assert "energy" in data["categories"]
