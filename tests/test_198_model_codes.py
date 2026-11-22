"""#198: model codes users actually type.

Testing 34 real codes against the resolver showed three groups that came
back "unknown": the size alone ("ERGA06", "Altherma 3 R ERGA06"), a
shortened suffix ("EPGA11DV", "ERLA11DV37") and three-phase codes
("EPRA12EAW1", "EPRA14DAW1", "ERLA16DAW1"). They now resolve on family + size
(+ the series letter when given). The wizard keeps what the user typed in
entry.data["model_code"], so diagnostics show it next to the resolved model.
"""
from __future__ import annotations

import pytest

from custom_components.daikin_cycle_ml.const import DOMAIN, MODEL_CHOICES
from custom_components.daikin_cycle_ml.engine.model_catalog import (
    FLAGGED_NON_CATALOGUE,
    resolve_model_text,
)
from tests.test_435_model_catalog import _source


@pytest.mark.parametrize(
    ("text", "kind", "key", "candidates"),
    [
        ("ERGA06", "alias", "erga06eav3", ["erga06eav3"]),
        ("Altherma 3 R ERGA06", "alias", "erga06eav3", ["erga06eav3"]),
        ("ERGA08", "ambiguous", None, ["erga08eav3", "erga08evh7"]),
        ("EPGA11DV", "alias", "epga11dav3", ["epga11dav3"]),
        ("ERLA11DV37", "alias", "erla11dav3", ["erla11dav3"]),
        ("EPRA12EVH7", "alias", "epra12eav3", ["epra12eav3"]),
        # three-phase: a three-phase datasheet first, else the same unit's
        ("EPRA14DAW1", "alias", "epra14daw17", ["epra14daw17"]),
        ("EPRA12EAW1", "alias", "epra12eav3", ["epra12eav3"]),
        ("ERLA16DAW1", "alias", "erla16dav3", ["erla16dav3"]),
        ("EPRA14", "ambiguous", None, ["epra14dav3", "epra14daw17"]),
        # a given series letter must match: EBLA08 D is not our EBLA08 E
        ("EBLA08", "alias", "ebla08ev3", ["ebla08ev3"]),
        ("EBLA08DAV3", "unknown", None, []),
        ("EDLA08DAV3", "unknown", None, []),
        # flagged datasheets are never offered (EPRA11 E, ERLA12 D)
        ("EPRA11", "unknown", None, []),
        ("ERLA12DAW1", "unknown", None, []),
    ],
)
def test_family_and_size(text, kind, key, candidates):
    m = resolve_model_text(text)
    assert (m.kind, m.key, m.candidates) == (kind, key, candidates)
    assert all(c in MODEL_CHOICES and c not in FLAGGED_NON_CATALOGUE for c in m.candidates)


@pytest.mark.parametrize(("typed", "model"), [("Altherma 3 R ERGA06", "erga06eav3"), ("EPRA14DAW1", "epra14daw17")])
async def test_the_wizard_keeps_the_typed_code(hass, typed, model):
    _source(hass)
    flow = hass.config_entries.flow
    r = await flow.async_init(DOMAIN, context={"source": "user"})
    r = await flow.async_configure(r["flow_id"], {"family": typed, "source_type": "monolithic"})
    assert r["step_id"] == "model"
    data = flow._progress[r["flow_id"]]._data
    assert data["model"] == model and data["model_code"] == typed
    flow.async_abort(r["flow_id"])
