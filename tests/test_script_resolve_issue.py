from scripts.resolve_issue import build


def test_build_unreleased():
    c = build("unreleased", 373, "8252d0b", prod_verified=False)
    assert "vunreleased" not in c
    assert "## Merged in #373" in c
    assert "Prod replay confirmed" not in c
    assert "- [ ] Prod replay pending" in c
    assert "- [ ] Targeted for unreleased" in c


def test_build_released_no_prod():
    c = build("1.22.9", 374, "45aee24", prod_verified=False)
    assert "## Resolved in v1.22.9" in c
    assert "Prod replay confirmed" not in c
    assert "- [ ] Prod replay pending" in c
    assert "- [x] Released in v1.22.9" in c


def test_build_released_with_prod():
    c = build("1.22.9", 374, "45aee24", prod_verified=True)
    assert "## Resolved in v1.22.9" in c
    assert "Prod replay confirmed" in c
    assert "- [x] Released in v1.22.9" in c
