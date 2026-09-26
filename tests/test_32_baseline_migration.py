"""Batch 32 -- MultiBaseline 11->12 migration logging + marker."""
from __future__ import annotations

import logging

from custom_components.daikin_cycle_ml.ml.features import (
    VECTOR_LEN,
    VECTOR_LEN_LEGACY,
)
from custom_components.daikin_cycle_ml.ml.multi_baseline import MultiBaseline


def test_from_dict_dim_11_sets_marker(caplog):
    old = MultiBaseline(11).to_dict()
    with caplog.at_level(logging.INFO):
        mb = MultiBaseline.from_dict(old)
    assert mb.dim == VECTOR_LEN
    assert mb._migrated_from_dim == 11
    assert any(
        'obsolete/missing' in rec.message and rec.levelno == logging.INFO
        for rec in caplog.records
    )
    assert not any(rec.levelno >= logging.WARNING for rec in caplog.records)


def test_from_dict_dim_8_sets_marker():
    mb = MultiBaseline.from_dict(MultiBaseline(VECTOR_LEN_LEGACY).to_dict())
    assert mb.dim == VECTOR_LEN
    assert mb._migrated_from_dim == VECTOR_LEN_LEGACY


def test_from_dict_dim_12_no_marker():
    mb = MultiBaseline.from_dict(MultiBaseline(VECTOR_LEN).to_dict())
    assert mb.dim == VECTOR_LEN
    assert mb._migrated_from_dim is None


def test_from_dict_small_dim_no_marker():
    mb = MultiBaseline.from_dict(MultiBaseline(3).to_dict())
    assert mb.dim == 3
    assert mb._migrated_from_dim is None


def test_from_dict_none_dim_sets_no_marker():
    mb = MultiBaseline.from_dict({})
    assert mb.dim == VECTOR_LEN
    assert mb._migrated_from_dim is None


def test_class_attr_default_none():
    assert MultiBaseline._migrated_from_dim is None
    assert MultiBaseline(VECTOR_LEN)._migrated_from_dim is None
