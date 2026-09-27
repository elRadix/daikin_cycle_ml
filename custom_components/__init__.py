"""Package marker for custom_components.

Batch 52b8i: without this file, pytest-homeassistant-custom-component
creates its own custom_components/ dir in site-packages during plugin
install, which shadows this repo's tree in clean CI environments.
Result: ModuleNotFoundError on `custom_components.daikin_cycle_ml`.
This file forces Python to treat our repo-root tree as a package.
"""
