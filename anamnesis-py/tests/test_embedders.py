"""Tests for the embedder factory and optional fastembed integration."""

from __future__ import annotations

import importlib.util

import numpy as np
import pytest
from anamnesis.storage import (
    embedder_for,
    fastembed_embedder,
    hash_embedder,
)

FASTEMBED_AVAILABLE = importlib.util.find_spec("fastembed") is not None


def test_embedder_for_hash_explicit():
    e = embedder_for("hash", dim=32)
    v = e("hello world")
    assert v.shape == (32,)
    assert np.isclose(np.linalg.norm(v), 1.0)


def test_embedder_for_unknown_raises():
    with pytest.raises(ValueError):
        embedder_for("not-a-real-embedder")


def test_embedder_for_default_works_when_fastembed_missing():
    # When fastembed isn't installed, default falls back to hash without error.
    e = embedder_for(dim=64)
    v = e("anything")
    assert v.shape[0] in (64, 384)  # 64 = hash, 384 = bge-small-en-v1.5


@pytest.mark.skipif(not FASTEMBED_AVAILABLE, reason="fastembed extra not installed")
def test_fastembed_embedder_produces_unit_norm_vector():
    e = fastembed_embedder()
    v = e("How do I compute the area of a triangle?")
    assert v.ndim == 1
    assert v.shape[0] >= 100
    assert np.isclose(np.linalg.norm(v), 1.0, atol=1e-6)


@pytest.mark.skipif(not FASTEMBED_AVAILABLE, reason="fastembed extra not installed")
def test_fastembed_similar_queries_have_lower_distance():
    e = fastembed_embedder()
    a = e("How do I compute the area of a triangle from base and height?")
    b = e("Calculating area of triangle when I know its base and height.")
    c = e("Recipe for chocolate cake with eggs and flour overnight.")
    sim_ab = float(a @ b)
    sim_ac = float(a @ c)
    assert sim_ab > sim_ac


def test_fastembed_embedder_raises_without_dep_when_explicit():
    if FASTEMBED_AVAILABLE:
        pytest.skip("fastembed is installed; cannot test ImportError path")
    with pytest.raises(ImportError):
        fastembed_embedder()


def test_hash_embedder_legacy_remains_available():
    e = hash_embedder(dim=16)
    v = e("legacy still works")
    assert v.shape == (16,)
